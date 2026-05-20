#!/usr/bin/env python3
"""
Complete pipeline with predictive forecasting capability.
Runs all steps from raw data to hybrid forecasts that understand upcoming events.
Optimized for in-memory processing.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Ensure we're in the project root
PROJECT_ROOT = Path(__file__).parent
os.chdir(PROJECT_ROOT)

sys.path.append(str(PROJECT_ROOT))
os.environ.setdefault("PYTHONUNBUFFERED", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

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
    print("\n" + "="*80, flush=True)
    print("🚀 SUPPLY CHAIN PREDICTIVE FORECASTING PIPELINE (OPTIMIZED)", flush=True)
    print("="*80, flush=True)
    print("\nThis pipeline enables forecasting based on news about UPCOMING events:", flush=True)
    print("  ✅ Hurricane warnings with predicted landfall dates", flush=True)
    print("  ✅ Scheduled strikes and labor actions", flush=True)
    print("  ✅ Announced regulatory changes", flush=True)
    print("  ✅ Expected logistics disruptions", flush=True)
    print("\n" + "="*80 + "\n", flush=True)


def check_dependencies():
    """Check if required packages are installed."""
    print("🔍 Checking dependencies...")
    
    required_packages = [
        ("prophet", "pip install prophet"),
        ("dateutil", "pip install python-dateutil"),
        ("transformers", "pip install transformers torch"),
        ("xgboost", "pip install xgboost"),
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


def print_summary(forecasts_ran: bool, db_loaded: bool):
    """Print pipeline summary."""
    print("\n" + "="*80)
    print("✅ PIPELINE COMPLETE")
    print("="*80)
    print("\nGenerated Outputs:")
    if forecasts_ran:
        print("  📁 data/forecasts/*.json")
    else:
        print("  📁 Forecast generation skipped")
    if db_loaded:
        print("  🐘 Data loaded to PostgreSQL")
    else:
        print("  🐘 Database load skipped")
    print("\nNext Steps:")
    print("  1. Review forecast files in data/forecasts/")
    print("  2. Start API: venv311/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000")
    print("  3. Test hybrid forecast endpoint:")
    print("     curl http://127.0.0.1:8000/suppliers/[NODE_NAME]/hybrid_forecast")
    print("  4. UI: cd chain-calm-main && npm run dev (expects API on :8000)")
    print("\nDocumentation:")
    print("  📖 See CLAUDE.md for pipeline and API overview")
    print("="*80 + "\n")


def load_preprocessed_data_from_file():
    filepath = "data/processed/processed_events.jsonl"
    with open(filepath, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the supply chain predictive pipeline end-to-end."
    )
    parser.add_argument(
        "--skip-preprocessing",
        action="store_true",
        help="Use data/processed/processed_events.jsonl instead of raw data preprocessing.",
    )
    parser.add_argument(
        "--skip-optional",
        action="store_true",
        help="Skip temporal extraction and predictive forecasting steps.",
    )
    parser.add_argument(
        "--save-intermediate",
        action="store_true",
        help="Write intermediate JSONL files to data/processed/.",
    )
    parser.add_argument(
        "--forecast-days",
        type=int,
        default=14,
        help="Forecast horizon in days for predictive forecasting (default: 14).",
    )
    parser.add_argument(
        "--no-db-load",
        action="store_true",
        help="Run pipeline but do not load results into PostgreSQL.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for runtime options (legacy behavior).",
    )
    parser.add_argument(
        "--no-dependency-check",
        action="store_true",
        help="Skip dependency import checks.",
    )
    return parser.parse_args()


def resolve_runtime_config(args):
    if not args.interactive:
        return {
            "skip_preprocessing": args.skip_preprocessing,
            "skip_optional": args.skip_optional,
            "save_intermediate": args.save_intermediate,
        }

    print("Pipeline Configuration:")
    print("  Step 1: Preprocessing (extracts events from raw news)")
    print("  Steps 2-5: Required processing steps (Filter, Score, Geocode, Match)")
    print("  Steps 6-8: Optional (predictive forecasting + database)")
    print()

    preprocessing_response = input(
        "Skip preprocessing and use existing data? (y/N): "
    ).strip().lower()
    skip_preprocessing = preprocessing_response == "y"
    skip_optional = input("Run optional predictive forecasting steps? (Y/n): ").strip().lower() == "n"
    save_intermediate = input("Save intermediate JSONL files to disk? (y/N): ").strip().lower() == "y"

    return {
        "skip_preprocessing": skip_preprocessing,
        "skip_optional": skip_optional,
        "save_intermediate": save_intermediate,
    }


def run_step(step_name, fn, *args, **kwargs):
    print(f"\n▶️  {step_name}", flush=True)
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - started
    print(f"✅ {step_name} complete in {elapsed:.2f}s", flush=True)
    return result


def main():
    """Run the complete pipeline in memory."""
    args = parse_args()
    print_header()

    # Pre-flight checks
    if not args.no_dependency_check and not check_dependencies():
        print("❌ Please install missing dependencies first.")
        sys.exit(1)

    try:
        runtime = resolve_runtime_config(args)
        skip_preprocessing = runtime["skip_preprocessing"]
        skip_optional = runtime["skip_optional"]
        save_intermediate = runtime["save_intermediate"]

        if skip_preprocessing:
            print("\n⏭️  Will skip preprocessing (using existing processed_events.jsonl)")
        else:
            print("\n▶️  Will run preprocessing from raw data")

        if skip_optional:
            print("⚠️  Optional temporal + forecasting steps are disabled.")
        else:
            print("✨ Optional temporal + forecasting steps are enabled.")

        if save_intermediate:
            print("💾 Intermediate JSONL files will be written to disk.")
        else:
            print("🧠 Running mostly in-memory (no intermediate writes).")

        if args.no_db_load:
            print("🧪 DB load step is disabled (--no-db-load).")

        # Check for required data files
        if not check_data_files(skip_preprocessing):
            if skip_preprocessing:
                print("❌ Cannot skip preprocessing without existing preprocessed data.")
                print("   Please run preprocessing first or add raw data.")
            else:
                print("❌ Please add raw news data to data/raw/web_scrape/")
            sys.exit(1)
        print("\n🚀 Starting in-memory pipeline execution...")

        # --- Step 1: Preprocessing ---
        preprocessing_step_name = "1. Preprocessing"
        if skip_preprocessing:
            events = run_step(preprocessing_step_name, load_preprocessed_data_from_file)
            print(f"📦 Loaded {len(events)} preprocessed events from disk.")
        else:
            events = run_step(preprocessing_step_name, process_all_data, save_to_disk=save_intermediate)

        if not events:
            print("❌ Pipeline failed: No events to process.")
            sys.exit(1)

        # --- Step 2: Filter Events ---
        events = run_step("2. Filter Events", filter_events, events)
        if save_intermediate:
            save_filtered_data(events)

        if not events:
            print("❌ Pipeline failed: All events were filtered out.")
            sys.exit(1)

        # --- Step 3: Risk Scoring ---
        events = run_step("3. Risk Scoring", score_all_events, events)
        if save_intermediate:
            save_scored_data(events)

        # --- Step 4: Geocoding ---
        events = run_step("4. Geocoding", geocode_events, events)
        if save_intermediate:
            save_geocoded_data(events)

        # --- Step 5: Match to Supply Chain Nodes ---
        events = run_step("5. Match to Supply Chain Nodes", match_all_events, events)
        if save_intermediate:
            save_matched_events(events)

        # Optional Steps
        if not skip_optional:
            # --- Step 6: Temporal Extraction ---
            events = run_step("6. Temporal Extraction", enrich_events_with_temporal_data, events)
            if save_intermediate:
                save_temporal_enriched_data(events)

        # --- Disruption & impact (XGBoost pickles, same as RSS) ---
        print("\n▶️  Disruption & impact models (optional; env DISRUPTION_CLASSIFIER_PATH / IMPACT_REGRESSOR_PATH)")
        from src.rss_ingest import apply_batch_disruption_and_impact

        run_step("Disruption & Impact Inference", apply_batch_disruption_and_impact, events)

        if not skip_optional:
            # --- Step 7: Predictive Forecasting ---
            run_step("7. Predictive Forecasting", generate_all_node_forecasts, events, forecast_days=args.forecast_days)

        # --- Step 8: Load to Database ---
        db_loaded = False
        if args.no_db_load:
            print("\n⏭️  8. Load to Database skipped.")
        else:
            print("\n▶️  8. Load to Database")
            engine = get_db_engine()
            if engine:
                run_step("Create DB tables", create_tables, engine)
                run_step("Populate database", populate_database, engine, events)
                db_loaded = True
            else:
                print("❌ Could not connect to database, skipping data load.")

        # Summary
        print_summary(forecasts_ran=not skip_optional, db_loaded=db_loaded)
    finally:
        print("\n🧹 Cleaning up ML models and memory...")
        try:
            from src.sentiment_finbert import unload_finbert
            from src.preprocessing import unload_ner
            from src.temporal_extraction import unload_nlp
            unload_finbert()
            unload_ner()
            unload_nlp()
        except ImportError:
            pass

        import gc
        gc.collect()
        gc.collect()
        gc.collect()
        
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                try:
                    torch.mps.empty_cache()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            import psutil
            import os
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / (1024 * 1024)
            print(f"📊 Current Resident Memory (RSS): {mem_mb:.2f} MB")
        except (ImportError, Exception):
            pass

        print("✅ Memory cleanup complete.")


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
