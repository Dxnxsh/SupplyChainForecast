
import os
import sys
import gc
import time
from pathlib import Path

# Force CPU for this test
os.environ["TORCH_DEVICE"] = "cpu"

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

def report_memory(label):
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_mb = process.memory_info().rss / (1024 * 1024)
        print(f"📊 {label} - Resident Memory (RSS): {mem_mb:.2f} MB")
    except ImportError:
        print(f"📊 {label} - psutil not installed")

def verify_memory_release():
    print("🚀 Starting Memory Release Verification (FORCED CPU)...")
    report_memory("Initial State")
    
    # 1. Load models
    print("\n--- Loading Models ---")
    try:
        from src.sentiment_finbert import get_finbert_pipeline
        from src.preprocessing import get_ner_pipeline
        from src.temporal_extraction import get_nlp
        
        print("Loading FinBERT...")
        get_finbert_pipeline()
        report_memory("After FinBERT")
        
        print("Loading NER...")
        get_ner_pipeline()
        report_memory("After NER")
        
        print("Loading spaCy...")
        get_nlp()
        report_memory("After all models loaded")
    except Exception as e:
        print(f"❌ Error loading models: {e}")
        import traceback
        traceback.print_exc()
        return

    # 2. Unload models
    print("\n--- Unloading Models ---")
    try:
        from src.sentiment_finbert import unload_finbert
        from src.preprocessing import unload_ner
        from src.temporal_extraction import unload_nlp
        
        unload_finbert()
        unload_ner()
        unload_nlp()
        
        print("\n🧹 Forcing additional garbage collection...")
        gc.collect()
        gc.collect()
        gc.collect()
        
        report_memory("After Cleanup")
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")

    print("\n✅ Verification complete.")

if __name__ == "__main__":
    verify_memory_release()
