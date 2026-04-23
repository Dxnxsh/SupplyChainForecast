# src/smart_acquisition.py
"""
Smart web scraping with crawl4ai's intelligent crawling strategies.
Uses keyword-based filtering, link scoring, and deep crawl strategies to find relevant content.
"""

try:
    from src.data_acquisition import save_raw_data
except ModuleNotFoundError:
    from data_acquisition import save_raw_data

import asyncio
import time
from datetime import datetime


def run_smart_crawl(
    seed_urls,
    source_name,
    keywords,
    max_pages=50,
    max_depth=3,
    allowed_domains=None,
    user_agent=None
):
    """
    Run an intelligent crawl that automatically finds and follows relevant links.
    
    Args:
        seed_urls: List of starting URLs
        source_name: Name for this data source
        keywords: List of keywords to filter relevant content (e.g., ['supply chain', 'semiconductor', 'TSMC'])
        max_pages: Maximum pages to crawl
        max_depth: How deep to follow links
        allowed_domains: List of allowed domains (optional)
        user_agent: Custom user agent string (optional)
    """
    try:
        from crawl4ai import (
            AsyncWebCrawler, 
            CrawlerRunConfig,
            BrowserConfig,
            CacheMode
        )
        # Deep crawl strategies and filters
        from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
        from crawl4ai.deep_crawling.filters import (
            FilterChain,
            DomainFilter,
            URLPatternFilter
        )
        from crawl4ai.deep_crawling.scorers import (
            KeywordRelevanceScorer,
            CompositeScorer
        )
        # URL scoring for relevance
        from crawl4ai.async_configs import MatchMode
    except ImportError as e:
        print(f"Error importing crawl4ai components: {e}")
        print("Make sure you're using crawl4ai >= 0.7.0")
        return False

    if user_agent is None:
        user_agent = "SupplyChainForecastBot/1.0 (+https://example.com)"

    async def _smart_crawl():
        # Configure browser for efficient crawling
        browser_config = BrowserConfig(
            headless=True,
            verbose=False
        )
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            for seed in seed_urls:
                print(f"  Starting smart crawl from: {seed}")
                
                # Create filters for allowed domains and URL patterns
                filters = []
                
                if allowed_domains:
                    # Only crawl URLs from allowed domains
                    domain_filter = DomainFilter(allowed_domains=allowed_domains)
                    filters.append(domain_filter)
                
                # Filter URLs that likely contain relevant content
                # Look for news, article, press-release type URLs
                url_patterns = [
                    r'/news/',
                    r'/article/',
                    r'/press/',
                    r'/blog/',
                    r'/\d{4}/',  # Year in URL (news articles often have dates)
                ]
                if keywords:
                    # Add keyword patterns to URL matching
                    url_patterns.extend([kw.lower().replace(' ', '-') for kw in keywords[:3]])
                
                filter_chain = FilterChain(filters=filters) if filters else FilterChain()
                
                # Create a URL scorer based on keywords
                scorer = None
                if keywords:
                    scorer = KeywordRelevanceScorer(keywords=keywords)
                
                # Create a BFS (Breadth-First Search) strategy for deep crawling
                deep_crawl_strategy = BFSDeepCrawlStrategy(
                    max_depth=max_depth,
                    max_pages=max_pages,
                    filter_chain=filter_chain,
                    url_scorer=scorer,
                    score_threshold=0.0,  # Accept URLs with any positive score
                )
                
                # Build crawler configuration
                config = CrawlerRunConfig(
                    url=seed,
                    user_agent=user_agent,
                    cache_mode=CacheMode.BYPASS,  # Always fetch fresh content
                    
                    # CRITICAL: Wait for JavaScript to render content
                    wait_until="networkidle",  # Wait until network is idle
                    delay_before_return_html=2.0,  # Wait 2 seconds for JS
                    
                    # Deep crawl strategy - this makes it smart!
                    deep_crawl_strategy=deep_crawl_strategy,
                    
                    # Content filtering - only keep relevant paragraphs
                    word_count_threshold=50,  # Ignore very short text blocks
                    
                    # URL matching - you can use regex or keywords
                    url_matcher=keywords,  # URLs containing these keywords get priority
                    match_mode=MatchMode.OR,  # Match ANY keyword (not all)
                    
                    # Extract settings
                    only_text=False,  # Keep HTML structure for better parsing
                    screenshot=False,  # Set True if you want screenshots
                    
                    # Performance settings
                    page_timeout=60000,  # 60 second timeout
                    verbose=True,  # Show progress
                    
                    # Link scoring - prioritize relevant links
                    score_links=True,
                )
                
                try:
                    # Run the crawl
                    result_container = await crawler.arun(seed, config=config)
                    
                    # Process results
                    crawled_count = 0
                    for crawl_result in result_container:
                        # Extract data from each crawled page
                        html = crawl_result.html
                        
                        # Extract text from HTML (since markdown/text may be empty for JS sites)
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html, 'html.parser')
                        text = soup.get_text(separator=' ', strip=True)
                        
                        item = {
                            'url': crawl_result.url,
                            'title': getattr(crawl_result, 'metadata', {}).get('title', ''),
                            'text': text,
                            'html': html[:5000],  # Save first 5000 chars of HTML
                            'timestamp': datetime.now().isoformat(),
                            'source': source_name,
                            'keywords_matched': keywords,
                        }
                        
                        # Add metadata if available
                        if hasattr(crawl_result, 'metadata'):
                            item['metadata'] = crawl_result.metadata
                        
                        # Filter by keyword relevance (basic check)
                        text_lower = item['text'].lower()
                        if any(kw.lower() in text_lower for kw in keywords):
                            save_raw_data(item, source_name.replace(" ", "_").lower(), "web_scrape")
                            crawled_count += 1
                        
                    print(f"  ✓ Saved {crawled_count} relevant pages from {seed}")
                    
                except Exception as e:
                    print(f"  ✗ Error during smart crawl for {seed}: {e}")
                    continue
        
        return True

    try:
        return asyncio.run(_smart_crawl())
    except Exception as e:
        print(f"  Error in smart crawl for {source_name}: {e}")
        return False


def run_llm_filtered_crawl(
    seed_urls,
    source_name,
    llm_instruction,
    max_pages=30,
    allowed_domains=None
):
    """
    Use an LLM to filter and extract only relevant content.
    Requires an OpenAI API key or compatible LLM provider.
    
    Args:
        seed_urls: List of starting URLs
        source_name: Name for this data source
        llm_instruction: Instruction for the LLM (e.g., "Extract news about supply chain disruptions")
        max_pages: Maximum pages to crawl
        allowed_domains: List of allowed domains
    """
    try:
        from crawl4ai import (
            AsyncWebCrawler,
            CrawlerRunConfig,
            CacheMode
        )
        from crawl4ai.extraction_strategy import LLMExtractionStrategy
        from crawl4ai.content_filter_strategy import LLMContentFilter
    except ImportError as e:
        print(f"Error importing crawl4ai LLM components: {e}")
        return False

    async def _llm_crawl():
        async with AsyncWebCrawler() as crawler:
            for seed in seed_urls:
                print(f"  Starting LLM-filtered crawl from: {seed}")
                
                # Create LLM extraction strategy
                llm_strategy = LLMExtractionStrategy(
                    provider="openai/gpt-4o-mini",  # or "openai/gpt-3.5-turbo" for cheaper
                    instruction=llm_instruction,
                    schema={
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "summary": {"type": "string"},
                            "relevant": {"type": "boolean"},
                            "key_facts": {"type": "array", "items": {"type": "string"}},
                        }
                    }
                )
                
                config = CrawlerRunConfig(
                    url=seed,
                    extraction_strategy=llm_strategy,
                    cache_mode=CacheMode.BYPASS,
                    verbose=True,
                )
                
                try:
                    result_container = await crawler.arun(seed, config=config)
                    
                    for crawl_result in result_container:
                        # The LLM will have extracted structured data
                        if hasattr(crawl_result, 'extracted_content'):
                            extracted = crawl_result.extracted_content
                            if extracted and extracted.get('relevant', False):
                                item = {
                                    'url': crawl_result.url,
                                    'title': extracted.get('title', ''),
                                    'summary': extracted.get('summary', ''),
                                    'key_facts': extracted.get('key_facts', []),
                                    'timestamp': datetime.now().isoformat(),
                                    'source': source_name,
                                }
                                save_raw_data(item, source_name.replace(" ", "_").lower(), "web_scrape")
                    
                    print(f"  ✓ Completed LLM-filtered crawl of {seed}")
                    
                except Exception as e:
                    print(f"  ✗ Error during LLM crawl for {seed}: {e}")
                    continue
        
        return True

    try:
        return asyncio.run(_llm_crawl())
    except Exception as e:
        print(f"  Error in LLM crawl for {source_name}: {e}")
        return False


# Example usage function
def run_smart_data_acquisition():
    """Example of using smart crawling for supply chain data."""
    
    print("--- Starting Smart Data Acquisition ---\n")
    
    # Example 1: Port of Long Beach - smart crawl for supply chain news
    print("1. Smart crawl: Port of Long Beach Supply Chain News")
    polb_keywords = [
        'supply chain', 'cargo', 'shipping', 'container', 'logistics',
        'import', 'export', 'trade', 'disruption', 'delay', 'congestion'
    ]
    run_smart_crawl(
        seed_urls=["https://polb.com/news/"],
        source_name="PortOfLongBeach_SmartCrawl",
        keywords=polb_keywords,
        max_pages=50,
        max_depth=2,
        allowed_domains=["polb.com"]
    )
    time.sleep(5)
    
    # Example 2: Semiconductor news with smart filtering
    print("\n2. Smart crawl: Taiwan Semiconductor News")
    tsmc_keywords = [
        'TSMC', 'semiconductor', 'chip', 'taiwan', 'foundry',
        'fabrication', 'shortage', 'capacity', 'investment'
    ]
    run_smart_crawl(
        seed_urls=["https://www.taiwannews.com.tw/"],
        source_name="TaiwanSemiconductor_SmartCrawl",
        keywords=tsmc_keywords,
        max_pages=40,
        max_depth=2,
        allowed_domains=["taiwannews.com.tw"]
    )
    time.sleep(5)
    
    # Example 3: General supply chain news aggregator
    print("\n3. Smart crawl: Supply Chain News Sites")
    supply_chain_keywords = [
        'supply chain', 'logistics', 'manufacturing', 'disruption',
        'semiconductor', 'shortage', 'forecast', 'inventory'
    ]
    run_smart_crawl(
        seed_urls=[
            "https://www.supplychaindive.com/",
            "https://www.freightwaves.com/",
        ],
        source_name="SupplyChain_General",
        keywords=supply_chain_keywords,
        max_pages=100,
        max_depth=2,
        allowed_domains=["supplychaindive.com", "freightwaves.com"]
    )
    
    print("\n--- Smart Data Acquisition Complete ---")
    print("Check 'data/raw/web_scrape/' for results.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Smart web scraping for supply chain data')
    parser.add_argument('--example', action='store_true', help='Run example smart crawls')
    parser.add_argument('--keywords', nargs='+', help='Keywords for filtering (e.g., --keywords "supply chain" TSMC)')
    parser.add_argument('--seed-url', help='Starting URL for crawl')
    parser.add_argument('--source-name', help='Name for this data source')
    parser.add_argument('--max-pages', type=int, default=50, help='Maximum pages to crawl')
    parser.add_argument('--max-depth', type=int, default=2, help='Maximum link depth')
    
    args = parser.parse_args()
    
    if args.example:
        run_smart_data_acquisition()
    elif args.seed_url and args.keywords and args.source_name:
        run_smart_crawl(
            seed_urls=[args.seed_url],
            source_name=args.source_name,
            keywords=args.keywords,
            max_pages=args.max_pages,
            max_depth=args.max_depth
        )
    else:
        parser.print_help()
