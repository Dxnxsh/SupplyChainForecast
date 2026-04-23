# src/data_acquisition.py

import json
import os
import time
from datetime import datetime

# NOTE: crawl4ai can be incompatible with older/newer Python environments or may
# not be installed in the user's venv. Avoid importing it at module import time
# so importing this module doesn't crash the whole program. We'll import it
# lazily inside the function that actually needs it.


# Import default user agent from config (optional). If the project doesn't
# provide config/config.py, fall back to a sensible default.
try:
    from config.config import DEFAULT_USER_AGENT  # type: ignore
except Exception:
    DEFAULT_USER_AGENT = "SupplyChainForecastBot/1.0 (+https://example.com)"

# --- General Utility Function for Saving Raw Data ---
def save_raw_data(data, filename_prefix, source_type):
    """Saves raw data to a JSON Lines file in data/raw/{source_type}/."""
    output_dir = os.path.join('data', 'raw', source_type)
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")

    # Ensure data is a list of dictionaries before processing
    if not isinstance(data, list):
        data = [data] # Wrap single items in a list

    with open(filepath, 'a', encoding='utf-8') as f:
        for entry in data:
            try:
                # Standardize timestamp if present and not already ISO
                if 'timestamp' in entry and isinstance(entry['timestamp'], str):
                    try:
                        # Attempt to parse common string formats to ISO
                        # This is a generic attempt; specific formats may need custom parsing
                        parsed_dt = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                        entry['timestamp'] = parsed_dt.isoformat()
                    except ValueError:
                        pass # Keep as is if parsing fails

                json.dump(entry, f, ensure_ascii=False)
                f.write('\n')
            except TypeError as e:
                print(f"Error serializing entry for {filename_prefix}: {entry}. Error: {e}")
                continue # Skip to next entry if there's a serialization error
    print(f"Saved {len(data)} entries to {filepath}")


# --- crawl4ai Web Scraper ---
def crawl4ai_output_handler(item, source_name):
    """
    Callback function for crawl4ai to process and save extracted items.
    'item' should be a dictionary containing 'title', 'text', 'url', 'timestamp' etc.
    """
    if not item or not item.get('url'): # Basic validation
        print(f"  Skipping invalid item from {source_name}: {item.get('url', 'No URL')}")
        return

    # Add 'source' field if not present in item
    if 'source' not in item:
        item['source'] = source_name

    # Basic content validation - ensure 'text' or 'title' is not empty
    if not item.get('text') and not item.get('title'):
         print(f"  Skipping item with no text/title from {source_name}: {item.get('url')}")
         return

    save_raw_data(item, source_name.replace(" ", "_").lower(), "web_scrape")


def run_crawl4ai_scraper(seed_urls, allowed_domains, source_name, max_pages=50, max_depth=2, selectors=None):
    """
    Configures and runs crawl4ai for specific target URLs.
    `seed_urls`: List of starting URLs (e.g., archive pages, category listings).
    `allowed_domains`: List of domains the crawler is allowed to visit.
    `source_name`: A unique name for the source (e.g., "PortOfLongBeachNews").
    `max_pages`: Maximum number of unique pages to crawl per run.
    `max_depth`: How many links deep to follow from seed URLs.
    `selectors`: Optional dictionary for custom CSS/XPath selectors for 'title', 'text', 'timestamp'.
                 This is highly recommended for accurate extraction.
    """
    print(f"Starting crawl4ai for {source_name} from {seed_urls}...")

    # Lazy import to avoid raising errors at module import time if crawl4ai is
    # not installed or is incompatible with the runtime.
    try:
        import crawl4ai
    except Exception as e:
        # Provide an actionable error message and return False so callers
        # can decide how to proceed instead of crashing.
        print(f"crawl4ai could not be imported: {e}")
        print("  - Ensure 'crawl4ai' is installed in your virtualenv: pip install crawl4ai")
        print("  - If it's installed, check compatibility with your Python version.")
        return False

    # Using a custom User-Agent for polite scraping
    headers = {'User-Agent': DEFAULT_USER_AGENT}

    # Build a CrawlerRunConfig using crawl4ai's dataclass (if available)
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
        import asyncio
    except Exception as e:
        print(f"Error importing AsyncWebCrawler/CrawlerRunConfig: {e}")
        return False

    async def _run():
        async with AsyncWebCrawler() as crawler:
            for seed in seed_urls:
                # Build a per-URL run config. Not all settings in the original
                # dict have direct equivalents; map the important ones.
                cfg = CrawlerRunConfig(
                    url=seed,
                    user_agent=DEFAULT_USER_AGENT,
                    verbose=False,
                    # IMPORTANT: Wait for JS-rendered content to load
                    wait_until="networkidle",  # Wait until network is idle
                    delay_before_return_html=2.0,  # Wait 2 seconds for JS to render
                    # Use 'experimental' dict to pass custom values if needed
                    experimental={
                        'allowed_domains': allowed_domains,
                        'max_pages_to_crawl': max_pages,
                        'max_depth': max_depth,
                        'selectors': selectors if selectors else {}
                    }
                )
                try:
                    result_or_gen = crawler.arun(seed, config=cfg)
                    # If arun returned an async generator, iterate it
                    if hasattr(result_or_gen, '__aiter__'):
                        async for item in result_or_gen:
                            try:
                                crawl4ai_output_handler(item, source_name)
                            except Exception as e:
                                print(f"  Error handling item from {seed}: {e}")
                    else:
                        # Otherwise it's awaitable/coroutine returning a result container
                        res = await result_or_gen
                        # Try to handle known result container types from crawl4ai
                        try:
                            from crawl4ai import models as c4models
                        except Exception:
                            c4models = None

                        if res is None:
                            # No results
                            pass
                        else:
                            # If it's a CrawlResultContainer, iterate its CrawlResult entries
                            handled = False
                            if c4models is not None and isinstance(res, getattr(c4models, 'CrawlResultContainer', (object,))):
                                try:
                                    for cr in res:
                                        item = {}
                                        if hasattr(cr, 'url'):
                                            item['url'] = getattr(cr, 'url')
                                        
                                        # Extract text from HTML using BeautifulSoup since markdown/text may be empty
                                        html = getattr(cr, 'html', '')
                                        if html:
                                            try:
                                                from bs4 import BeautifulSoup
                                                soup = BeautifulSoup(html, 'html.parser')
                                                extracted_text = soup.get_text(separator=' ', strip=True)
                                                item['text'] = extracted_text if extracted_text else html[:10000]
                                            except Exception as e:
                                                # Fallback to raw HTML if BeautifulSoup fails
                                                item['text'] = html[:10000]
                                        
                                        # Try to get markdown if available (better formatted)
                                        markdown = getattr(cr, 'markdown', '')
                                        if markdown and len(markdown) > 10:
                                            item['text'] = markdown
                                        
                                        if hasattr(cr, 'title'):
                                            item['title'] = getattr(cr, 'title')
                                        if hasattr(cr, 'metadata'):
                                            metadata = getattr(cr, 'metadata', {})
                                            if metadata and isinstance(metadata, dict):
                                                item['title'] = metadata.get('title', item.get('title', ''))
                                        
                                        if hasattr(cr, 'timestamp'):
                                            item['timestamp'] = getattr(cr, 'timestamp')
                                        try:
                                            crawl4ai_output_handler(item, source_name)
                                        except Exception as e:
                                            print(f"  Error handling CrawlResult from {seed}: {e}")
                                    handled = True
                                except Exception as e:
                                    print(f"  Error iterating CrawlResultContainer: {e}")

                            if not handled:
                                # Fallback: if it's iterable, iterate and pass items through
                                try:
                                    for item in res:
                                        try:
                                            crawl4ai_output_handler(item, source_name)
                                        except Exception as e:
                                            print(f"  Error handling item from {seed}: {e}")
                                except Exception:
                                    # Can't iterate/rescue; ignore
                                    pass
                except Exception as e:
                    print(f"  Error during async crawl for {source_name} seed {seed}: {e}")
                    # Continue to next seed rather than aborting entirely
                    continue
        return True

    try:
        return asyncio.run(_run())
    except Exception as e:
        print(f"  Error running asyncio loop for {source_name}: {e}")
        return False


# --- Main Execution for Testing (Optional, useful for quick checks) ---
if __name__ == "__main__":
    print("\n--- Testing crawl4ai Scraper (Port of Long Beach News Archive) ---")
    polb_seed_urls = ["https://polb.com/news/archive/"]
    polb_allowed_domains = ["polb.com"]
    # IMPORTANT: Inspect Element for polb.com/news/archive/ to find actual selectors for title, text, timestamp
    # This is just an example; you NEED to verify these on the actual site.
    # If 'extract_main_content_only' works well, you might not need custom selectors initially.
    polb_selectors = {
        # Example:
        # "title": "h1.entry-title",
        # "text": "div.entry-content",
        # "timestamp": "time.entry-date"
    }
    run_crawl4ai_scraper(polb_seed_urls, polb_allowed_domains, "PortOfLongBeachOfficialNews", max_pages=10, max_depth=1, selectors=polb_selectors)
    time.sleep(15)

    print("\n--- Testing crawl4ai Scraper (Taiwan News Archive - Main Page) ---")
    # Find a suitable archive or category page for Taiwan news relevant to TSMC
    taiwan_news_seed_urls = ["https://www.taiwannews.com.tw/archive/"] # Or more specific: https://www.taiwannews.com.tw/p/13
    taiwan_news_allowed_domains = ["taiwannews.com.tw"]
    # As above, check 'Inspect Element' for specific article content selectors
    taiwan_news_selectors = {
        # Example:
        # "title": "h1.article-title",
        # "text": "div.article-content",
        # "timestamp": "span.publish-date"
    }
    run_crawl4ai_scraper(taiwan_news_seed_urls, taiwan_news_allowed_domains, "TaiwanNewsArchive", max_pages=10, max_depth=1, selectors=taiwan_news_selectors)
    time.sleep(15)

    # Add more tests for your other chosen sources