#!/usr/bin/env python3
"""
Quick analysis examples for processed supply chain data.
Run this to see practical examples of data analysis.
"""

import pandas as pd
import glob
from pathlib import Path


def load_data():
    """Load the latest processed data."""
    csv_files = glob.glob('data/processed/processed_data_*.csv')
    if not csv_files:
        print("❌ No data found. Run: python src/data_processing.py")
        return None
    
    latest = max(csv_files, key=lambda x: Path(x).stat().st_mtime)
    df = pd.read_csv(latest)
    print(f"✅ Loaded {len(df)} articles from {Path(latest).name}\n")
    return df


def example_1_filter_by_keyword(df):
    """Find articles mentioning specific keywords."""
    print("="*70)
    print("EXAMPLE 1: Find articles about 'supply chain' or 'disruption'")
    print("="*70)
    
    # Filter for articles with these keywords
    supply_chain = df[df['keywords_found'].str.contains('supply chain', na=False)]
    
    print(f"\nFound {len(supply_chain)} articles mentioning 'supply chain'")
    print("\nTop 3 by relevance:")
    for idx, row in supply_chain.nlargest(3, 'relevance_score').iterrows():
        print(f"  • Score {row['relevance_score']:.0f}: {row['url']}")


def example_2_category_filter(df):
    """Filter by category."""
    print("\n" + "="*70)
    print("EXAMPLE 2: Filter by category (port operations)")
    print("="*70)
    
    port_articles = df[df['categories'].str.contains('port_operations', na=False)]
    
    print(f"\nFound {len(port_articles)} port operations articles")
    print(f"Average relevance score: {port_articles['relevance_score'].mean():.1f}")
    print(f"Total text analyzed: {port_articles['text_length'].sum():,} characters")


def example_3_high_priority(df):
    """Find high-priority articles."""
    print("\n" + "="*70)
    print("EXAMPLE 3: High-priority articles (relevance >= 500)")
    print("="*70)
    
    high_priority = df[df['relevance_score'] >= 500].sort_values('relevance_score', ascending=False)
    
    print(f"\nFound {len(high_priority)} high-priority articles\n")
    for idx, row in high_priority.head(3).iterrows():
        print(f"Score: {row['relevance_score']:.0f}")
        print(f"  Source: {row['source']}")
        print(f"  URL: {row['url']}")
        print(f"  Length: {row['text_length']:,} chars")
        print()


def example_4_keyword_comparison(df):
    """Compare keyword frequencies."""
    print("="*70)
    print("EXAMPLE 4: Compare keyword frequencies")
    print("="*70)
    
    keywords_to_check = ['port', 'cargo', 'supply chain', 'semiconductor']
    
    print("\nKeyword frequency across all articles:")
    for keyword in keywords_to_check:
        count = df['keywords_found'].str.contains(keyword, na=False).sum()
        print(f"  {keyword:20s}: {count} articles")


def example_5_source_analysis(df):
    """Analyze by source."""
    print("\n" + "="*70)
    print("EXAMPLE 5: Compare data sources")
    print("="*70)
    
    source_stats = df.groupby('source').agg({
        'relevance_score': 'mean',
        'text_length': 'mean',
        'keyword_count': 'mean',
        'url': 'count'
    }).round(1)
    
    source_stats.columns = ['Avg Relevance', 'Avg Length', 'Avg Keywords', 'Article Count']
    
    print("\n" + source_stats.to_string())


def example_6_export_filtered(df):
    """Export filtered subset."""
    print("\n" + "="*70)
    print("EXAMPLE 6: Export filtered data for further analysis")
    print("="*70)
    
    # Filter: high relevance supply chain articles
    filtered = df[
        (df['relevance_score'] >= 300) &
        (df['categories'].str.contains('supply_chain', na=False))
    ]
    
    output_file = 'data/processed/high_value_supply_chain.csv'
    filtered.to_csv(output_file, index=False)
    
    print(f"\n✅ Exported {len(filtered)} articles to: {output_file}")
    print(f"   Average relevance: {filtered['relevance_score'].mean():.1f}")
    print(f"   Use for: Detailed analysis, ML training, reporting")


def example_7_time_analysis(df):
    """Analyze by time if timestamps available."""
    print("\n" + "="*70)
    print("EXAMPLE 7: Time-based analysis")
    print("="*70)
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date
    
    daily_counts = df.groupby('date').size()
    
    print(f"\nArticles collected per day:")
    for date, count in daily_counts.items():
        print(f"  {date}: {count} articles")
    
    print(f"\nTotal collection period: {df['date'].nunique()} days")


def example_8_text_sample(df):
    """Show text sample from top article."""
    print("\n" + "="*70)
    print("EXAMPLE 8: Sample text from highest-scored article")
    print("="*70)
    
    top_article = df.nlargest(1, 'relevance_score').iloc[0]
    
    print(f"\nArticle: {top_article['url']}")
    print(f"Score: {top_article['relevance_score']:.0f}")
    print(f"Keywords: {top_article['keywords_found']}")
    print(f"\nText sample (first 300 chars):")
    print("-" * 70)
    print(top_article['text'][:300] + "...")
    print("-" * 70)


def main():
    """Run all examples."""
    df = load_data()
    
    if df is None:
        return
    
    # Run examples
    example_1_filter_by_keyword(df)
    example_2_category_filter(df)
    example_3_high_priority(df)
    example_4_keyword_comparison(df)
    example_5_source_analysis(df)
    example_6_export_filtered(df)
    example_7_time_analysis(df)
    example_8_text_sample(df)
    
    print("\n" + "="*70)
    print("✅ All examples complete!")
    print("="*70)
    print("\nNext steps:")
    print("  1. Modify these examples for your specific needs")
    print("  2. Build custom analysis based on your use case")
    print("  3. Export data for visualization tools (Tableau, PowerBI)")
    print("  4. Use for ML model training (forecasting, classification)")
    print("\nSee DATA_PROCESSING_GUIDE.md for more details")


if __name__ == "__main__":
    main()
