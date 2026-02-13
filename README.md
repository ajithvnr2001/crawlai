# CrawlAI v1

A high-performance, resilient web crawler designed to recursively crawl websites and extract clean, structured content using Google's Gemini 2.5 Flash Lite LLM.

## Overview

CrawlAI is built on top of `crawl4ai` and `Playwright` to provide a robust solution for data extraction from technical documentation, blogs, and forums. It uses an LLM-based extraction strategy to ensure that the data collected is clean, categorized, and formatted in Markdown and JSON.

### Key Features

- **Recursive Crawling**: Automatically discovers and follows links within allowed domains.
- **Deep Extraction**: Uses Gemini 2.5 Flash Lite to extract 'title', 'main_content', and 'category' from every page.
- **Resilient Stateful Crawl**: Uses an SQLite database to track 'pending', 'processing', 'completed', and 'failed' URLs, allowing for easy resumes after crashes or interruptions.
- **Zero-Logging Noise**: Includes custom monkeypatching for `litellm` to bypass known library bugs and provide a clean terminal experience.
- **Dual Export**: Saves every page as a structured JSON file and a full raw Markdown file for maximum data retention.

## How It Works

1. **Initialization**: The crawler starts at the `START_URL` and adds it to an SQLite database.
2. **Dynamic Processing**: It pulls the next "pending" URL and opens it in a headless browser via Playwright.
3. **LLM Extraction**: The page HTML is sent to Gemini with specific instructions to extract structured technical content.
4. **Link Discovery**: It parses the page to find new links, filters them by domain, and adds them to the database queue (Depth + 1).
5. **State Management**: Every step is recorded in the DB, ensuring that no page is crawled twice.

## Prerequisites

- Python 3.10+
- [Crawl4AI](https://github.com/unclecode/crawl4ai)
- Playwright (`playwright install`)
- Google Gemini API Key

## Setup & Running

1. **Install Dependencies**:
   ```bash
   pip install crawl4ai beautifulsoup4 litellm
   playwright install
   ```

2. **Configure API Key**:
   Set your Gemini API key in your environment variables.

   **Windows (PowerShell):**
   ```powershell
   $env:GEMINI_API_KEY = "your_key_here"
   ```

   **Linux/Mac:**
   ```bash
   export GEMINI_API_KEY="your_key_here"
   ```

3. **Run the Crawler**:
   ```bash
   python rclone_crawler.py
   ```

## Project Structure

- `rclone_crawler.py`: The main crawler script with built-in state management and LLM logic.
- `crawl_state.db`: SQLite database tracking crawl progress (auto-generated).
- `extracted_data/`: Directory containing JSON and Markdown exports (auto-generated).

## Why This?

This project was specifically optimized to crawl complex technical documentation (like rclone.org) where standard scrapers often fail to distinguish between code blocks, navigation menus, and actual content. By leveraging Gemini, CrawlAI "understands" the page structure and extract only the relevant information.
