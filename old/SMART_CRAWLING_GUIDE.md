# Smart Crawling Guide for Supply Chain Data

This guide explains how to use crawl4ai's intelligent crawling features to automatically find and extract relevant supply chain content.

## Overview

The `smart_acquisition.py` module provides two main approaches:

1. **Keyword-Based Smart Crawling** - Automatically follows links and filters content based on keywords
2. **LLM-Filtered Crawling** - Uses AI to intelligently extract only relevant information

## Quick Start

### 1. Run Example Smart Crawls

```bash
# Activate your venv
source venv311/bin/activate

# Run the example smart crawls
python src/smart_acquisition.py --example
```

### 2. Custom Smart Crawl

```bash
python src/smart_acquisition.py \
  --seed-url "https://polb.com/news/" \
  --source-name "PortNews" \
  --keywords "supply chain" "cargo" "shipping" \
  --max-pages 50 \
  --max-depth 3
```

## How Smart Crawling Works

### Keyword-Based Smart Crawling

The system automatically:

1. **Scores Links**: Ranks discovered links based on keyword matches in URL/text
2. **Follows Relevant Paths**: Prioritizes following links that contain your keywords
3. **Filters Content**: Only saves pages that contain relevant keywords
4. **Respects Limits**: Stops at max_pages or max_depth

#### Key Parameters:

```python
run_smart_crawl(
    seed_urls=["https://example.com/news"],
    source_name="MySource",
    keywords=['supply chain', 'semiconductor', 'TSMC'],
    max_pages=50,          # Stop after 50 pages
    max_depth=3,          # Don't go deeper than 3 links from seed
    allowed_domains=['example.com']  # Stay on this domain
)
```

### Deep Crawl Strategies

crawl4ai supports multiple strategies:

#### 1. BFS (Breadth-First Search) - Default
- Explores level by level
- Good for finding diverse content
- Better for news sites with category pages

```python
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy

strategy = BFSDeepCrawlStrategy(
    max_depth=3,
    max_pages=50,
    scoring_keywords=['supply chain', 'logistics'],
    allowed_domains=['example.com']
)
```

#### 2. DFS (Depth-First Search)
- Follows each branch deeply before backtracking
- Good for drilling into specific article series
- Better for blogs or sequential content

```python
from crawl4ai.deep_crawling import DFSDeepCrawlStrategy

strategy = DFSDeepCrawlStrategy(
    max_depth=5,
    max_pages=30,
    scoring_keywords=['TSMC', 'semiconductor']
)
```

### URL Matching & Filtering

Control which pages to crawl:

```python
# Match URLs containing specific patterns
config = CrawlerRunConfig(
    url=seed,
    url_matcher=[
        'news',           # Match URLs with 'news'
        'article',        # Match URLs with 'article'
        r'/\d{4}/\d{2}/', # Match date patterns (regex)
    ],
    match_mode=MatchMode.OR  # Match ANY pattern
)
```

### Content Filtering

Filter content at multiple levels:

```python
from crawl4ai.content_filter_strategy import (
    RelevantContentFilter,
    PruningContentFilter
)

config = CrawlerRunConfig(
    url=seed,
    # Text-based filtering
    word_count_threshold=100,  # Ignore short paragraphs
    
    # Keyword relevance
    url_matcher=['supply', 'chain', 'logistics'],
    
    # Advanced: Use content filters
    # (Note: These require specific crawl4ai versions)
)
```

## Real-World Examples

### Example 1: Port Supply Chain News

Crawl port news for supply chain disruptions:

```python
from src.smart_acquisition import run_smart_crawl

run_smart_crawl(
    seed_urls=["https://polb.com/news/"],
    source_name="PortNews_Disruptions",
    keywords=[
        'disruption', 'delay', 'congestion', 'backlog',
        'supply chain', 'cargo', 'container'
    ],
    max_pages=100,
    max_depth=2,
    allowed_domains=["polb.com"]
)
```

### Example 2: Semiconductor Industry

Track TSMC and semiconductor news:

```python
run_smart_crawl(
    seed_urls=[
        "https://www.taipeitimes.com/News/biz",
        "https://www.taiwannews.com.tw/en/news/4800000"
    ],
    source_name="Semiconductor_Industry",
    keywords=[
        'TSMC', 'semiconductor', 'chip shortage',
        'foundry', 'wafer', 'fab', 'capacity',
        'investment', 'expansion'
    ],
    max_pages=150,
    max_depth=3,
    allowed_domains=["taipeitimes.com", "taiwannews.com.tw"]
)
```

### Example 3: Multi-Site Aggregation

Crawl multiple supply chain news sites:

```python
supply_chain_sites = [
    "https://www.supplychaindive.com/",
    "https://www.freightwaves.com/news",
    "https://www.joc.com/",
]

keywords = [
    'supply chain', 'logistics', 'shipping',
    'forecast', 'outlook', 'trends',
    'semiconductor', 'automotive', 'retail'
]

for site in supply_chain_sites:
    run_smart_crawl(
        seed_urls=[site],
        source_name=f"SupplyChain_{site.split('//')[1].split('.')[1]}",
        keywords=keywords,
        max_pages=50,
        max_depth=2
    )
    time.sleep(10)  # Be polite between sites
```

## LLM-Based Crawling (Advanced)

For even smarter extraction, use an LLM to understand content:

### Setup

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="sk-your-key-here"
```

### Usage

```python
from src.smart_acquisition import run_llm_filtered_crawl

run_llm_filtered_crawl(
    seed_urls=["https://polb.com/news/"],
    source_name="Port_LLM_Filtered",
    llm_instruction="""
    Extract information about supply chain disruptions, delays, or 
    capacity issues. Include the following:
    - Main topic/event
    - Impact on supply chain
    - Expected duration
    - Companies/regions affected
    Mark as relevant only if it discusses actual disruptions or forecasts.
    """,
    max_pages=30,
    allowed_domains=["polb.com"]
)
```

The LLM will:
- Read each page's content
- Extract structured information
- Filter out irrelevant pages
- Return clean, structured JSON data

## Best Practices

### 1. Start Small
```python
# Test with low limits first
run_smart_crawl(..., max_pages=10, max_depth=1)
```

### 2. Use Specific Keywords
```python
# Good - specific
keywords = ['TSMC fab expansion', 'semiconductor shortage Q3']

# Less effective - too broad
keywords = ['news', 'business', 'technology']
```

### 3. Respect Rate Limits
```python
import time

for source in sources:
    run_smart_crawl(...)
    time.sleep(10)  # Wait between crawls
```

### 4. Monitor Results
```python
# Check what was saved
import json

with open('data/raw/web_scrape/latest_file.jsonl') as f:
    for line in f:
        item = json.loads(line)
        print(f"URL: {item['url']}")
        print(f"Matched keywords: {item.get('keywords_matched', [])}")
```

### 5. Iterate and Refine
1. Run small test crawl
2. Review results
3. Adjust keywords/depth
4. Scale up

## Performance Tips

1. **Use `headless=True`** for faster crawling (default in smart_acquisition.py)
2. **Set reasonable timeouts**: `page_timeout=30000` (30s)
3. **Use caching for development**: `cache_mode=CacheMode.ENABLED`
4. **Limit max_pages** to avoid overwhelming sites
5. **Use `allowed_domains`** to stay focused

## Troubleshooting

### No results saved?
- Check your keywords are in the content: `grep -i "keyword" data/raw/web_scrape/*.jsonl`
- Try broader keywords initially
- Increase `max_depth` (but carefully)

### Too many irrelevant pages?
- Use more specific keywords
- Reduce `max_depth`
- Add `url_matcher` patterns to filter URLs

### Crawl is slow?
- Reduce `max_pages`
- Use `screenshot=False`
- Set `only_text=True` if you don't need HTML

## Integration with Your Pipeline

After crawling, the data is saved as JSONL in `data/raw/web_scrape/`. Integrate with your processing:

```python
# In your data processing pipeline
import json
import glob

for jsonl_file in glob.glob('data/raw/web_scrape/*.jsonl'):
    with open(jsonl_file) as f:
        for line in f:
            item = json.loads(line)
            # Your processing here
            process_supply_chain_article(item)
```

## Next Steps

1. **Try the examples**: `python src/smart_acquisition.py --example`
2. **Customize for your sources**: Adjust keywords and domains
3. **Schedule regular crawls**: Use cron or a task scheduler
4. **Add new sources**: Expand the supply chain coverage
5. **Experiment with LLM filtering**: For highest quality extraction

## Additional Resources

- [crawl4ai Documentation](https://github.com/unclecode/crawl4ai)
- [Deep Crawl Strategies](https://crawl4ai.com/mkdocs/deep-crawling/)
- [Content Filtering](https://crawl4ai.com/mkdocs/content-filtering/)
