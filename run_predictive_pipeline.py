#!/usr/bin/env python3
"""
Complete pipeline with predictive forecasting capability.
Runs all steps from raw data to hybrid forecasts that understand upcoming events.
"""

import sys
import subprocess
import os
from pathlib import Path

# Ensure we're in the project root
PROJECT_ROOT = Path(__file__).parent
os.chdir(PROJECT_ROOT)

STEPS = [
    {
        "name": "1. Preprocessing",
        "script": "src/preprocessing.py",
        "description": "Extract events from raw news articles",
        "required": True
    },
    {
        "name": "2. Filter Events",
        "script": "src/filter_events.py",
        "description": "Filter for supply-chain relevant events",
        "required": True
    },
    {
        "name": "3. Risk Scoring",
        "script": "src/risk_scoring.py",
        "description": "Calculate risk scores based on event types and urgency",
        "required": True
    },
    {
        "name": "4. Geocoding",
        "script": "src/geocoding.py",
        "description": "Extract and geocode location information",
        "required": True
    },
    {
        "name": "5. Match to Supply Chain Nodes",
        "script": "src/match_events_to_nodes.py",
        "description": "Match events to supplier nodes",
        "required": True
    },
    {
        "name": "6. Temporal Extraction (NEW)",
        "script": "src/temporal_extraction.py",
        "description": "Extract WHEN predicted events will occur (hurricanes, strikes, etc.)",
        "required": False,
        "new": True
    },
    {
        "name": "7. Hybrid Forecasting (NEW)",
        "script": "src/predictive_forecasting.py",
        "description": "Generate forecasts combining news predictions + historical trends",
        "required": False,
        "new": True
    },
    {
        "name": "8. Load to Database",
        "script": "src/load_to_db.py",
        "description": "Load processed events to PostgreSQL database",
        "required": False
    }
]


def print_header():
    """Print a nice header."""
    print("\n" + "="*80)
    print("🚀 SUPPLY CHAIN PREDICTIVE FORECASTING PIPELINE")
    print("="*80)
    print("\nThis pipeline enables forecasting based on news about UPCOMING events:")
    print("  ✅ Hurricane warnings with predicted landfall dates")
    print("  ✅ Scheduled strikes and labor actions")
    print("  ✅ Announced regulatory changes")
    print("  ✅ Expected logistics disruptions")
    print("\n" + "="*80 + "\n")


def run_step(step, skip_optional=False, skip_preprocessing=False):
    """Run a single pipeline step."""
    # Skip optional steps if requested
    if not step['required'] and skip_optional:
        print(f"\n⏭️  Skipping: {step['name']} (optional)")
        return True
    
    # Skip preprocessing if requested
    if skip_preprocessing and step['name'] == "1. Preprocessing":
        print(f"\n⏭️  Skipping: {step['name']} (using existing processed data)")
        return True
    
    print(f"\n{'🆕' if step.get('new') else '▶️'}  {step['name']}")
    print(f"   {step['description']}")
    print("-" * 80)
    
    script_path = PROJECT_ROOT / step['script']
    
    if not script_path.exists():
        print(f"   ⚠️  Script not found: {script_path}")
        return False
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=PROJECT_ROOT,
            capture_output=False,
            text=True
        )
        
        if result.returncode != 0:
            print(f"   ❌ Step failed with return code {result.returncode}")
            return False
        
        print(f"   ✅ Completed successfully")
        return True
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def check_dependencies():
    """Check if required packages are installed."""
    print("🔍 Checking dependencies...")
    
    required_packages = [
        ('spacy', 'python -m spacy download en_core_web_sm'),
        ('prophet', 'pip install prophet'),
        ('dateutil', 'pip install python-dateutil'),
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
    print("  📁 data/processed/temporal_enriched_events.jsonl")
    print("  📁 data/forecasts/*.json")
    print("\nNext Steps:")
    print("  1. Review forecast files in data/forecasts/")
    print("  2. Start API server: python src/main.py")
    print("  3. Test hybrid forecast endpoint:")
    print("     curl http://127.0.0.1:8000/suppliers/[NODE_NAME]/hybrid_forecast")
    print("  4. Update frontend to use hybrid forecasts")
    print("\nDocumentation:")
    print("  📖 See PREDICTIVE_FORECASTING_GUIDE.md for details")
    print("="*80 + "\n")


def main():
    """Run the complete pipeline."""
    print_header()
    
    # Pre-flight checks
    if not check_dependencies():
        print("❌ Please install missing dependencies first.")
        sys.exit(1)
    
    # Ask user about preprocessing
    print("Pipeline Configuration:")
    print("  Step 1: Preprocessing (extracts events from raw news)")
    print("  Steps 2-5: Required processing steps")
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
    
    if skip_optional:
        print("\n⚠️  Will skip optional steps (no hybrid forecasting)")
    else:
        print("\n✨ Will run full pipeline with predictive forecasting")
    
    input("\nPress Enter to continue...")
    
    # Run pipeline steps
    success_count = 0
    fail_count = 0
    skipped_count = 0
    
    for step in STEPS:
        # Check if we're skipping this step
        is_skipped = (skip_preprocessing and step['name'] == "1. Preprocessing") or \
                     (not step['required'] and skip_optional)
        
        if is_skipped and (skip_preprocessing and step['name'] == "1. Preprocessing"):
            skipped_count += 1
        
        success = run_step(step, skip_optional, skip_preprocessing)
        if success:
            success_count += 1
        else:
            fail_count += 1
            
            if step['required'] and not (skip_preprocessing and step['name'] == "1. Preprocessing"):
                print(f"\n❌ Required step failed: {step['name']}")
                print("   Pipeline cannot continue.")
                sys.exit(1)
            elif not step['required']:
                response = input(f"\n⚠️  Optional step failed. Continue? (y/N): ").strip().lower()
                if response != 'y':
                    print("\n🛑 Pipeline stopped by user.")
                    sys.exit(1)
    
    # Summary
    print_summary()
    print(f"📊 Summary: {success_count} steps completed, {fail_count} steps failed, {skipped_count} steps skipped\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Pipeline interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

