# 🤖 Auto-Crawling Relevant Topics - Summary

## What You Asked For
**"How do I make crawl4ai auto crawl relevant topics?"**

## Answer: 3 Ways to Auto-Crawl Relevant Content

### ✅ 1. Keyword-Based Smart Crawling (Easiest)
Uses keywords to automatically find and follow relevant links.

**Example:**
```bash
source venv311/bin/activate
python src/smart_acquisition.py \
  --seed-url "https://polb.com/news/" \
  --source-name "PortNews" \
  --keywords "supply chain" "cargo" "shipping" \
  --max-pages 30 \
  --max-depth 2
```

**How it works:**
- Crawls the seed URL
- Finds all links on the page
- Scores links based on keyword matches
- Follows the most relevant links
- Saves pages that contain your keywords

### ✅ 2. Deep Crawl Strategies (More Control)
Automatically discovers and follows links using intelligent strategies.

**Example:**
```python
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer

scorer = KeywordRelevanceScorer(keywords=['TSMC', 'semiconductor'])
strategy = BFSDeepCrawlStrategy(
    max_depth=3,
    max_pages=50,
    url_scorer=scorer
)
```

**Strategies available:**
- `BFSDeepCrawlStrategy` - Breadth-first (level by level)
- `DFSDeepCrawlStrategy` - Depth-first (follow branches deep)

### ✅ 3. LLM-Based Filtering (Most Intelligent)
Uses AI to understand and extract only truly relevant content.

**Example:**
```python
from crawl4ai.extraction_strategy import LLMExtractionStrategy

llm_strategy = LLMExtractionStrategy(
    provider="openai/gpt-4o-mini",
    instruction="Extract supply chain disruption information",
    schema={...}
)
```

## 📁 Files Created for You

1. **`src/smart_acquisition.py`** - Full-featured smart crawling
   - Keyword-based filtering
   - Deep crawl strategies  
   - Domain restrictions
   - URL scoring

2. **`src/simple_smart_crawl.py`** - Simplified learning example
   - Easy to understand
   - Shows core concepts
   - Good starting point

3. **`QUICK_START_SMART_CRAWL.md`** - Quick reference guide
   - Common patterns
   - Troubleshooting
   - Best practices

4. **`SMART_CRAWLING_GUIDE.md`** - Comprehensive documentation
   - Detailed API reference
   - Advanced techniques
   - Real-world examples

## 🚀 Quick Start

### Test it now:
```bash
source venv311/bin/activate

# Simple test with 5 pages
python src/smart_acquisition.py \
  --seed-url "https://polb.com/news/" \
  --source-name "Test" \
  --keywords "port" "cargo" \
  --max-pages 5 \
  --max-depth 1
```

### Run full examples:
```bash
python src/smart_acquisition.py --example
```

## 🎯 Key Concepts

### 1. **Keywords** = What to look for
```python
keywords = ['supply chain', 'TSMC', 'disruption']
```

### 2. **URL Matchers** = Which links to follow
```python
url_matcher = ['news', 'article', r'/\d{4}/']  # news, articles, dated URLs
```

### 3. **Scorers** = How to rank links
```python
scorer = KeywordRelevanceScorer(keywords=keywords)
```

### 4. **Filters** = What to exclude
```python
domain_filter = DomainFilter(allowed_domains=['example.com'])
```

## 📊 How It Finds Relevant Content

```
1. Start at seed URL
   ↓
2. Extract all links
   ↓
3. Score each link (keywords in URL/text)
   ↓
4. Filter by domain/patterns
   ↓
5. Follow highest-scoring links
   ↓
6. Check if page content matches keywords
   ↓
7. Save if relevant, repeat with new links
```

## 🔧 Configuration Examples

### For News Sites:
```python
run_smart_crawl(
    seed_urls=["https://news-site.com"],
    keywords=['supply chain', 'disruption'],
    max_pages=50,
    max_depth=2,
    allowed_domains=['news-site.com']
)
```

### For Multiple Sources:
```python
sources = [
    ("https://site1.com", ['keyword1', 'keyword2']),
    ("https://site2.com", ['keyword3', 'keyword4']),
]

for url, keywords in sources:
    run_smart_crawl(
        seed_urls=[url],
        source_name=url.split('//')[1].split('.')[0],
        keywords=keywords,
        max_pages=30
    )
```

## 💡 Tips for Best Results

1. **Start with broad keywords, refine based on results**
   ```python
   # First try:
   keywords = ['supply chain']
   
   # Then refine:
   keywords = ['supply chain disruption', 'port congestion', 'shipping delay']
   ```

2. **Use domain restrictions to stay focused**
   ```python
   allowed_domains=['polb.com', 'marad.dot.gov']
   ```

3. **Adjust depth vs. breadth**
   ```python
   # Broad coverage:
   max_depth=1, max_pages=100
   
   # Deep dive:
   max_depth=5, max_pages=30
   ```

4. **Monitor what's being saved**
   ```bash
   ls -lh data/raw/web_scrape/
   jq . data/raw/web_scrape/latest.jsonl | head -50
   ```

## 📈 Next Steps

1. **Test with your supply chain sources**
2. **Review saved data quality**
3. **Adjust keywords and filters**
4. **Scale up max_pages**
5. **Schedule regular crawls**

## 📚 Documentation

- **Quick Start**: `QUICK_START_SMART_CRAWL.md`
- **Full Guide**: `SMART_CRAWLING_GUIDE.md`
- **Code Examples**: `src/smart_acquisition.py`

## ✨ What This Gives You

Instead of manually:
- Clicking through news sites
- Copy-pasting articles
- Tracking which pages you've seen

You now have:
- Automated discovery of relevant content
- Intelligent link following
- Keyword-based filtering
- Structured data output
- Scalable crawling

**The crawler finds relevant supply chain content automatically!** 🎉
