
import sys
from pathlib import Path

# Mock modules to test cleanup
import os
os.makedirs("src", exist_ok=True)
with open("src/sentiment_finbert.py", "a") as f:
    pass # Already exists

with open("src/preprocessing.py", "a") as f:
    pass # Already exists

def test_cleanup():
    print("Testing cleanup logic...")
    try:
        print("Running logic...")
        # Simulate some work
    finally:
        print("\n🧹 Cleaning up ML models and memory...")
        try:
            from src.sentiment_finbert import unload_finbert
            from src.preprocessing import unload_ner
            unload_finbert()
            unload_ner()
        except ImportError as e:
            print(f"Import error: {e}")
        
        import gc
        gc.collect()
        print("✅ Memory cleanup complete.")

if __name__ == "__main__":
    test_cleanup()
