# src/simple_smart_crawl.py
"""
Simplified smart crawling example - easier to understand and customize.
This shows the core concepts without complex deep crawl strategies.
"""

try:
    from src.data_acquisition import save_raw_data
except ModuleNotFoundError:
    from data_acquisition import save_raw_data

import asyncio
from datetime import datetime


def simple_smart_crawl(seed_url, source_name, keywords, max_pages=10):
    """
    Simple keyword-based crawling that:
    1. Fetches a page
    2. Checks if it contains your keywords
    3. Saves it if relevant
    4. Finds and follows links that might be relevant
    
    Args:
        seed_url: Starting URL
        source_name: Name for the data source
        keywords: List of keywords to look for
        max_pages: Maximum pages to crawl
    """
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
        from bs4 import BeautifulSoup
        import re
    except ImportError as e:
        print(f"Import error: {e}")
        print("Install required packages: pip install crawl4ai beautifulsoup4")
        return False

    async def _crawl():
        visited = set()
        to_visit = [seed_url]
        pages_saved = 0
        
        async with AsyncWebCrawler() as crawler:
            while to_visit and len(visited) < max_pages:
                current_url = to_visit.pop(0)
                
                if current_url in visited:
                    continue
                    
                visited.add(current_url)
                print(f"\n📄 Crawling: {current_url}")
                
                try:
                    # Fetch the page
                    config = CrawlerRunConfig(
                        url=current_url,
                        cache_mode=CacheMode.BYPASS,
                        verbose=False,
                        page_timeout=30000,
                        # CRITICAL: Wait for JavaScript to load
                        wait_until="networkidle",
                        delay_before_return_html=2.0,
                    )
                    
                    result = await crawler.arun(current_url, config=config)
                    
                    for crawl_result in result:
                        html = getattr(crawl_result, 'html', '')
                        
                        # Extract text from HTML using BeautifulSoup
                        soup = BeautifulSoup(html, 'html.parser')
                        text = soup.get_text(separator=' ', strip=True).lower()
                        
                        # Check if page contains any keywords
                        keyword_matches = [kw for kw in keywords if kw.lower() in text]
                        
                        if keyword_matches:
                            # This page is relevant! Save it
                            item = {
                                'url': current_url,
                                'title': getattr(crawl_result, 'metadata', {}).get('title', ''),
                                'text': soup.get_text(separator=' ', strip=True),  # Full text
                                'html': html[:5000],  # Save first 5000 chars of HTML
                                'keywords_found': keyword_matches,
                                'timestamp': datetime.now().isoformat(),
                                'source': source_name,
                            }
                            save_raw_data(item, source_name.replace(" ", "_").lower(), "web_scrape")
                            pages_saved += 1
                            print(f"  ✅ Saved! (keywords found: {', '.join(keyword_matches)})")
                            
                            # Extract links from this relevant page
                            soup = BeautifulSoup(html, 'html.parser')
                            for link in soup.find_all('a', href=True):
                                href = link['href']
                                
                                # Make absolute URL
                                if href.startswith('/'):
                                    from urllib.parse import urljoin
                                    href = urljoin(current_url, href)
                                
                                # Check if link text or URL contains keywords
                                link_text = link.get_text().lower()
                                link_score = sum(1 for kw in keywords if kw.lower() in link_text or kw.lower() in href.lower())
                                
                                if link_score > 0 and href not in visited and href not in to_visit:
                                    to_visit.append(href)
                                    print(f"  🔗 Found relevant link: {href[:80]}...")
                        else:
                            print(f"  ⏭️  Skipped (no keywords found)")
                
                except Exception as e:
                    print(f"  ❌ Error crawling {current_url}: {e}")
                    continue
        
        print(f"\n✅ Crawl complete! Saved {pages_saved} relevant pages from {len(visited)} visited")
        return True
    
    try:
        return asyncio.run(_crawl())
    except Exception as e:
        print(f"Error in crawl: {e}")
        return False


# Example usage
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Simple smart crawling')
    parser.add_argument('--url', required=True, help='Starting URL')
    parser.add_argument('--name', required=True, help='Source name')
    parser.add_argument('--keywords', nargs='+', required=True, help='Keywords to search for')
    parser.add_argument('--max-pages', type=int, default=10, help='Max pages to crawl')
    
    args = parser.parse_args()
    
    print(f"""
🚀 Starting Smart Crawl
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Seed URL:    {args.url}
Source:      {args.name}
Keywords:    {', '.join(args.keywords)}
Max Pages:   {args.max_pages}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
    
    simple_smart_crawl(
        seed_url=args.url,
        source_name=args.name,
        keywords=args.keywords,
        max_pages=args.max_pages
    )
