
import os
import sys
import gc
import time
from pathlib import Path

# Force CPU
os.environ["TORCH_DEVICE"] = "cpu"
sys.path.append(str(Path(__file__).resolve().parent.parent))

def get_module_memory_info():
    import torch
    import gc
    count = 0
    for obj in gc.get_objects():
        try:
            if torch.is_tensor(obj) or (hasattr(obj, 'data') and torch.is_tensor(obj.data)):
                count += 1
        except Exception:
            pass
    return count

def report_memory(label):
    import psutil
    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / (1024 * 1024)
    print(f"📊 {label} - Resident Memory (RSS): {mem_mb:.2f} MB | Tensors in GC: {get_module_memory_info()}")

def verify_aggressive_release():
    print("🚀 Starting Aggressive Memory Release Verification...")
    report_memory("Initial State")
    
    from src.sentiment_finbert import get_finbert_pipeline
    from src.preprocessing import get_ner_pipeline
    
    print("\n--- Loading Models ---")
    get_finbert_pipeline()
    get_ner_pipeline()
    report_memory("Models Loaded")

    print("\n--- Unloading Models (Aggressive) ---")
    from src.sentiment_finbert import unload_finbert
    from src.preprocessing import unload_ner
    
    unload_finbert()
    unload_ner()
    
    # Try to find any remaining transformers models in GC
    import torch
    import gc
    for obj in gc.get_objects():
        try:
            if hasattr(obj, "__class__") and "transformers" in str(obj.__class__):
                # Try to clear it
                if hasattr(obj, "cpu"):
                    obj.cpu()
                del obj
        except Exception:
            pass
            
    gc.collect()
    gc.collect()
    
    report_memory("After Aggressive Cleanup")

    print("\n--- Final attempt: Clear all modules ---")
    # This is dangerous but let's see
    for name in list(sys.modules.keys()):
        if "transformers" in name or "torch" in name or "spacy" in name:
            del sys.modules[name]
            
    gc.collect()
    report_memory("After Module Deletion")

if __name__ == "__main__":
    verify_aggressive_release()
