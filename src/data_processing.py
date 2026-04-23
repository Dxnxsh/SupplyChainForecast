# src/data_processing.py
"""
Data processing pipeline for supply chain news data.
Cleans, normalizes, and prepares scraped data for analysis.
"""

import json
import glob
import pandas as pd
from datetime import datetime
from pathlib import Path
import re
from collections import Counter


def load_jsonl_files(directory='data/raw/web_scrape'):
    """Load all JSONL files from the directory."""
    files = glob.glob(f'{directory}/*.jsonl')
    data = []
    
    for file in files:
        with open(file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    item['source_file'] = Path(file).name
                    data.append(item)
                except json.JSONDecodeError as e:
                    print(f"Error reading {file}: {e}")
                    continue
    
    return data


def clean_text(text):
    """Clean and normalize text content."""
    if not text:
        return ""
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove special characters but keep punctuation
    text = re.sub(r'[^\w\s.,!?;:\-\'\"()]', '', text)
    
    # Remove URLs
    text = re.sub(r'http[s]?://\S+', '', text)
    
    # Remove email addresses
    text = re.sub(r'\S+@\S+', '', text)
    
    return text.strip()


def extract_keywords(text, custom_keywords=None):
    """Extract and count keywords from text."""
    if custom_keywords is None:
        custom_keywords = [
            'supply chain', 'logistics', 'shipping', 'cargo', 'port',
            'semiconductor', 'chip', 'TSMC', 'disruption', 'delay',
            'shortage', 'forecast', 'inventory', 'demand', 'capacity'
        ]
    
    text_lower = text.lower()
    found_keywords = {}
    
    for keyword in custom_keywords:
        count = text_lower.count(keyword.lower())
        if count > 0:
            found_keywords[keyword] = count
    
    return found_keywords


def extract_dates(text):
    """Extract dates from text."""
    # Common date patterns
    date_patterns = [
        r'\b\d{4}-\d{2}-\d{2}\b',  # 2024-01-15
        r'\b\d{1,2}/\d{1,2}/\d{4}\b',  # 01/15/2024
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b',  # January 15, 2024
    ]
    
    dates = []
    for pattern in date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        dates.extend(matches)
    
    return dates


def categorize_content(text, keywords_found):
    """Categorize content based on keywords and topics."""
    categories = []
    
    # Supply chain topics
    if any(k in keywords_found for k in ['supply chain', 'logistics', 'shipping']):
        categories.append('supply_chain')
    
    # Semiconductor topics
    if any(k in keywords_found for k in ['semiconductor', 'chip', 'TSMC']):
        categories.append('semiconductor')
    
    # Disruption/Issues
    if any(k in keywords_found for k in ['disruption', 'delay', 'shortage']):
        categories.append('disruption')
    
    # Forecasting/Planning
    if any(k in keywords_found for k in ['forecast', 'outlook', 'predict']):
        categories.append('forecast')
    
    # Port operations
    if any(k in keywords_found for k in ['port', 'cargo', 'container']):
        categories.append('port_operations')
    
    return categories if categories else ['general']


def calculate_relevance_score(item):
    """Calculate relevance score for the article."""
    score = 0
    
    # Keywords weight
    keywords_found = item.get('keywords_found', [])
    if isinstance(keywords_found, list):
        score += len(keywords_found) * 10
    elif isinstance(keywords_found, dict):
        score += sum(keywords_found.values()) * 5
    
    # Text length (more content = potentially more relevant)
    text_length = len(item.get('text', ''))
    if text_length > 5000:
        score += 20
    elif text_length > 2000:
        score += 10
    elif text_length > 500:
        score += 5
    
    # Has title
    if item.get('title') and len(item.get('title', '')) > 10:
        score += 10
    
    return score


def process_data(input_dir='data/raw/web_scrape', output_dir='data/processed'):
    """Main processing pipeline."""
    print("Loading raw data...")
    raw_data = load_jsonl_files(input_dir)
    print(f"Loaded {len(raw_data)} items")
    
    if not raw_data:
        print("No data to process!")
        return
    
    print("\nProcessing data...")
    processed_items = []
    
    for item in raw_data:
        # Clean text
        text = item.get('text', '')
        cleaned_text = clean_text(text)
        
        # Skip if no meaningful content
        if len(cleaned_text) < 100:
            continue
        
        # Extract keywords
        keywords_found = extract_keywords(cleaned_text)
        
        # Extract dates
        dates = extract_dates(cleaned_text)
        
        # Categorize
        categories = categorize_content(cleaned_text, keywords_found)
        
        # Calculate relevance
        item['keywords_found'] = keywords_found
        relevance_score = calculate_relevance_score(item)
        
        processed_item = {
            'url': item.get('url'),
            'title': item.get('title', ''),
            'text': cleaned_text,
            'text_length': len(cleaned_text),
            'source': item.get('source', ''),
            'source_file': item.get('source_file', ''),
            'timestamp': item.get('timestamp', datetime.now().isoformat()),
            'keywords_found': keywords_found,
            'keyword_count': len(keywords_found),
            'dates_mentioned': dates,
            'categories': categories,
            'relevance_score': relevance_score,
        }
        
        processed_items.append(processed_item)
    
    print(f"Processed {len(processed_items)} items")
    
    # Convert to DataFrame
    df = pd.DataFrame(processed_items)
    
    # Save processed data
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Save as CSV
    csv_path = f"{output_dir}/processed_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(csv_path, index=False)
    print(f"\n✅ Saved processed data to: {csv_path}")
    
    # Save as JSON
    json_path = f"{output_dir}/processed_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    df.to_json(json_path, orient='records', indent=2)
    print(f"✅ Saved processed data to: {json_path}")
    
    # Generate summary statistics
    print("\n" + "="*60)
    print("PROCESSING SUMMARY")
    print("="*60)
    
    print(f"\nTotal items processed: {len(df)}")
    print(f"Average text length: {df['text_length'].mean():.0f} characters")
    print(f"Average relevance score: {df['relevance_score'].mean():.1f}")
    
    print("\nTop Keywords:")
    all_keywords = {}
    for kw_dict in df['keywords_found']:
        for k, v in kw_dict.items():
            all_keywords[k] = all_keywords.get(k, 0) + v
    for keyword, count in sorted(all_keywords.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {keyword}: {count}")
    
    print("\nCategories Distribution:")
    all_categories = []
    for cats in df['categories']:
        all_categories.extend(cats)
    category_counts = Counter(all_categories)
    for cat, count in category_counts.most_common():
        print(f"  {cat}: {count}")
    
    print("\nTop Sources:")
    source_counts = df['source'].value_counts().head(5)
    for source, count in source_counts.items():
        print(f"  {source}: {count}")
    
    print("\n" + "="*60)
    
    return df


def filter_relevant_items(df, min_relevance_score=20, categories=None):
    """Filter DataFrame for most relevant items."""
    filtered = df[df['relevance_score'] >= min_relevance_score].copy()
    
    if categories:
        filtered = filtered[filtered['categories'].apply(
            lambda x: any(cat in x for cat in categories)
        )]
    
    return filtered.sort_values('relevance_score', ascending=False)


def export_for_analysis(df, output_path='data/processed/analysis_ready.csv'):
    """Export data in format ready for ML/analysis."""
    # Select key columns for analysis
    analysis_df = df[[
        'url', 'title', 'text', 'source', 'timestamp',
        'keyword_count', 'relevance_score', 'categories'
    ]].copy()
    
    # Convert categories list to string
    analysis_df['categories'] = analysis_df['categories'].apply(lambda x: ','.join(x))
    
    # Save
    analysis_df.to_csv(output_path, index=False)
    print(f"✅ Exported analysis-ready data to: {output_path}")
    
    return analysis_df


if __name__ == "__main__":
    # Process all data
    df = process_data()
    
    if df is not None:
        # Filter high-relevance items
        print("\n" + "="*60)
        print("HIGH RELEVANCE ITEMS (score >= 30)")
        print("="*60)
        high_rel = filter_relevant_items(df, min_relevance_score=30)
        print(f"\nFound {len(high_rel)} high-relevance items")
        
        if len(high_rel) > 0:
            print("\nTop 5 by relevance:")
            for idx, row in high_rel.head(5).iterrows():
                print(f"\n{row['relevance_score']:.0f} - {row['title'][:80]}...")
                print(f"  URL: {row['url']}")
                print(f"  Categories: {', '.join(row['categories'])}")
                print(f"  Keywords: {', '.join(list(row['keywords_found'].keys())[:5])}")
        
        # Export for analysis
        export_for_analysis(df)
