import asyncio
import sqlite3
import os
import json
import logging
from urllib.parse import urljoin, urlparse
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, LLMConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from bs4 import BeautifulSoup
import litellm
import boto3
from botocore.config import Config

# --- Configuration ---
S3_CONFIG = {
    "endpoint_url": os.getenv("S3_ENDPOINT", "https://s3.us-west-1.wasabisys.com"),
    "access_key": os.getenv("S3_ACCESS_KEY"),
    "secret_key": os.getenv("S3_SECRET_KEY"),
    "bucket": os.getenv("S3_BUCKET", "crawlai")
}

DB_PATH = "crawl_state.db"
START_URL = "https://rclone.org/"
ALLOWED_DOMAINS = ["rclone.org", "forum.rclone.org"]
BLACKLIST_PATTERNS = ["/fix-", "/integration-tests/", "/v1.", "/v1_", "beta.rclone.org", "pub.rclone.org", "downloads.rclone.org"]
EXCLUDED_EXTENSIONS = ('.txt', '.bin', '.exe', '.zip', '.tar.gz', '.rpm', '.deb', '.iso', '.img', '.dmg', '.pkg', '.msi', '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.svg')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WasabiStorage:
    def __init__(self, config):
        self.s3 = boto3.client(
            's3',
            endpoint_url=config["endpoint_url"],
            aws_access_key_id=config["access_key"],
            aws_secret_access_key=config["secret_key"],
            config=Config(signature_version='s3v4')
        )
        self.bucket = config["bucket"]

    def upload_file(self, local_path, s3_path):
        try:
            self.s3.upload_file(local_path, self.bucket, s3_path)
            # logger.info(f"Uploaded {local_path} to s3://{self.bucket}/{s3_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload {local_path}: {e}")
            return False

    def download_file(self, s3_path, local_path):
        try:
            self.s3.download_file(self.bucket, s3_path, local_path)
            logger.info(f"Downloaded s3://{self.bucket}/{s3_path} to {local_path}")
            return True
        except Exception as e:
            logger.warning(f"Could not download {s3_path} from S3: {e}")
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
        except Exception as e:
            logger.error(f"Error adding URL {url}: {e}")

    def get_pending_url(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT url, depth FROM urls WHERE status = 'pending' LIMIT 1")
            return cursor.fetchone()

    def update_status(self, url, status):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE urls SET status = ?, last_updated = CURRENT_TIMESTAMP WHERE url = ?", (status, url))
            conn.commit()

async def crawl_rclone():
    api_key = os.getenv("GEMINI_API_KEY")
    storage = WasabiStorage(S3_CONFIG)
    
    # Restore DB from S3
    logger.info("Restoring crawl state from S3...")
    storage.download_file(DB_PATH, DB_PATH)
    
    state = StateManager(DB_PATH)
    state.add_url(START_URL, depth=0)

    browser_config = BrowserConfig(headless=True)
    
    extraction_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="gemini/gemini-2.0-flash-exp", 
            api_token=api_key
        ),
        instruction="Extract technical documentation. Return JSON with 'title', 'main_content' (markdown), and 'category'.",
    )

    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy
    )

    processed_count = 0

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            while True:
                row = state.get_pending_url()
                if not row: break

                url, depth = row
                if any(p in url.lower() for p in BLACKLIST_PATTERNS) or url.lower().endswith(EXCLUDED_EXTENSIONS):
                    state.update_status(url, "skipped")
                    continue

                logger.info(f"Crawling: {url}")
                state.update_status(url, "processing")

                try:
                    result = await crawler.arun(url=url, config=run_config)
                    
                    if result.success:
                        # Save and Upload
                        base_filename = url.replace("https://", "").replace("/", "_").replace(".", "_")
                        json_name = f"{base_filename}.json"
                        md_name = f"{base_filename}.md"
                        
                        with open(json_name, "w", encoding="utf-8") as f:
                            f.write(result.extracted_content)
                        storage.upload_file(json_name, f"extracted_data/{json_name}")
                        
                        with open(md_name, "w", encoding="utf-8") as f:
                            f.write(result.markdown)
                        storage.upload_file(md_name, f"extracted_data/{md_name}")
                        
                        # Discovery
                        soup = BeautifulSoup(result.html, 'html.parser')
                        for a in soup.find_all('a', href=True):
                            raw_href = a['href'].split('#')[0].split('?')[0].strip().rstrip('/')
                            if not raw_href or raw_href.startswith(('mailto:', 'tel:', 'javascript:')): continue
                            full_url = urljoin(url, raw_href)
                            parsed = urlparse(full_url)
                            if any(d == parsed.netloc or parsed.netloc.endswith('.' + d) for d in ALLOWED_DOMAINS):
                                if not any(p in full_url.lower() for p in BLACKLIST_PATTERNS) and not full_url.lower().endswith(EXCLUDED_EXTENSIONS):
                                    state.add_url(full_url, depth + 1)
                        
                        state.update_status(url, "completed")
                        processed_count += 1
                        
                        # Cleanup local
                        os.remove(json_name)
                        os.remove(md_name)
                        
                        if processed_count % 5 == 0:
                            logger.info("Backing up database to S3...")
                            storage.upload_file(DB_PATH, DB_PATH)
                    else:
                        state.update_status(url, "failed")
                except Exception as e:
                    logger.error(f"Error on {url}: {e}")
                    state.update_status(url, "failed")

    finally:
        storage.upload_file(DB_PATH, DB_PATH)
        logger.info("Crawler finished.")

if __name__ == "__main__":
    asyncio.run(crawl_rclone())
