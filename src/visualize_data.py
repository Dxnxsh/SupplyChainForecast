# src/visualize_data.py
"""
Visualization tools for processed supply chain data.
Creates charts and insights from your scraped news.
"""

import pandas as pd
import json
from pathlib import Path
from collections import Counter
import glob


def load_latest_processed_data(directory='data/processed'):
    """Load the most recent processed data file."""
    csv_files = glob.glob(f'{directory}/processed_data_*.csv')
    if not csv_files:
        print("❌ No processed data found. Run data_processing.py first!")
        return None
    
    latest_file = max(csv_files, key=lambda x: Path(x).stat().st_mtime)
    print(f"Loading: {latest_file}")
    return pd.read_csv(latest_file)


def analyze_keyword_trends(df):
    """Analyze keyword frequency and trends."""
    print("\n" + "="*70)
    print("KEYWORD ANALYSIS")
    print("="*70)
    
    # Aggregate all keywords
    all_keywords = Counter()
    for kw_str in df['keywords_found']:
        try:
            # Handle different formats
            if isinstance(kw_str, str):
                kw_dict = eval(kw_str)  # Convert string dict to actual dict
            else:
                kw_dict = kw_str
            
            for k, v in kw_dict.items():
                all_keywords[k] += v
        except:
            continue
    
    print(f"\nTotal unique keywords found: {len(all_keywords)}")
    print("\nTop 15 Keywords by Frequency:")
    print("-" * 50)
    for keyword, count in all_keywords.most_common(15):
        bar_length = int(count / max(all_keywords.values()) * 40)
        bar = "█" * bar_length
        print(f"{keyword:20s} | {bar} {count}")


def analyze_categories(df):
    """Analyze content categories."""
    print("\n" + "="*70)
    print("CATEGORY ANALYSIS")
    print("="*70)
    
    # Extract all categories
    all_categories = []
    for cats in df['categories']:
        if isinstance(cats, str):
            all_categories.extend(eval(cats))
        else:
            all_categories.extend(cats)
    
    category_counts = Counter(all_categories)
    
    print(f"\nTotal articles: {len(df)}")
    print("\nCategory Distribution:")
    print("-" * 50)
    for cat, count in category_counts.most_common():
        percentage = (count / len(df)) * 100
        bar_length = int(percentage / 100 * 40)
        bar = "█" * bar_length
        print(f"{cat:20s} | {bar} {count} ({percentage:.1f}%)")


def analyze_sources(df):
    """Analyze data sources."""
    print("\n" + "="*70)
    print("SOURCE ANALYSIS")
    print("="*70)
    
    source_counts = df['source'].value_counts()
    
    print(f"\nTotal sources: {len(source_counts)}")
    print("\nArticles per Source:")
    print("-" * 50)
    for source, count in source_counts.items():
        percentage = (count / len(df)) * 100
        bar_length = int(percentage / 100 * 40)
        bar = "█" * bar_length
        print(f"{source[:30]:30s} | {bar} {count} ({percentage:.1f}%)")


def analyze_relevance(df):
    """Analyze relevance scores."""
    print("\n" + "="*70)
    print("RELEVANCE SCORE ANALYSIS")
    print("="*70)
    
    print(f"\nAverage relevance: {df['relevance_score'].mean():.1f}")
    print(f"Median relevance: {df['relevance_score'].median():.1f}")
    print(f"Max relevance: {df['relevance_score'].max():.0f}")
    print(f"Min relevance: {df['relevance_score'].min():.0f}")
    
    # Score distribution
    print("\nRelevance Score Distribution:")
    print("-" * 50)
    bins = [(0, 20, 'Low'), (20, 50, 'Medium'), (50, 100, 'High'), (100, float('inf'), 'Very High')]
    
    for min_score, max_score, label in bins:
        count = len(df[(df['relevance_score'] >= min_score) & (df['relevance_score'] < max_score)])
        percentage = (count / len(df)) * 100
        bar_length = int(percentage / 100 * 40)
        bar = "█" * bar_length
        max_str = '∞' if max_score == float('inf') else str(int(max_score))
        print(f"{label:15s} ({min_score:3d}-{max_str:>3s}) | {bar} {count} ({percentage:.1f}%)")


def show_top_articles(df, n=10):
    """Display top articles by relevance."""
    print("\n" + "="*70)
    print(f"TOP {n} ARTICLES BY RELEVANCE")
    print("="*70)
    
    top_articles = df.nlargest(n, 'relevance_score')
    
    for idx, (i, row) in enumerate(top_articles.iterrows(), 1):
        print(f"\n{idx}. Score: {row['relevance_score']:.0f} | {row['source']}")
        title = str(row['title']) if pd.notna(row['title']) else 'No title'
        print(f"   Title: {title[:80]}...")
        print(f"   URL: {row['url']}")
        
        # Show keywords
        try:
            keywords = eval(row['keywords_found']) if isinstance(row['keywords_found'], str) else row['keywords_found']
            kw_str = ', '.join([f"{k}({v})" for k, v in list(keywords.items())[:5]])
            print(f"   Keywords: {kw_str}")
        except:
            pass
        
        # Show categories
        try:
            cats = eval(row['categories']) if isinstance(row['categories'], str) else row['categories']
            print(f"   Categories: {', '.join(cats)}")
        except:
            pass


def content_length_analysis(df):
    """Analyze content length distribution."""
    print("\n" + "="*70)
    print("CONTENT LENGTH ANALYSIS")
    print("="*70)
    
    print(f"\nAverage text length: {df['text_length'].mean():.0f} characters")
    print(f"Median text length: {df['text_length'].median():.0f} characters")
    print(f"Longest article: {df['text_length'].max():.0f} characters")
    print(f"Shortest article: {df['text_length'].min():.0f} characters")
    
    print("\nLength Distribution:")
    print("-" * 50)
    bins = [
        (0, 1000, 'Very Short'),
        (1000, 5000, 'Short'),
        (5000, 10000, 'Medium'),
        (10000, 50000, 'Long'),
        (50000, float('inf'), 'Very Long')
    ]
    
    for min_len, max_len, label in bins:
        count = len(df[(df['text_length'] >= min_len) & (df['text_length'] < max_len)])
        if count > 0:
            percentage = (count / len(df)) * 100
            avg_in_range = df[(df['text_length'] >= min_len) & (df['text_length'] < max_len)]['text_length'].mean()
            bar_length = int(percentage / 100 * 40)
            bar = "█" * bar_length
            print(f"{label:12s} | {bar} {count} ({percentage:.1f}%) avg: {avg_in_range:.0f} chars")


def keyword_co_occurrence(df):
    """Find keywords that appear together."""
    print("\n" + "="*70)
    print("KEYWORD CO-OCCURRENCE")
    print("="*70)
    
    # Build co-occurrence matrix
    co_occurrence = Counter()
    
    for kw_str in df['keywords_found']:
        try:
            keywords = eval(kw_str) if isinstance(kw_str, str) else kw_str
            kw_list = list(keywords.keys())
            
            # Find all pairs
            for i, kw1 in enumerate(kw_list):
                for kw2 in kw_list[i+1:]:
                    pair = tuple(sorted([kw1, kw2]))
                    co_occurrence[pair] += 1
        except:
            continue
    
    print("\nTop 10 Keyword Pairs (frequently appear together):")
    print("-" * 50)
    for (kw1, kw2), count in co_occurrence.most_common(10):
        print(f"{kw1} + {kw2}: {count} articles")


def export_insights(df, output_file='data/processed/insights_summary.txt'):
    """Export text summary of insights."""
    import sys
    from io import StringIO
    
    # Capture print output
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()
    
    # Run all analyses
    print("SUPPLY CHAIN DATA INSIGHTS REPORT")
    print("="*70)
    print(f"Generated: {pd.Timestamp.now()}")
    print(f"Total Articles Analyzed: {len(df)}")
    
    analyze_keyword_trends(df)
    analyze_categories(df)
    analyze_sources(df)
    analyze_relevance(df)
    content_length_analysis(df)
    keyword_co_occurrence(df)
    show_top_articles(df, n=5)
    
    # Get the output
    report = captured_output.getvalue()
    sys.stdout = old_stdout
    
    # Save to file
    with open(output_file, 'w') as f:
        f.write(report)
    
    print(f"\n✅ Insights report saved to: {output_file}")
    
    # Also print to console
    print("\n" + report)


def main():
    """Run all visualizations."""
    df = load_latest_processed_data()
    
    if df is None:
        return
    
    print(f"\n📊 Analyzing {len(df)} articles...")
    
    # Run all analyses
    analyze_keyword_trends(df)
    analyze_categories(df)
    analyze_sources(df)
    analyze_relevance(df)
    content_length_analysis(df)
    keyword_co_occurrence(df)
    show_top_articles(df, n=5)
    
    # Export summary
    print("\n" + "="*70)
    export_insights(df)


if __name__ == "__main__":
    main()
