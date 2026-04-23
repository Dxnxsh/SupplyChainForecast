# src/main_acquisition.py

# Make imports robust so the module can be used either
#  - as a package (python -m src.main_acquisition)
#  - or run directly by path (python src/main_acquisition.py or using an absolute path)
try:
    # Preferred: import as a package when running from the project root
    from src.data_acquisition import (
        run_crawl4ai_scraper
    )
except ModuleNotFoundError:
    # Fallback: running the file directly (sys.path[0] == src/), import the sibling module
    from data_acquisition import run_crawl4ai_scraper
from datetime import datetime, timedelta
import time
import argparse

def run_all_data_acquisition():
    print("--- Starting All Data Acquisition Tasks ---")

    # --- crawl4ai Web Scrapers for ALL identified sources ---

    # 1. Port of Long Beach Official News Archive
    print("\n--- Running crawl4ai for Port of Long Beach News ---")
    polb_archive_seed_urls = ["https://polb.com/news/archive/"]
    polb_archive_allowed_domains = ["polb.com"]
    # Provide specific selectors if 'extract_main_content_only' isn't perfect for this site
    run_crawl4ai_scraper(polb_archive_seed_urls, polb_archive_allowed_domains, "PortOfLongBeachOfficialNews", max_pages=20, max_depth=1)
    time.sleep(15) # Longer delay after a crawl

    # 2. Taiwan News Archive (e.g., taiwannews.com.tw or a government news site)
    # IMPORTANT: VERIFY the seed URL and selectors with "Inspect Element"
    print("\n--- Running crawl4ai for Taiwan News Archive (TSMC relevance) ---")
    taiwan_news_seed_urls = ["https://www.taiwannews.com.tw/archive/"] # Check actual archive structure
    taiwan_news_allowed_domains = ["taiwannews.com.tw"]
    # Example selectors; customize after inspecting the site!
    taiwan_news_selectors = {
        # "title": "h3.title-class",
        # "text": "div.content-body",
        # "timestamp": "span.date-class"
    }
    run_crawl4ai_scraper(taiwan_news_seed_urls, taiwan_news_allowed_domains, "TaiwanNewsArchive", max_pages=20, max_depth=1, selectors=taiwan_news_selectors)
    time.sleep(15)

    # 3. China Local/Industry News/Blog (Foxconn Zhengzhou relevance)
    # IMPORTANT: This is a placeholder. You NEED to find a real, scrape-friendly site
    # that covers local news or industry discussions around Zhengzhou/Foxconn.
    # Chinese websites might also have character encoding issues to consider.
    print("\n--- Running crawl4ai for China Local/Industry News (Foxconn relevance) ---")
    foxconn_site_seed_urls = ["http://www.zhengzhou.gov.cn/zwdt/zzyw/"] # EXAMPLE: Zhengzhou gov news
    foxconn_site_allowed_domains = ["zhengzhou.gov.cn"] # EXAMPLE
    foxconn_selectors = {} # Customize as needed
    run_crawl4ai_scraper(foxconn_site_seed_urls, foxconn_site_allowed_domains, "ZhengzhouLocalNews", max_pages=20, max_depth=2, selectors=foxconn_selectors)
    time.sleep(15)

    # Add `crawl4ai` calls for other supply chain nodes and sources here.
    # E.g., for EV Battery: a lithium mining news site, a battery manufacturer's press releases, etc.

    print("\nAll crawl4ai data acquisition tasks completed. Check 'data/raw/web_scrape/' for results.")

if __name__ == "__main__":
    # Ensure you are running this from the project root:
    # python src/main_acquisition.py
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-crawls', action='store_true', help='Skip running crawl4ai scrapers (useful for testing without crawl4ai)')
    args = parser.parse_args()

    if args.skip_crawls:
        print('Skipping crawls as requested (--skip-crawls). Exiting.')
    else:
        run_all_data_acquisition()