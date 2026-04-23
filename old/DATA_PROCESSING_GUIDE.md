# Data Processing Guide

Complete guide to processing your scraped supply chain data.

## Quick Start

```bash
# Activate environment
source venv311/bin/activate

# Process all scraped data
python src/data_processing.py
```

## What It Does

The processing pipeline:
1. ✅ **Loads** all JSONL files from `data/raw/web_scrape/`
2. ✅ **Cleans** text (removes extra whitespace, URLs, special chars)
3. ✅ **Extracts** keywords and counts occurrences
4. ✅ **Categorizes** content by topic
5. ✅ **Scores** relevance for prioritization
6. ✅ **Exports** to CSV and JSON in `data/processed/`

## Output Files

```
data/processed/
├── processed_data_YYYYMMDD_HHMMSS.csv    # Main processed data
├── processed_data_YYYYMMDD_HHMMSS.json   # JSON format
└── analysis_ready.csv                     # Clean format for ML/analysis
```

## Processing Features

### 1. Text Cleaning
- Removes extra whitespace
- Strips special characters
- Removes URLs and emails
- Normalizes formatting

### 2. Keyword Extraction
**Default Keywords:**
- supply chain, logistics, shipping, cargo, port
- semiconductor, chip, TSMC
- disruption, delay, shortage
- forecast, inventory, demand, capacity

**Customize keywords:**
```python
from src.data_processing import extract_keywords

keywords = extract_keywords(text, custom_keywords=[
    'Taiwan', 'China', 'trade war',
    'lithium', 'batteries', 'EV'
])
```

### 3. Auto-Categorization
Content is categorized into:
- **supply_chain**: Logistics, shipping topics
- **semiconductor**: Chip manufacturing, tech supply
- **disruption**: Delays, shortages, issues
- **forecast**: Predictions, outlooks
- **port_operations**: Port/cargo operations
- **general**: Uncategorized

### 4. Relevance Scoring
Score based on:
- Keyword count (×10 points per keyword)
- Text length (5-20 points)
- Has meaningful title (+10 points)

Higher scores = more relevant content

## Using Processed Data

### Load CSV into pandas
```python
import pandas as pd

df = pd.read_csv('data/processed/processed_data_20241010_120000.csv')

# View summary
print(df.info())
print(df.head())
```

### Filter by Category
```python
# Only semiconductor-related articles
semicon_df = df[df['categories'].str.contains('semiconductor')]

# Multiple categories
important_df = df[df['categories'].str.contains('disruption|forecast')]
```

### Filter by Relevance
```python
# High-relevance items only (score >= 50)
high_priority = df[df['relevance_score'] >= 50]

# Sort by relevance
top_items = df.sort_values('relevance_score', ascending=False).head(20)
```

### Analyze Keywords
```python
import json

# Get all keywords from first row
keywords = json.loads(df.iloc[0]['keywords_found'].replace("'", '"'))
print(keywords)

# Find articles mentioning specific keyword
port_articles = df[df['keywords_found'].str.contains('port')]
```

### Time Series Analysis
```python
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['date'] = df['timestamp'].dt.date

# Articles per day
daily_counts = df.groupby('date').size()

# Keywords over time
df.groupby('date')['keyword_count'].mean()
```

## Advanced Processing

### Custom Processing Pipeline
```python
from src.data_processing import load_jsonl_files, clean_text, extract_keywords

# Load raw data
raw_data = load_jsonl_files('data/raw/web_scrape')

# Process with custom keywords
custom_kw = ['lithium', 'cobalt', 'rare earth', 'mining']

for item in raw_data:
    text = clean_text(item['text'])
    keywords = extract_keywords(text, custom_keywords=custom_kw)
    
    if len(keywords) >= 2:  # At least 2 keyword matches
        print(f"Relevant: {item['url']}")
        print(f"Keywords: {keywords}")
```

### Filter During Processing
```python
from src.data_processing import process_data, filter_relevant_items

# Process all data
df = process_data()

# Filter for semiconductor + high relevance
semicon_high = filter_relevant_items(
    df, 
    min_relevance_score=40,
    categories=['semiconductor']
)

# Export filtered data
semicon_high.to_csv('data/processed/semiconductor_focus.csv', index=False)
```

### Export for Machine Learning
```python
from src.data_processing import export_for_analysis

# Creates clean CSV with key columns only
export_for_analysis(df, 'data/processed/ml_ready.csv')
```

## Example Workflows

### Workflow 1: Daily News Monitoring
```bash
# 1. Crawl latest news
python src/simple_smart_crawl.py \
  --url "https://polb.com/news/" \
  --name "DailyPortNews" \
  --keywords "port" "cargo" "shipping" \
  --max-pages 5

# 2. Process new data
python src/data_processing.py

# 3. Check high-priority items
python -c "
import pandas as pd
df = pd.read_csv('data/processed/analysis_ready.csv')
top = df.nlargest(5, 'relevance_score')
print(top[['title', 'relevance_score', 'categories']])
"
```

### Workflow 2: Topic-Specific Analysis
```python
# Focus on semiconductor supply chain
import pandas as pd

df = pd.read_csv('data/processed/processed_data_LATEST.csv')

# Filter: semiconductor + disruption topics, high relevance
semicon_issues = df[
    (df['categories'].str.contains('semiconductor')) &
    (df['categories'].str.contains('disruption')) &
    (df['relevance_score'] >= 30)
]

# Export for detailed review
semicon_issues.to_excel('semicon_disruptions.xlsx', index=False)
```

### Workflow 3: Keyword Trend Analysis
```python
import pandas as pd
from collections import Counter
import json

df = pd.read_csv('data/processed/processed_data_LATEST.csv')

# Aggregate all keywords
all_keywords = Counter()
for kw_str in df['keywords_found']:
    kw_dict = json.loads(kw_str.replace("'", '"'))
    all_keywords.update(kw_dict)

# Top 20 keywords
print("Top Keywords in Supply Chain News:")
for keyword, count in all_keywords.most_common(20):
    print(f"{keyword:20s}: {count:4d}")
```

## Troubleshooting

### No data processed?
Check if raw data exists:
```bash
ls -lh data/raw/web_scrape/
```

### Empty text fields?
The crawler may not have waited for JavaScript. See `CRAWLER_FIX_GUIDE.md`.

### KeyError in processing?
Some fields may be missing. The processor handles this gracefully but check your JSONL format.

### Memory issues with large datasets?
Process in batches:
```python
import glob
import pandas as pd

all_dfs = []
for file in glob.glob('data/raw/web_scrape/*.jsonl')[:10]:  # First 10 files
    # Process individual file
    pass
```

## Next Steps

1. **Schedule regular processing**: Run daily/weekly with cron
2. **Build visualizations**: Use matplotlib/seaborn for trends
3. **Add sentiment analysis**: Track positive/negative news
4. **Build forecasting models**: Use processed data for ML
5. **Create alerts**: Flag high-relevance disruption news

## Custom Keywords for Supply Chain

```python
# Semiconductor supply chain
SEMICON_KEYWORDS = [
    'TSMC', 'Samsung', 'Intel', 'chip shortage',
    'wafer', 'foundry', 'fab', 'semiconductor'
]

# Logistics & shipping
LOGISTICS_KEYWORDS = [
    'container', 'freight', 'shipping', 'logistics',
    'port', 'cargo', 'vessel', 'carrier'
]

# Geopolitical
GEOPOLITICAL_KEYWORDS = [
    'tariff', 'trade war', 'sanctions', 'export control',
    'China', 'Taiwan', 'US-China', 'geopolitical'
]

# Raw materials
MATERIALS_KEYWORDS = [
    'lithium', 'cobalt', 'rare earth', 'copper',
    'nickel', 'aluminum', 'steel', 'commodities'
]
```

Use these in your processing:
```python
from src.data_processing import process_data

# Add custom keywords to the processor
# Edit src/data_processing.py, line 52-57
```

---

**Need help?** Check other guides:
- `CRAWLER_FIX_GUIDE.md` - Crawling issues
- `SMART_CRAWLING_GUIDE.md` - Advanced crawling
- `QUICK_START_SMART_CRAWL.md` - Quick reference
