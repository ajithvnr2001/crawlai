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
try:
    from litellm.litellm_core_utils.model_param_helper import ModelParamHelper
    # Override the buggy function that tries to access __annotations__
    def patched_get_transcription_kwargs():
        return set()
    ModelParamHelper._get_litellm_supported_transcription_kwargs = staticmethod(patched_get_transcription_kwargs)
except Exception as e:
    # Fallback if imports change, though the above is the current path in stack trace
    pass

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Silence litellm further
litellm.set_verbose = False
litellm.drop_params = True
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)

DB_PATH = "crawl_state.db"
START_URL = "https://rclone.org/"
ALLOWED_DOMAINS = ["rclone.org", "forum.rclone.org"]
OUTPUT_DIR = "extracted_data"
EXCLUDED_EXTENSIONS = ('.txt', '.bin', '.exe', '.zip', '.tar.gz', '.rpm', '.deb', '.iso', '.img', '.dmg', '.pkg', '.msi', '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.svg')
BLACKLIST_PATTERNS = ["/fix-", "/integration-tests/", "/v1.", "/v1_", "beta.rclone.org", "pub.rclone.org","downloads.rclone.org"]

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

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
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable not set.")
        return

    state = StateManager(DB_PATH)
    state.add_url(START_URL, depth=0)

    browser_config = BrowserConfig(headless=True)
    
    # LLM Extraction Strategy
    extraction_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="gemini/gemini-2.5-flash-lite", 
            api_token=api_key
        ),
        instruction="Extract the main content of the page, including titles, sections, and technical details. Format the output as a clean JSON with 'title', 'main_content' (in markdown), and 'category' (e.g., documentation, blog, forum).",
        schema=None
    )

    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy
    )

    try:
        while True:
            row = state.get_pending_url()
            if not row:
                logger.info("No more pending URLs. Crawl complete.")
                break

            url, depth = row
            
            # [PRE-FETCH SKIP] Skip logs/binaries/noise already in the DB queue
            is_excluded_ext = url.lower().endswith(EXCLUDED_EXTENSIONS)
            is_blacklisted = any(pattern in url.lower() for pattern in BLACKLIST_PATTERNS)
            
            if is_excluded_ext or is_blacklisted:
                logger.info(f"Skipping noise/excluded URL: {url}")
                state.update_status(url, "skipped")
                continue

            try:
                async with AsyncWebCrawler(config=browser_config) as crawler:
                    while True:
                        # Inner loop to process multiple URLs per browser session for performance
                        logger.info(f"Crawling: {url} (Depth: {depth})")
                        state.update_status(url, "processing")

                        try:
                            result = await crawler.arun(url=url, config=run_config)
                            
                            if result.success:
                                # Save clean content (JSON from extraction strategy)
                                try:
                                    content_data = json.loads(result.extracted_content)
                                except Exception as e:
                                    logger.error(f"Error parsing extracted content for {url}: {e}")
                                    content_data = {"raw_markdown": result.markdown}

                                base_filename = url.replace("https://", "").replace("/", "_").replace(".", "_")
                                
                                # Save JSON
                                json_path = os.path.join(OUTPUT_DIR, base_filename + ".json")
                                with open(json_path, "w", encoding="utf-8") as f:
                                    json.dump(content_data, f, indent=2)
                                
                                # Save Markdown
                                md_path = os.path.join(OUTPUT_DIR, base_filename + ".md")
                                with open(md_path, "w", encoding="utf-8") as f:
                                    f.write(result.markdown)
                                
                                # Discover links
                                try:
                                    soup = BeautifulSoup(result.html, 'html.parser')
                                    for a in soup.find_all('a', href=True):
                                        raw_href = a['href'].split('#')[0].split('?')[0].strip().rstrip('/')
                                        if not raw_href or raw_href.startswith(('mailto:', 'tel:', 'javascript:')):
                                            continue
                                            
                                        full_url = urljoin(url, raw_href)
                                        parsed_uri = urlparse(full_url)
                                        
                                        # Filter for rclone domains and skip binaries/logs
                                        is_allowed = any(domain == parsed_uri.netloc or parsed_uri.netloc.endswith('.' + domain) 
                                                       for domain in ALLOWED_DOMAINS)
                                        
                                        is_valid_type = not full_url.lower().endswith(EXCLUDED_EXTENSIONS)
                                        is_not_blacklisted = not any(pattern in full_url.lower() for pattern in BLACKLIST_PATTERNS)
                                        
                                        if is_allowed and is_valid_type and is_not_blacklisted:
                                            state.add_url(full_url, depth + 1)
                                except Exception as e:
                                    logger.error(f"Error discovering links on {url}: {e}")
                                
                                state.update_status(url, "completed")
                                logger.info(f"Successfully crawled: {url}")
                            else:
                                # Handle deliberate failures (404, etc)
                                logger.error(f"Extraction failed for {url}: {result.error_message}")
                                state.update_status(url, "failed")

                        except Exception as e:
                            # Handle unexpected page-level navigation errors
                            logger.error(f"Page-level navigation failure for {url}: {e}")
                            state.update_status(url, "failed")
                            # If it's a fatal browser error, the 'async with' will likely raise it too

                        # Get next URL for the SAME browser session
                        await asyncio.sleep(1)
                        row = state.get_pending_url()
                        if not row:
                            break
                        url, depth = row
                        
                        # Pre-check again for the next URL
                        if url.lower().endswith(EXCLUDED_EXTENSIONS):
                            state.update_status(url, "skipped")
                            # Need to get another one
                            row = state.get_pending_url()
                            if not row: break
                            url, depth = row

            except Exception as e:
                # Fatal browser error handler - allows the outer loop to RESTART the browser
                logger.error(f"FATAL: Browser context crashed or failed to initialize: {e}")
                logger.info("Attempting recovery in 5 seconds...")
                await asyncio.sleep(5)
                # The outer loop will call get_pending_url() and try again
    except Exception as e:
        logger.error(f"Fatal error in crawl loop: {e}")
    finally:
        logger.info("Crawler finished.")

if __name__ == "__main__":
    asyncio.run(crawl_rclone())
