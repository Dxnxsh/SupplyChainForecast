# Quick Start: Auto-Crawling Relevant Topics with crawl4ai

## TL;DR - Make crawl4ai Find Relevant Content Automatically

crawl4ai can automatically find and follow relevant links using **keywords**, **URL patterns**, and **deep crawl strategies**. Here's how:

### Method 1: Simple Keyword-Based Crawling (Recommended to Start)

```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
import asyncio

async def smart_crawl():
    keywords = ['supply chain', 'TSMC', 'semiconductor', 'shortage']
    
    async with AsyncWebCrawler() as crawler:
        config = CrawlerRunConfig(
            url="https://example.com/news",
            
            # KEY SETTINGS FOR AUTO-DISCOVERY:
            
            # 1. Match URLs containing these keywords
            url_matcher=keywords,
            match_mode="or",  # Match ANY keyword
            
            # 2. Score and prioritize links
            score_links=True,  # Automatically score links by relevance
            
            # 3. Extract main content only
            word_count_threshold=50,  # Skip short/irrelevant blocks
            
            verbose=True
        )
        
        result = await crawler.arun("https://example.com/news", config=config)
        
        for page in result:
            # Check if content is relevant
            text = page.html.lower()  # Use HTML since text extraction varies
            if any(kw.lower() in text for kw in keywords):
                print(f"Found relevant page: {page.url}")
                # Save it
                
asyncio.run(smart_crawl())
```

### Method 2: Deep Crawling (Follow Links Automatically)

This automatically follows links based on your criteria:

```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import FilterChain, DomainFilter
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
import asyncio

async def deep_smart_crawl():
    keywords = ['supply chain', 'logistics', 'disruption']
    
    # Create filters
    domain_filter = DomainFilter(allowed_domains=["example.com"])
    filter_chain = FilterChain(filters=[domain_filter])
    
    # Create scorer
    scorer = KeywordRelevanceScorer(keywords=keywords)
    
    # Create deep crawl strategy
    strategy = BFSDeepCrawlStrategy(
        max_depth=3,           # Follow links up to 3 levels deep
        max_pages=50,          # Stop after 50 pages
        filter_chain=filter_chain,
        url_scorer=scorer,
        score_threshold=0.1    # Only follow links with positive scores
    )
    
    async with AsyncWebCrawler() as crawler:
        config = CrawlerRunConfig(
            url="https://example.com/news",
            deep_crawl_strategy=strategy,
            verbose=True
        )
        
        result = await crawler.arun("https://example.com/news", config=config)
        
        for page in result:
            print(f"Crawled: {page.url}")

asyncio.run(deep_smart_crawl())
```

## Real Examples for Your Supply Chain Project

### Example 1: Port News Auto-Crawler

```bash
# Using the included smart_acquisition.py
source venv311/bin/activate

python src/smart_acquisition.py \
  --seed-url "https://polb.com/news/" \
  --source-name "PortNews" \
  --keywords "port" "cargo" "terminal" "delay" \
  --max-pages 30 \
  --max-depth 2
```

### Example 2: Semiconductor News

```python
# Custom script for TSMC/semiconductor news
from src.smart_acquisition import run_smart_crawl

run_smart_crawl(
    seed_urls=["https://www.taiwannews.com.tw/en/news/4800000"],
    source_name="SemiconductorNews",
    keywords=[
        'TSMC', 'semiconductor', 'chip',
        'fab', 'capacity', 'shortage'
    ],
    max_pages=50,
    max_depth=2,
    allowed_domains=["taiwannews.com.tw"]
)
```

### Example 3: Multi-Source Aggregator

```python
supply_chain_sources = [
    {
        "url": "https://www.supplychaindive.com/",
        "keywords": ["supply chain", "disruption", "forecast"],
        "domain": "supplychaindive.com"
    },
    {
        "url": "https://www.freightwaves.com/news",
        "keywords": ["freight", "shipping", "logistics"],
        "domain": "freightwaves.com"
    }
]

for source in supply_chain_sources:
    run_smart_crawl(
        seed_urls=[source["url"]],
        source_name=source["domain"].split('.')[0],
        keywords=source["keywords"],
        max_pages=40,
        max_depth=2,
        allowed_domains=[source["domain"]]
    )
    time.sleep(10)  # Be polite
```

## How It Works

### 1. **URL Scoring**
crawl4ai scores discovered links based on:
- Keywords in URL text
- Keywords in link anchor text
- URL patterns you specify

### 2. **Link Following**
The deep crawl strategy:
- Discovers all links on a page
- Filters by domain/patterns
- Scores each link
- Follows highest-scoring links first
- Stops at max_depth or max_pages

### 3. **Content Filtering**
Pages are saved if they:
- Match your URL patterns
- Contain your keywords
- Meet word count threshold
- Pass custom filters

## Key Configuration Options

### URL Matching
```python
# Match URLs containing any of these
url_matcher=['news', 'article', 'blog', 'press']

# Or use regex patterns
url_matcher=[r'/\d{4}/\d{2}/',  # Date patterns
             r'/news/',
             'supply-chain']
```

### Keyword Scoring
```python
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer

scorer = KeywordRelevanceScorer(
    keywords=['supply chain', 'TSMC'],
    url_weight=0.3,      # How much URL text matters
    anchor_weight=0.7    # How much link text matters
)
```

### Domain Filtering
```python
from crawl4ai.deep_crawling.filters import DomainFilter

# Only crawl these domains
filter = DomainFilter(allowed_domains=['example.com', 'news.example.com'])

# Or exclude domains
filter = DomainFilter(blocked_domains=['ads.example.com'])
```

## Troubleshooting

### Problem: No pages are saved

**Solution**: Check if your keywords are too specific. Try:
```python
# Instead of:
keywords = ['TSMC 3nm fab expansion Taiwan']  # Too specific

# Use:
keywords = ['TSMC', 'fab', 'expansion', 'Taiwan']  # Better
```

### Problem: Too many irrelevant pages

**Solution**: Use more restrictive filters:
```python
config = CrawlerRunConfig(
    # ... other settings ...
    url_matcher=['news', 'article'],  # Only news/article URLs
    word_count_threshold=200,         # Skip short pages
    score_threshold=0.5                # Higher relevance threshold
)
```

### Problem: Crawl is too slow

**Solution**: Reduce limits and use caching:
```python
config = CrawlerRunConfig(
    max_pages=20,              # Fewer pages
    max_depth=1,               # Shallower crawl
    cache_mode=CacheMode.ENABLED,  # Cache during development
    page_timeout=30000         # 30s timeout
)
```

## Best Practices

### 1. Start Small, Scale Up
```python
# First run: Test with limits
run_smart_crawl(..., max_pages=5, max_depth=1)

# Review results, then scale:
run_smart_crawl(..., max_pages=100, max_depth=3)
```

### 2. Use Specific Keywords
```python
# Generic (less effective):
keywords = ['news', 'business']

# Specific (more effective):
keywords = ['supply chain disruption', 'chip shortage', 'TSMC capacity']
```

### 3. Layer Your Filters
```python
# Multiple filters working together:
- Domain filter (stay on relevant sites)
- URL pattern filter (news/article URLs only)
- Keyword filter (content must mention topics)
- Word count filter (substantial content only)
```

### 4. Monitor and Iterate
```python
# After each run, check:
import json
with open('data/raw/web_scrape/latest.jsonl') as f:
    for line in f:
        item = json.loads(line)
        print(f"URL: {item['url']}")
        print(f"Keywords found: {item.get('keywords_matched', [])}")
        print("---")

# Adjust keywords/filters based on results
```

## Advanced: LLM-Based Filtering

For highest quality, use an LLM to understand content:

```python
from crawl4ai.extraction_strategy import LLMExtractionStrategy

# Set your API key
import os
os.environ['OPENAI_API_KEY'] = 'sk-...'

llm_strategy = LLMExtractionStrategy(
    provider="openai/gpt-4o-mini",
    instruction="""
    Extract information about supply chain disruptions.
    Include:
    - What caused the disruption
    - Which companies/regions affected
    - Expected impact and duration
    
    Only mark as relevant if it discusses actual or
    predicted supply chain issues.
    """,
    schema={
        "type": "object",
        "properties": {
            "relevant": {"type": "boolean"},
            "summary": {"type": "string"},
            "impact": {"type": "string"},
            "affected_parties": {"type": "array"}
        }
    }
)

config = CrawlerRunConfig(
    url=seed_url,
    extraction_strategy=llm_strategy
)
```

## Summary

**To make crawl4ai auto-crawl relevant topics:**

1. **Define keywords** - What you're looking for
2. **Set URL matchers** - What URLs to follow  
3. **Use deep crawl strategy** - Automatically discover and follow links
4. **Add filters** - Stay on relevant sites/content
5. **Score links** - Prioritize most relevant paths

Start with `smart_acquisition.py` and customize from there!

## Files to Use

- `src/smart_acquisition.py` - Full-featured smart crawling
- `src/simple_smart_crawl.py` - Simplified version to learn from
- See `SMART_CRAWLING_GUIDE.md` for detailed API reference

## Quick Commands

```bash
# Test with 5 pages
python src/smart_acquisition.py \
  --seed-url "https://example.com" \
  --source-name "Test" \
  --keywords "keyword1" "keyword2" \
  --max-pages 5

# Production run
python src/smart_acquisition.py --example
```
