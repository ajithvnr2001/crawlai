import asyncio
import sqlite3
import os
import json
import logging
import time
import re
from urllib.parse import urljoin, urlparse
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor

# --- Configuration ---
S3_CONFIG = {
    "endpoint_url": os.getenv("S3_ENDPOINT", "https://s3.us-west-1.wasabisys.com"),
    "access_key": os.getenv("S3_ACCESS_KEY"),
    "secret_key": os.getenv("S3_SECRET_KEY"),
    "bucket": os.getenv("S3_BUCKET", "crawlai")
}

NVIDIA_CONFIG = {
    "api_key": os.getenv("NVIDIA_API_KEY"),
    "base_url": os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
    "model": os.getenv("NVIDIA_MODEL", "stepfun-ai/step-3.5-flash") 
}

DB_PATH = "crawl_state_updated.db"
START_URL = "https://rclone.org/"
ALLOWED_DOMAINS = ["rclone.org", "forum.rclone.org"]
BLACKLIST_PATTERNS = ["/fix-", "/integration-tests/", "/v1.", "/v1_", "beta.rclone.org", "pub.rclone.org", "downloads.rclone.org"]
EXCLUDED_EXTENSIONS = ('.txt', '.bin', '.exe', '.zip', '.tar.gz', '.rpm', '.deb', '.iso', '.img', '.dmg', '.pkg', '.msi', '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.svg')

# Rate limit settings (39 RPM)
MIN_LLM_INTERVAL = 60.0 / 39.0 # ~1.54 seconds
last_llm_call_time = 0

# Thread pool for non-blocking S3 uploads
executor = ThreadPoolExecutor(max_workers=4)

class S3Persistence:
    def __init__(self, config):
        self.s3 = boto3.client(
            's3',
            endpoint_url=config["endpoint_url"],
            aws_access_key_id=config["access_key"],
            aws_secret_access_key=config["secret_key"],
            config=Config(signature_version='s3v4')
        )
        self.bucket = config["bucket"]

    async def upload_file_async(self, local_path, s3_path):
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(executor, self.s3.upload_file, local_path, self.bucket, s3_path)
            # Generate presigned URL for instant review (valid for 1 hour)
            url = self.s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': s3_path},
                ExpiresIn=3600
            )
            return url
        except Exception as e:
            print(f"  [S3 ERR] Failed to upload {local_path}: {e}")
            return None

    def download_file(self, s3_path, local_path):
        try:
            self.s3.download_file(self.bucket, s3_path, local_path)
            print(f"  [S3] Restored database from cloud.")
            return True
        except Exception as e:
            print(f"  [S3] No cloud backup found, starting fresh.")
            return False

class StateManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS urls (
                    url TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'pending',
                    depth INTEGER DEFAULT 0,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def add_url(self, url, depth=0):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("INSERT OR IGNORE INTO urls (url, depth) VALUES (?, ?)", (url, depth))
                conn.commit()
        except: pass

    def get_pending_url(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT url, depth FROM urls WHERE status = 'pending' ORDER BY last_updated DESC LIMIT 1")
            return cursor.fetchone()

    def update_status(self, url, status):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE urls SET status = ?, last_updated = CURRENT_TIMESTAMP WHERE url = ?", (status, url))
            conn.commit()

def clean_html_pruned(html):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "svg", "meta", "link"]):
        tag.decompose()
    for noisy in soup.select('.nav, .navbar, .footer, .sidebar, .ad, .avatar, .signature, .social-share'):
        noisy.decompose()
    return str(soup)

def clean_llm_json(content):
    """Strip markdown backticks and whitespace from LLM response."""
    if not content: return None
    # Remove markdown code blocks if present
    content = re.sub(r'^```json\s*', '', content.strip())
    content = re.sub(r'\s*```$', '', content)
    return content.strip()

async def extract_with_nvidia_direct(client, url, html_content):
    global last_llm_call_time
    now = time.time()
    elapsed = now - last_llm_call_time
    if elapsed < MIN_LLM_INTERVAL:
        await asyncio.sleep(MIN_LLM_INTERVAL - elapsed)
    last_llm_call_time = time.time()
    
    prompt = f"Extract technical documentation from {url} into a JSON object with 'title', 'content' (markdown), and 'code_snippets'. Output ONLY the JSON object.\n\nHTML:\n{html_content[:12000]}"
    
    try:
        response = await client.chat.completions.create(
            model=NVIDIA_CONFIG["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
            # response_format is broken for this model on NVIDIA endpoint
        )
        raw_content = response.choices[0].message.content
        return clean_llm_json(raw_content)
    except Exception as e:
        print(f"  [LLM ERR] {e}")
        return None

async def crawl_rclone():
    s3 = S3Persistence(S3_CONFIG)
    openai_client = AsyncOpenAI(api_key=NVIDIA_CONFIG["api_key"], base_url=NVIDIA_CONFIG["base_url"])
    
    print("[INIT] Restoring state from S3...")
    s3.download_file(DB_PATH, DB_PATH)
    state = StateManager(DB_PATH)
    state.add_url(START_URL, depth=0)

    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until='domcontentloaded',
        page_timeout=35000, # Increased timeout
        word_count_threshold=5
    )

    processed_count = 0
    crawler = None

    try:
        while True:
            if crawler is None:
                print("[INIT] Starting fresh browser instance...")
                crawler = AsyncWebCrawler(config=browser_config)
                await crawler.start()

            row = state.get_pending_url()
            if not row: break

            url, depth = row
            if any(p in url.lower() for p in BLACKLIST_PATTERNS) or url.lower().endswith(EXCLUDED_EXTENSIONS):
                state.update_status(url, "skipped")
                continue

            print(f"\n[NEXT] {url}")
            state.update_status(url, "processing")
            t_start = time.time()

            try:
                # 1. FETCH with internal retry
                result = None
                for attempt in range(2):
                    try:
                        result = await crawler.arun(url=url, config=run_config)
                        if result.success: break
                    except Exception as e:
                        if attempt == 0: await asyncio.sleep(2)
                        else: raise e
                
                if not result or not result.success:
                    print(f"  [ERR] Fetch failed: {result.error_message if result else 'Unknown'}")
                    state.update_status(url, "failed")
                    continue

                # 2. LLM
                pruned_html = clean_html_pruned(result.html)
                extracted_json = await extract_with_nvidia_direct(openai_client, url, pruned_html)

                if not extracted_json:
                    print("  [ERR] Extraction results were None or empty.")
                    state.update_status(url, "failed")
                    continue

                # 3. S3
                base_name = url.replace("https://", "").replace("/", "_").replace(".", "_")
                with open(f"{base_name}.json", "w", encoding="utf-8") as f: f.write(extracted_json)
                with open(f"{base_name}.md", "w", encoding="utf-8") as f: f.write(result.markdown)
                
                json_url = await s3.upload_file_async(f"{base_name}.json", f"extracted_data/{base_name}.json")
                md_url = await s3.upload_file_async(f"{base_name}.md", f"extracted_data/{base_name}.md")
                
                # Discovery
                soup = BeautifulSoup(result.html, 'html.parser')
                discovered = 0
                for a in soup.find_all('a', href=True):
                    raw_href = a['href'].split('#')[0].split('?')[0].strip().rstrip('/')
                    if not raw_href or raw_href.startswith(('mailto:', 'tel:', 'javascript:')): continue
                    full_url = urljoin(url, raw_href)
                    parsed = urlparse(full_url)
                    if any(d in parsed.netloc for d in ALLOWED_DOMAINS):
                        if not any(p in full_url.lower() for p in BLACKLIST_PATTERNS) and not full_url.lower().endswith(EXCLUDED_EXTENSIONS):
                            state.add_url(full_url, depth + 1)
                            discovered += 1
                
                state.update_status(url, "completed")
                processed_count += 1
                
                try: 
                    os.remove(f"{base_name}.json")
                    os.remove(f"{base_name}.md")
                except: pass

                print(f"  [DONE] S3 Verified.")
                if json_url: print(f"  [JSON] {json_url}")
                if md_url:   print(f"  [MD  ] {md_url}")
                print(f"  [STATS] Total: {time.time()-t_start:.1f}s | Discover: {discovered}")

                if processed_count % 5 == 0:
                    print("  [SYNC] Periodic state backup...")
                    await s3.upload_file_async(DB_PATH, DB_PATH)

            except Exception as e:
                err_str = str(e)
                if any(x in err_str for x in ["TargetClosedError", "browser has been closed", "detached"]):
                    print(f"  [FIX] Browser/Navigation error. Resetting browser...")
                    try: await crawler.close()
                    except: pass
                    crawler = None
                else:
                    print(f"  [ERR] Page Loop: {e}")
                    state.update_status(url, "failed")

            await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        print("\n[STOP] User interrupted.")
    finally:
        if crawler: await crawler.close()
        await s3.upload_file_async(DB_PATH, DB_PATH)
        executor.shutdown(wait=False)

if __name__ == "__main__":
    asyncio.run(crawl_rclone())
