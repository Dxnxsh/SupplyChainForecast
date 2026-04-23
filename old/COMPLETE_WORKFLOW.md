# Complete Supply Chain Data Pipeline Workflow

End-to-end guide for crawling, processing, and analyzing supply chain news data.

## 📋 Overview

Your complete data pipeline consists of 3 main stages:

```
1. DATA COLLECTION (Crawling)
   ↓
2. DATA PROCESSING (Cleaning & Analysis)
   ↓
3. DATA VISUALIZATION & INSIGHTS
```

---

## 🚀 Quick Start (3 Steps)

### Step 1: Crawl Data
```bash
# Activate environment
source venv311/bin/activate

# Run smart crawler
python src/simple_smart_crawl.py \
  --url "https://polb.com/news/" \
  --name "PortNews" \
  --keywords "port" "cargo" "shipping" "supply chain" \
  --max-pages 10
```

**Output:** Raw JSONL files in `data/raw/web_scrape/`

### Step 2: Process Data
```bash
# Clean, categorize, and score the data
python src/data_processing.py
```

**Output:** 
- `data/processed/processed_data_YYYYMMDD_HHMMSS.csv`
- `data/processed/processed_data_YYYYMMDD_HHMMSS.json`
- `data/processed/analysis_ready.csv`

### Step 3: Analyze & Visualize
```bash
# Generate insights and visualizations
python src/visualize_data.py
```

**Output:**
- Console output with charts and statistics
- `data/processed/insights_summary.txt`

---

## 📊 What You Get

### From Processing:
- ✅ **Cleaned text** (removed noise, normalized formatting)
- ✅ **Keyword extraction** (frequency counts for each term)
- ✅ **Auto-categorization** (supply_chain, semiconductor, port_operations, etc.)
- ✅ **Relevance scoring** (prioritize most important articles)
- ✅ **Date extraction** (mentioned dates in content)

### From Visualization:
- ✅ **Keyword trends** (most mentioned topics)
- ✅ **Category distribution** (content breakdown)
- ✅ **Source analysis** (which sources provide most data)
- ✅ **Relevance scores** (quality distribution)
- ✅ **Content length** (article size patterns)
- ✅ **Keyword co-occurrence** (related topics)
- ✅ **Top articles** (highest priority content)

---

## 🔄 Complete Daily Workflow

```bash
#!/bin/bash
# daily_pipeline.sh - Run this daily for fresh data

# 1. Crawl multiple sources
python src/simple_smart_crawl.py \
  --url "https://polb.com/news/" \
  --name "PortLB" \
  --keywords "port" "cargo" "shipping" \
  --max-pages 10

python src/simple_smart_crawl.py \
  --url "https://www.joc.com/maritime-news" \
  --name "JOC_Maritime" \
  --keywords "supply chain" "shipping" "container" \
  --max-pages 5

# 2. Process all new data
python src/data_processing.py

# 3. Generate insights
python src/visualize_data.py

# 4. Run analysis examples
python examples/analyze_data.py

echo "✅ Daily pipeline complete!"
```

Make it executable:
```bash
chmod +x daily_pipeline.sh
./daily_pipeline.sh
```

---

## 📁 Project Structure

```
SupplyChainForecast/
├── data/
│   ├── raw/
│   │   └── web_scrape/          # Raw crawled JSONL files
│   └── processed/                # Cleaned, analyzed CSV/JSON
│       ├── processed_data_*.csv
│       ├── analysis_ready.csv
│       └── insights_summary.txt
│
├── src/
│   ├── data_acquisition.py      # Core crawling logic
│   ├── simple_smart_crawl.py    # Easy-to-use crawler
│   ├── smart_acquisition.py     # Advanced crawling
│   ├── data_processing.py       # Processing pipeline
│   └── visualize_data.py        # Analytics & charts
│
├── examples/
│   └── analyze_data.py          # Analysis examples
│
└── Documentation/
    ├── DATA_PROCESSING_GUIDE.md
    ├── SMART_CRAWLING_GUIDE.md
    ├── CRAWLER_FIX_GUIDE.md
    └── COMPLETE_WORKFLOW.md (this file)
```

---

## 🎯 Use Cases

### 1. Daily News Monitoring
**Goal:** Track latest supply chain disruptions

```bash
# Morning: Crawl overnight news
python src/simple_smart_crawl.py \
  --url "https://polb.com/news/" \
  --name "DailyNews" \
  --keywords "disruption" "delay" "shortage" \
  --max-pages 5

# Process and check high-priority items
python src/data_processing.py
python -c "
import pandas as pd
df = pd.read_csv('data/processed/analysis_ready.csv')
urgent = df[df['relevance_score'] >= 500].nlargest(3, 'relevance_score')
print('🚨 HIGH PRIORITY TODAY:')
print(urgent[['url', 'relevance_score', 'categories']])
"
```

### 2. Competitor Intelligence
**Goal:** Monitor specific companies/ports

```bash
# Crawl with company-specific keywords
python src/simple_smart_crawl.py \
  --url "https://industry-site.com/news/" \
  --name "CompetitorNews" \
  --keywords "CompanyA" "CompanyB" "market share" \
  --max-pages 20

# Filter results
python examples/analyze_data.py
```

### 3. Trend Analysis
**Goal:** Identify emerging topics over time

```python
import pandas as pd
import glob

# Load all historical processed data
all_data = []
for file in glob.glob('data/processed/processed_data_*.csv'):
    df = pd.read_csv(file)
    all_data.append(df)

combined = pd.concat(all_data)
combined['timestamp'] = pd.to_datetime(combined['timestamp'])
combined['week'] = combined['timestamp'].dt.to_period('W')

# Keyword trends over time
weekly_keywords = combined.groupby('week')['keyword_count'].mean()
print("Keyword density over time:")
print(weekly_keywords)
```

### 4. Export for Reporting
**Goal:** Share insights with team

```python
import pandas as pd

df = pd.read_csv('data/processed/analysis_ready.csv')

# Create executive summary
summary = df.groupby('categories').agg({
    'relevance_score': 'mean',
    'url': 'count'
}).round(1)

summary.columns = ['Avg Relevance', 'Article Count']
summary.to_excel('weekly_report.xlsx')
```

---

## 🔧 Customization

### Add Custom Keywords

Edit `src/data_processing.py`, line ~48:

```python
def extract_keywords(text, custom_keywords=None):
    if custom_keywords is None:
        custom_keywords = [
            # Supply chain
            'supply chain', 'logistics', 'shipping', 'cargo', 'port',
            
            # Your custom keywords
            'lithium', 'batteries', 'EV',
            'TSMC', 'Samsung', 'Intel',
            'China', 'Taiwan', 'trade war',
            
            # Add more...
        ]
```

### Add Custom Categories

Edit `src/data_processing.py`, line ~85:

```python
def categorize_content(text, keywords_found):
    categories = []
    
    # Existing categories...
    
    # Add your custom categories
    if any(k in keywords_found for k in ['lithium', 'cobalt', 'batteries']):
        categories.append('raw_materials')
    
    if any(k in keywords_found for k in ['AI', 'automation', 'robotics']):
        categories.append('technology')
    
    return categories if categories else ['general']
```

### Change Relevance Scoring

Edit `src/data_processing.py`, line ~102:

```python
def calculate_relevance_score(item):
    score = 0
    
    # Customize weights
    keywords_found = item.get('keywords_found', [])
    score += len(keywords_found) * 15  # Increase keyword weight
    
    # Add custom scoring factors
    if 'semiconductor' in str(item.get('categories', [])):
        score += 50  # Boost semiconductor content
    
    return score
```

---

## 📈 Advanced Analytics

### Export to pandas for ML

```python
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

# Load processed data
df = pd.read_csv('data/processed/analysis_ready.csv')

# Create TF-IDF features from text
vectorizer = TfidfVectorizer(max_features=100)
tfidf_features = vectorizer.fit_transform(df['text'])

# Now ready for ML models (clustering, classification, etc.)
```

### Time Series Forecasting

```python
import pandas as pd

df = pd.read_csv('data/processed/analysis_ready.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['date'] = df['timestamp'].dt.date

# Daily keyword counts (proxy for supply chain activity)
daily_keywords = df.groupby('date')['keyword_count'].sum()

# Use for forecasting (ARIMA, Prophet, etc.)
```

### Sentiment Analysis

```bash
# Install sentiment library
pip install textblob

# Then in Python:
```

```python
from textblob import TextBlob
import pandas as pd

df = pd.read_csv('data/processed/analysis_ready.csv')

# Add sentiment scores
df['sentiment'] = df['text'].apply(
    lambda x: TextBlob(str(x)[:5000]).sentiment.polarity
)

# Identify negative news (potential disruptions)
negative_news = df[df['sentiment'] < -0.1].nlargest(10, 'relevance_score')
print("🚨 Most relevant negative news:")
print(negative_news[['url', 'sentiment', 'relevance_score']])
```

---

## 🔄 Automation

### Schedule with cron (macOS/Linux)

```bash
# Edit crontab
crontab -e

# Add daily run at 6 AM
0 6 * * * cd /Users/meordanish/Desktop/Projects/SupplyChainForecast && source venv311/bin/activate && ./daily_pipeline.sh >> logs/daily_$(date +\%Y\%m\%d).log 2>&1
```

### Create logs directory

```bash
mkdir -p logs
```

---

## 🐛 Troubleshooting

### No data collected?
```bash
# Check if crawler is working
ls -lh data/raw/web_scrape/

# If empty, check crawler with verbose output
python src/simple_smart_crawl.py --url "URL" --name "Test" --keywords "test" --max-pages 1
```

### Processing errors?
```bash
# Check raw data format
head -n 1 data/raw/web_scrape/*.jsonl | python -m json.tool
```

### Empty text in processed data?
See `CRAWLER_FIX_GUIDE.md` - likely JavaScript rendering issue.

---

## 📊 Sample Output

### Processing Summary
```
Total items processed: 8
Average text length: 86,322 characters
Average relevance score: 565.0

Top Keywords:
  port: 827
  cargo: 20
  supply chain: 13
  
Categories Distribution:
  port_operations: 8 (100.0%)
  supply_chain: 5 (62.5%)
```

### High-Priority Alert
```
🚨 HIGH PRIORITY ARTICLES (score >= 500)

Score: 1640 | https://polb.com/news/archive/
  Keywords: supply chain(1), cargo(8), port(315)
  Categories: supply_chain, port_operations
```

---

## 🎓 Learning Path

1. **Week 1:** Run basic crawls and understand raw data
2. **Week 2:** Customize keywords and categories for your domain
3. **Week 3:** Build automated daily pipeline
4. **Week 4:** Add custom analytics and reporting
5. **Week 5:** Integrate with ML models or dashboards

---

## 📚 Additional Resources

- **Crawling:** See `SMART_CRAWLING_GUIDE.md`
- **Processing:** See `DATA_PROCESSING_GUIDE.md`
- **Troubleshooting:** See `CRAWLER_FIX_GUIDE.md`
- **Quick Reference:** See `QUICK_START_SMART_CRAWL.md`

---

## ✅ Success Checklist

- [ ] Can successfully crawl data from target sources
- [ ] Raw JSONL files contain actual text content (not empty)
- [ ] Processing pipeline runs without errors
- [ ] Processed CSV has meaningful keyword counts
- [ ] Visualization shows clear insights
- [ ] Can filter and export relevant subsets
- [ ] Understand how to customize for your needs
- [ ] Set up automated daily runs (optional)

---

## 🚀 Next Steps

1. **Expand sources:** Add more industry news sites
2. **Refine keywords:** Focus on your specific supply chain segment
3. **Build dashboard:** Use processed data with PowerBI/Tableau
4. **Add forecasting:** Use historical data for predictions
5. **Create alerts:** Email/Slack notifications for high-priority news
6. **Share insights:** Generate automated weekly reports

---

**Questions?** Check the guide files or review the inline code comments in each script.

**Happy data hunting! 📊🚢**
