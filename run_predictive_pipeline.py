#!/usr/bin/env python3
"""
Complete pipeline with predictive forecasting capability.
Runs all steps from raw data to hybrid forecasts that understand upcoming events.
Optimized for in-memory processing.
"""

import sys
import os
import json
from pathlib import Path

# Ensure we're in the project root
PROJECT_ROOT = Path(__file__).parent
os.chdir(PROJECT_ROOT)

sys.path.append(str(PROJECT_ROOT))

# Import pipeline functions
from src.preprocessing import process_all_data
from src.filter_events import filter_events, save_filtered_data
from src.risk_scoring import score_all_events, save_scored_data
from src.geocoding import geocode_events, save_geocoded_data
from src.match_events_to_nodes import match_all_events, save_matched_events
from src.temporal_extraction import enrich_events_with_temporal_data, save_temporal_enriched_data
from src.predictive_forecasting import generate_all_node_forecasts
from src.load_to_db import get_db_engine, create_tables, populate_database


def print_header():
    """Print a nice header."""
    print("\n" + "="*80)
    print("🚀 SUPPLY CHAIN PREDICTIVE FORECASTING PIPELINE (OPTIMIZED)")
    print("="*80)
    print("\nThis pipeline enables forecasting based on news about UPCOMING events:")
    print("  ✅ Hurricane warnings with predicted landfall dates")
    print("  ✅ Scheduled strikes and labor actions")
    print("  ✅ Announced regulatory changes")
    print("  ✅ Expected logistics disruptions")
    print("\n" + "="*80 + "\n")


def check_dependencies():
    """Check if required packages are installed."""
    print("🔍 Checking dependencies...")
    
    required_packages = [
        ('prophet', 'pip install prophet'),
        ('dateutil', 'pip install python-dateutil'),
        ('transformers', 'pip install transformers torch'),
    ]
    
    missing = []
    
    for package, install_cmd in required_packages:
        try:
            __import__(package)
            print(f"   ✅ {package}")
        except ImportError:
            print(f"   ❌ {package} not found")
            missing.append((package, install_cmd))
    
    if missing:
        print("\n⚠️  Missing dependencies. Install with:")
        for package, install_cmd in missing:
            print(f"   {install_cmd}")
        print()
        return False
    
    print("   ✅ All dependencies installed\n")
    return True


def check_data_files(skip_preprocessing=False):
    """Check if raw data files exist."""
    if skip_preprocessing:
        print("🔍 Checking for preprocessed data...")
        processed_file = PROJECT_ROOT / "data" / "processed" / "processed_events.jsonl"
        if processed_file.exists():
            print(f"   ✅ Found preprocessed data: {processed_file.name}")
            print()
            return True
        else:
            print(f"   ⚠️  Preprocessed data not found at {processed_file}")
            print("   Cannot skip preprocessing without existing preprocessed data.")
            print()
            return False
    else:
        print("🔍 Checking for raw data...")
        
        raw_data_dir = PROJECT_ROOT / "data" / "raw" / "web_scrape"
        
        if not raw_data_dir.exists():
            print(f"   ⚠️  Raw data directory not found: {raw_data_dir}")
            return False
        
        json_files = list(raw_data_dir.glob("*.json"))
        
        if not json_files:
            print(f"   ⚠️  No JSON files found in {raw_data_dir}")
            return False
        
        print(f"   ✅ Found {len(json_files)} data file(s)")
        for f in json_files:
            print(f"      - {f.name}")
        print()
        return True


def print_summary():
    """Print pipeline summary."""
    print("\n" + "="*80)
    print("✅ PIPELINE COMPLETE")
    print("="*80)
    print("\nGenerated Outputs:")
    print("  📁 data/forecasts/*.json")
    print("  🐘 Data loaded to PostgreSQL")
    print("\nNext Steps:")
    print("  1. Review forecast files in data/forecasts/")
    print("  2. Start API server: python src/main.py")
    print("  3. Test hybrid forecast endpoint:")
    print("     curl http://127.0.0.1:8000/suppliers/[NODE_NAME]/hybrid_forecast")
    print("  4. Update frontend to use hybrid forecasts")
    print("\nDocumentation:")
    print("  📖 See PREDICTIVE_FORECASTING_GUIDE.md for details")
    print("="*80 + "\n")


def load_preprocessed_data_from_file():
    filepath = "data/processed/processed_events.jsonl"
    with open(filepath, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f]


def main():
    """Run the complete pipeline in memory."""
    print_header()
    
    # Pre-flight checks
    if not check_dependencies():
        print("❌ Please install missing dependencies first.")
        sys.exit(1)
    
    # Ask user about preprocessing
    print("Pipeline Configuration:")
    print("  Step 1: Preprocessing (extracts events from raw news)")
    print("  Steps 2-5: Required processing steps (Filter, Score, Geocode, Match)")
    print("  Steps 6-8: Optional (predictive forecasting + database)")
    print()
    
    preprocessing_response = input("Skip preprocessing and use existing data? (y/N): ").strip().lower()
    skip_preprocessing = (preprocessing_response == 'y')
    
    if skip_preprocessing:
        print("\n⏭️  Will skip preprocessing (using existing processed_events.jsonl)")
    else:
        print("\n▶️  Will run preprocessing from raw data")
    
    # Check for required data files
    if not check_data_files(skip_preprocessing):
        if skip_preprocessing:
            print("❌ Cannot skip preprocessing without existing preprocessed data.")
            print("   Please run preprocessing first or add raw data.")
        else:
            print("❌ Please add raw news data to data/raw/web_scrape/")
        sys.exit(1)
    
    # Ask user about optional steps
    print()
    optional_response = input("Run optional predictive forecasting steps? (Y/n): ").strip().lower()
    skip_optional = (optional_response == 'n')
    
    save_intermediate = input("Save intermediate JSONL files to disk? (y/N): ").strip().lower() == 'y'

    if skip_optional:
        print("\n⚠️  Will skip optional steps (no hybrid forecasting)")
    else:
        print("\n✨ Will run full pipeline with predictive forecasting")
    
    print("\n🚀 Starting in-memory pipeline execution...")
    
    # --- Step 1: Preprocessing ---
    print("\n▶️  1. Preprocessing")
    if skip_preprocessing:
        events = load_preprocessed_data_from_file()
        print(f"✅ Loaded {len(events)} preprocessed events from disk.")
    else:
        events = process_all_data(save_to_disk=save_intermediate)

    if not events:
        print("❌ Pipeline failed: No events to process.")
        sys.exit(1)

    # --- Step 2: Filter Events ---
    print("\n▶️  2. Filter Events")
    events = filter_events(events)
    if save_intermediate:
        save_filtered_data(events)

    if not events:
        print("❌ Pipeline failed: All events were filtered out.")
        sys.exit(1)

    # --- Step 3: Risk Scoring ---
    print("\n▶️  3. Risk Scoring")
    events = score_all_events(events)
    if save_intermediate:
        save_scored_data(events)

    # --- Step 4: Geocoding ---
    print("\n▶️  4. Geocoding")
    events = geocode_events(events)
    if save_intermediate:
        save_geocoded_data(events)

    # --- Step 5: Match to Supply Chain Nodes ---
    print("\n▶️  5. Match to Supply Chain Nodes")
    events = match_all_events(events)
    if save_intermediate:
        save_matched_events(events)

    # Optional Steps
    if not skip_optional:
        # --- Step 6: Temporal Extraction ---
        print("\n▶️  6. Temporal Extraction")
        events = enrich_events_with_temporal_data(events)
        if save_intermediate:
            save_temporal_enriched_data(events)

        # --- Step 7: Predictive Forecasting ---
        print("\n▶️  7. Predictive Forecasting")
        generate_all_node_forecasts(events, forecast_days=14)

    # --- Step 8: Load to Database ---
    print("\n▶️  8. Load to Database")
    engine = get_db_engine()
    if engine:
        create_tables(engine)
        populate_database(engine, events)
    else:
        print("❌ Could not connect to database, skipping data load.")

    # Summary
    print_summary()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Pipeline interrupted by user.")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n❌ Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)
