# Rclone Advanced Documentation Crawler (CrawlAI)

A professional-grade, resilient web crawler ecosystem designed to recursively process technical documentation and forums, extracting structured content into JSON and Markdown using state-of-the-art LLMs (Gemini & NVIDIA/StepFun).

---

## 🚀 Overview

This repository contains three specialized versions of the crawler, optimized for different environments:

1.  **`rclone_crawler.py` (Local/Desktop)**: Standard version using Google Gemini 2.0 Flash for content extraction. Optimized for single-machine use with local SQLite state management.
2.  **`rclone_crawler_colab.py` (Cloud/Gemini)**: Migrated version for Google Colab. Features **Wasabi S3 Persistence** and database synchronization to handle Colab session disconnects.
3.  **`rclone_crawler_nvidia_colab.py` (High-Speed/NVIDIA)**: The most advanced version. Uses NVIDIA's `stepfun-ai/step-3.5-flash` model via direct OpenAI-compatible integration. Optimized for speed with **Phase-Separated Execution** and **Presigned S3 URLs**.

---

## 🛠 Features & Architecture

### 1. Persistence Layer (Wasabi S3)
- **Zero-Loss State**: The SQLite database (`crawl_state.db`) is automatically synced to Wasabi S3 every 5 pages. Upon restarting a session, the crawler automatically pulls the latest state from the cloud.
- **Direct Streaming**: Extracted `.json` and `.md` files are uploaded immediately to S3, bypassing limited local disk space in cloud environments.
- **Presigned URLs**: (NVIDIA Version) Generates temporary, clickable S3 links in the console for instant verification of extraction quality.

### 2. High-Performance Crawling
- **LIFO URL Prioritization**: The crawler prioritizes the most recently discovered links. This allows it to process new forum topics and recent updates immediately, even with a backlog of 15k+ URLs.
- **Aggressive HTML Pruning**: Uses BeautifulSoup to strip scripts, styles, navbars, footers, and sidebars before sending content to the LLM. This reduces token usage by 60-80% and speeds up extraction.
- **Phase-Separated Logging**: Provides granular timing for **Fetch**, **Prune**, **LLM Extraction**, and **S3 Upload** phases to identify bottlenecks.

### 3. Resilience & Self-Healing
- **Browser Recovery**: Automatically catches `TargetClosedError` or `detached frame` errors. If Playwright crashes, the script re-initializes the browser instance and continues from the current URL.
- **Navigation Retries**: Built-in 2-attempt retry logic for network-level failures (`net::ERR_ABORTED`).
- **Domain Guardians**: Strict domain and subdomain filtering (skips noise like `beta.rclone.org` and `pub.rclone.org`) with pattern-based blacklisting for integration tests and legacy versions.

---

## 🔧 Installation & Setup

### Requirements
- Python 3.10+
- [Crawl4AI 0.4.0+](https://github.com/unclecode/crawl4ai)
- Playwright
- Boto3 (for S3 support)
- OpenAI/AsyncOpenAI (for NVIDIA integration)

### Installation
```bash
pip install crawl4ai beautifulsoup4 litellm boto3 openai
playwright install
```

### Environment Variables
The crawlers are sanitized and require the following environment variables:

| Variable | Description | Example |
| :--- | :--- | :--- |
| `S3_ENDPOINT` | Wasabi S3 Endpoint | `https://s3.us-west-1.wasabisys.com` |
| `S3_ACCESS_KEY` | Wasabi Access Key | `YOUR_ACCESS_KEY` |
| `S3_SECRET_KEY` | Wasabi Secret Key | `YOUR_SECRET_KEY` |
| `S3_BUCKET` | Destination Bucket | `crawlai` |
| `GEMINI_API_KEY` | Google Gemini Key | `YOUR_GEMINI_KEY` |
| `NVIDIA_API_KEY` | NVIDIA integrate key | `nvapi-XXXX` |

---

## 📜 Usage Instructions

### Running in Google Colab (Recommended for Large Backlogs)
1. Open a new Colab Notebook.
2. Install dependencies: `!pip install crawl4ai beautifulsoup4 boto3 openai && playwright install`.
3. Set your environment variables (using Colab Secrets or `os.environ`).
4. Copy the contents of `rclone_crawler_nvidia_colab.py` into a cell and run.

### Running Locally
```bash
python rclone_crawler.py
```

---

## 📂 Project Structure
- `rclone_crawler_nvidia_colab.py`: Feature-complete version for NVIDIA API.
- `rclone_crawler_colab.py`: Original S3 version for Gemini.
- `rclone_crawler.py`: Local execution version.
- `check_url.py`: Tool to verify the status of a specific URL in the local DB.
- `inspect_s3.py`: Lists the most recent 50 objects and state files on Wasabi S3.
- `nvidia.py`: Standalone sample for verifying NVIDIA API connectivity.

---

## ⚖️ License
This project is optimized for technical research and documentation synthesis. Use responsibly within the rate limits of your LLM providers.
