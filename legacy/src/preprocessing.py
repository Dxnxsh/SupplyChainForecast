# src/preprocessing.py

import os
from dotenv import load_dotenv
# Load environment variables at the absolute top before any ML imports
load_dotenv()

# Explicitly disable Rust tokenizer parallelism to prevent asyncio/uvicorn deadlocks in background workers
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import json
import pickle
import re
import time
import warnings
import gc
import torch
from langdetect import detect
from gliner2 import GLiNER2

# Import default user agent from config
#from config.config import DEFAULT_USER_AGENT

# --- Performance Configuration ---
NER_BATCH_SIZE = int(os.getenv("NER_BATCH_SIZE", "32"))
# GLiNER2 attention matrices scale quadratically with token count; truncate inputs to cap peak VRAM.
NER_MAX_CHARS = int(os.getenv("NER_MAX_CHARS", "1000"))
ML_CLASSIFIER_PATH = os.getenv("ML_CLASSIFIER_PATH", "model_training/classifier.pkl")
_GLINER_MODEL_ID = os.getenv("GLINER_MODEL", "fastino/gliner2-base-v1")
_GLINER_LABEL = "location"
PROGRESS_EVERY_DOCS = int(os.getenv("PREPROCESS_PROGRESS_EVERY_DOCS", "25"))
# Incremented when NER raises (e.g. HIP/CUDA kernel mismatch); see end-of-run summary.
_NER_BATCH_EXCEPTIONS = 0


def _select_torch_device():
    """
    Select device for Hugging Face NER pipeline.
    Order: env TORCH_DEVICE (cuda|mps|cpu), then CUDA, then Apple Metal (MPS), then CPU.
    On MacBook, MPS is used automatically when available; set TORCH_DEVICE=cpu to force CPU.
    AMD ROCm builds still use the CUDA-compatible API: torch.cuda.is_available() is True and
    device 0 is the Radeon GPU; use TORCH_DEVICE=cuda after installing torch+rocm wheels.
    """
    forced = (os.getenv("TORCH_DEVICE") or "").strip().lower()
    if forced == "cpu":
        return "cpu", "cpu"
    if forced == "cuda":
        if torch.cuda.is_available():
            return 0, "cuda"
        print("⚠️ TORCH_DEVICE=cuda requested but CUDA is not available; using auto selection.")
    if forced == "mps":
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps", "mps"
        print("⚠️ TORCH_DEVICE=mps requested but MPS is not available; using auto selection.")
    if torch.cuda.is_available():
        return 0, "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps", "mps"
    return "cpu", "cpu"


def load_ml_classifier(model_path=ML_CLASSIFIER_PATH):
    """Load classifier pickle: (vectorizer, model) or (vectorizer, model, LabelEncoder)."""
    if not os.path.exists(model_path):
        print(f"⚠️ ML classifier not found at {model_path}. Continuing without ML labels.")
        return None, None, None
    try:
        with open(model_path, "rb") as f:
            payload = pickle.load(f)
        if isinstance(payload, tuple) and len(payload) == 3:
            vectorizer, model, label_encoder = payload[0], payload[1], payload[2]
        elif isinstance(payload, tuple) and len(payload) == 2:
            vectorizer, model, label_encoder = payload[0], payload[1], None
        else:
            raise ValueError("classifier pickle must be 2- or 3-tuple")
        # Pin XGBoost to CPU so TF-IDF sparse matrices don't trigger a CPU→GPU transfer.
        try:
            import xgboost as xgb
            if isinstance(model, (xgb.XGBClassifier, xgb.XGBRegressor, xgb.XGBModel)):
                model.set_params(device="cpu", tree_method="hist")
            elif isinstance(model, xgb.Booster):
                model.set_param({"device": "cpu", "tree_method": "hist"})
        except Exception:
            pass
        print(f"✅ ML risk classifier loaded from {model_path}")
        return vectorizer, model, label_encoder
    except Exception as e:
        print(f"⚠️ Failed to load ML classifier: {e}")
        print("   Continuing without ML risk labels.")
        return None, None, None


# --- Global NLP Model Initialization ---
# This section defines lazy loading for models.

_gliner_model = None

def _resolve_gliner_model_path(model_id: str) -> str:
    """Return a local snapshot path if the model is cached, else return model_id for HF download."""
    try:
        from huggingface_hub import try_to_load_from_cache, HUGGINGFACE_HUB_CACHE
        snapshot_path = try_to_load_from_cache(model_id, "config.json")
        if snapshot_path and os.path.isfile(snapshot_path):
            local_dir = os.path.dirname(snapshot_path)
            return local_dir
    except Exception:
        pass
    return model_id


def get_ner_pipeline():
    """Lazily load the GLiNER2 model for zero-shot NER."""
    global _gliner_model
    if _gliner_model is None:
        try:
            ner_device, ner_device_name = _select_torch_device()
            model_path = _resolve_gliner_model_path(_GLINER_MODEL_ID)
            print(f"Loading GLiNER2 model ({_GLINER_MODEL_ID})...")
            # Force offline mode when model is already cached to avoid network hangs.
            # transformers' AutoTokenizer/AutoConfig still hit HF even with a local dir.
            _is_local = model_path != _GLINER_MODEL_ID
            _prev_hf = os.environ.get("HF_HUB_OFFLINE")
            _prev_tr = os.environ.get("TRANSFORMERS_OFFLINE")
            if _is_local:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
            try:
                model = GLiNER2.from_pretrained(model_path)
            finally:
                if _is_local:
                    if _prev_hf is None:
                        os.environ.pop("HF_HUB_OFFLINE", None)
                    else:
                        os.environ["HF_HUB_OFFLINE"] = _prev_hf
                    if _prev_tr is None:
                        os.environ.pop("TRANSFORMERS_OFFLINE", None)
                    else:
                        os.environ["TRANSFORMERS_OFFLINE"] = _prev_tr
            # MPS has known init issues with DeBERTa-based models on Apple Silicon;
            # fall back to CPU if the move fails.
            try:
                model = model.to(ner_device)
            except Exception as mps_err:
                if ner_device_name == "mps":
                    print(f"⚠️ MPS transfer failed ({mps_err}); falling back to CPU for GLiNER2.")
                    ner_device, ner_device_name = "cpu", "cpu"
                    model = model.to(ner_device)
                else:
                    raise
            _gliner_model = model
            if ner_device_name == "mps":
                print(
                    f"GLiNER2 model loaded on Apple Metal (MPS) with batch size {NER_BATCH_SIZE}. "
                    "If you see errors, try: export PYTORCH_ENABLE_MPS_FALLBACK=1"
                )
            elif ner_device_name == "cuda" and torch.cuda.is_available():
                try:
                    dev = torch.cuda.get_device_name(0)
                except Exception:
                    dev = "cuda:0"
                print(f"GLiNER2 model loaded on CUDA/HIP ({dev}) with batch size {NER_BATCH_SIZE}.")
            else:
                print(f"GLiNER2 model loaded on {ner_device_name.upper()} with batch size {NER_BATCH_SIZE}.")
        except Exception as e:
            print(f"❌ Error loading GLiNER2 model: {e}")
            print("Check internet connection and ensure `gliner2` and `torch` are installed.")
            raise e
    return _gliner_model


def unload_ner():
    """Clear the GLiNER2 model from RAM and trigger garbage collection."""
    global _gliner_model
    if _gliner_model is not None:
        print("📉 Unloading GLiNER2 model from RAM...")
        try:
            _gliner_model.to("cpu")
        except Exception:
            pass

        del _gliner_model
        _gliner_model = None

        gc.collect()
        gc.collect()

        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                try:
                    torch.mps.empty_cache()
                except Exception:
                    pass
        except Exception:
            pass

# --- Event Keyword Definitions ---
EVENT_KEYWORDS = {
    'Labor_Issue': ['strike', 'protest', 'walkout', 'labor dispute', 'union', 'wage', 'unrest', 'shutdown', 'picket'],
    'Logistics_Issue': ['port congestion', 'delay', 'shipping', 'freight', 'cargo', 'customs', 'port closure', 'vessel', 'container', 'blockade', 'traffic'],
    'Natural_Disaster': ['earthquake', 'typhoon', 'flood', 'tsunami', 'hurricane', 'wildfire', 'storm', 'drought', 'blizzard'],
    'Industrial_Accident': ['factory fire', 'explosion', 'chemical spill', 'power outage', 'maintenance', 'malfunction', 'breakdown', 'accident'],
    'Political_Regulatory': ['tariff', 'embargo', 'trade war', 'lockdown', 'sanction', 'regulation','military conflict', 'geopolitical tension', 'export ban', 'import restrictions'], 
    'Demand_Supply_Shift': ['shortage', 'oversupply', 'demand drop', 'demand surge', 'inventory', 'stockpile'],
    'Cyber_Attack': ['cyberattack', 'hack', 'ransomware', 'data breach', 'system outage']
}


def _keyword_matches(text, keyword):
    """Match phrases loosely and single words on boundaries."""
    if ' ' in keyword:
        return keyword in text
    return re.search(rf'\b{re.escape(keyword)}\b', text) is not None

# --- Core Preprocessing Functions ---

def load_raw_data(directory="data/raw/web_scrape"):
    """
    Loads multiple .json files from a directory, cleans invalid control characters
    before parsing, and handles the specific JSON structure.
    """
    all_entries = []
    if not os.path.exists(directory):
        print(f"❌ Error: Raw data directory not found at {directory}")
        return []

    json_files = [f for f in os.listdir(directory) if f.endswith(".json")]
    if not json_files:
        print(f"🤷 No .json files found in {directory}")
        return []

    print(f"🔎 Loading {len(json_files)} .json files from {directory}...")
    for filename in json_files:
        filepath = os.path.join(directory, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Aggressive cleaning: Remove ALL ASCII control characters (0x00-0x1F)
            # This is the most likely fix for the "Invalid control character" error.
            cleaned_content = re.sub(r'[\x00-\x1f]', '', content)

            entry_list = json.loads(cleaned_content)

            if isinstance(entry_list, list):
                all_entries.extend(entry_list)
            else:
                print(f"⚠️ Warning: File {filename} does not contain a list of entries at root. Skipping.")

        except json.JSONDecodeError as e:
            print(f"❌ Error: Could not decode JSON from {filepath} after cleaning. Error: {e}")

            # --- Debugging Block ---
            # If the error persists, this will help us find the exact character.
            char_index = e.pos
            print(f"   Debugging: Error occurred at character index {char_index}.")
            if char_index < len(cleaned_content):
                problem_char = cleaned_content[char_index]
                print(f"   Character at index {char_index} is: '{problem_char}' (ASCII/Unicode value: {ord(problem_char)})")
                start = max(0, char_index - 50)
                end = min(len(cleaned_content), char_index + 50)
                print(f"   Context: '{cleaned_content[start:end]}'")
            else:
                print(f"   Problematic character index {char_index} is out of bounds for cleaned content.")

        except Exception as e:
            print(f"❌ An unexpected error occurred while loading {filepath}: {e}")

    print(f"✅ Loaded {len(all_entries)} total entries from all .json files in {directory}")
    return all_entries

def parse_entry_metadata(entry):
    """Parses the 'label' field into source, title, url, and timestamp."""
    label_str = entry.get('label', '')
    parts = label_str.split(';')

    return {
        "source": parts[0] if len(parts) > 0 else "Unknown",
        "title": parts[1] if len(parts) > 1 else "",
        "url": parts[2] if len(parts) > 2 else "",
        "timestamp": parts[3] if len(parts) > 3 else None,
        "original_text": entry.get('text', '')
    }

def clean_text(text):
    """Performs basic text cleaning."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'<[^>]+>', '', text)
    text = ''.join(char for char in text if char.isprintable())
    return text

def split_into_paragraphs(text):
    """Splits text into paragraphs based on double newlines."""
    paragraphs = []
    raw_paragraphs = text.split('\n\n')
    for para in raw_paragraphs:
        cleaned_para = clean_text(para)
        if len(cleaned_para) > 50: # Only consider paragraphs long enough to be meaningful
            paragraphs.append(cleaned_para)
    return paragraphs

def detect_language(text):
    """Detects the language of the text."""
    try:
        if len(text) < 50: return "unknown"
        return detect(text)
    except:
        return "unknown"

def detect_potential_events(text, title=""):
    """Identifies potential event categories based on keyword matching."""
    detected_events = []
    lower_text = f"{title} {text}".lower().strip()
    for event, keywords in EVENT_KEYWORDS.items():
        if any(_keyword_matches(lower_text, keyword) for keyword in keywords):
            detected_events.append(event)
    return list(set(detected_events))

def extract_locations_batch(texts):
    """Extract location entities for a list of texts using GLiNER2 batched inference."""
    if not texts:
        return []
    try:
        model = get_ner_pipeline()
        from tqdm import tqdm

        labels = [_GLINER_LABEL]

        all_locations = []
        _cuda = torch.cuda.is_available()
        _mps = not _cuda and hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        if _cuda:
            _total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3

        pbar = tqdm(
            range(0, len(texts), NER_BATCH_SIZE),
            desc="Step 2/5: Extracting Locations (NER)",
        )
        for i in pbar:
            batch = [(t or "")[:NER_MAX_CHARS] for t in texts[i:i + NER_BATCH_SIZE]]
            batch_results = model.batch_extract_entities(batch, labels)
            for result in batch_results:
                locs = result.get("entities", {}).get(_GLINER_LABEL, [])
                all_locations.append(locs)

            try:
                if _cuda:
                    torch.cuda.empty_cache()
                    alloc = torch.cuda.memory_allocated() / 1024**3
                    free = _total_gb - torch.cuda.memory_reserved() / 1024**3
                    pbar.set_postfix({"alloc": f"{alloc:.2f}G", "free": f"{free:.2f}G", "tot": f"{_total_gb:.2f}G"})
                elif _mps:
                    alloc = torch.mps.current_allocated_memory() / 1024**3
                    pbar.set_postfix({"mps_alloc": f"{alloc:.2f}G"})
            except Exception:
                pass
        return all_locations
    except Exception as e:
        global _NER_BATCH_EXCEPTIONS
        _NER_BATCH_EXCEPTIONS += 1
        if not getattr(extract_locations_batch, "_warned", False):
            extract_locations_batch._warned = True
            warnings.warn(
                f"GLiNER2 location extraction failed for a batch ({e!s}). "
                "Returning empty locations for those paragraphs. "
                "Set TORCH_DEVICE=cpu if you see GPU errors.",
                UserWarning,
                stacklevel=2,
            )
        return [[] for _ in texts]


def predict_ml_risk_batch(headlines, texts, vectorizer, model, label_encoder=None):
    """Predict ML risk labels/probabilities for headline+text inputs."""
    if not texts:
        return []
    if vectorizer is None or model is None:
        return [
            {
                "ml_risk_label": None,
                "ml_risk_confidence": None,
                "ml_risk_probabilities": None,
            }
            for _ in texts
        ]
    try:
        import numpy as np

        model_inputs = [f"{h} {t[:300]}" for h, t in zip(headlines, texts)]
        X = vectorizer.transform(model_inputs)
        raw_preds = model.predict(X)
        probs = model.predict_proba(X)
        if label_encoder is not None:
            classes = [str(c) for c in label_encoder.classes_]
            pred_labels = label_encoder.inverse_transform(np.asarray(raw_preds, dtype=int))
        else:
            classes = [str(c) for c in model.classes_]
            pred_labels = [str(p) for p in raw_preds]
        outputs = []
        for pred, prob in zip(pred_labels, probs):
            prob_map = {c: round(float(p), 4) for c, p in zip(classes, prob)}
            outputs.append({
                "ml_risk_label": str(pred),
                "ml_risk_confidence": round(max(prob_map.values()), 4) if prob_map else None,
                "ml_risk_probabilities": prob_map
            })
        return outputs
    except Exception:
        return [
            {
                "ml_risk_label": None,
                "ml_risk_confidence": None,
                "ml_risk_probabilities": None,
            }
            for _ in texts
        ]

# --- Main Orchestration Function ---

def process_all_data(save_to_disk=False):
    """Main function to run the full preprocessing pipeline."""
    global _NER_BATCH_EXCEPTIONS
    _NER_BATCH_EXCEPTIONS = 0
    extract_locations_batch._warned = False
    total_start = time.perf_counter()
    load_start = time.perf_counter()
    raw_entries = load_raw_data(directory="data/raw/web_scrape")
    load_elapsed = time.perf_counter() - load_start
    ml_vectorizer, ml_model, ml_label_encoder = load_ml_classifier()
    all_processed_events = []
    docs_processed = 0
    english_docs = 0
    candidate_paragraphs = 0
    ner_elapsed_total = 0.0
    ml_elapsed_total = 0.0

    processing_start = time.perf_counter()
    total_docs = len(raw_entries)
    last_progress_ts = time.perf_counter()
    for i, raw_entry in enumerate(raw_entries):
        if i == 0 or (i + 1) % max(PROGRESS_EVERY_DOCS, 1) == 0:
            now = time.perf_counter()
            processed_so_far = i + 1
            elapsed = now - processing_start
            docs_per_sec = (processed_so_far / elapsed) if elapsed > 0 else 0.0
            pct = (processed_so_far / total_docs * 100.0) if total_docs else 100.0
            print(
                f"🔄 Preprocessing progress: {processed_so_far}/{total_docs} docs ({pct:.1f}%) "
                f"| events={len(all_processed_events)} | candidates={candidate_paragraphs} | {docs_per_sec:.2f} docs/s",
                flush=True,
            )
            last_progress_ts = now
        docs_processed += 1

        article_metadata = parse_entry_metadata(raw_entry)
        full_text = article_metadata.get('original_text', '')

        if not full_text: continue

        paragraphs = split_into_paragraphs(full_text)

        if not paragraphs: continue

        article_lang = detect_language(full_text)
        if article_lang != 'en':
            continue
        english_docs += 1

        paragraph_candidates = []
        for j, para_text in enumerate(paragraphs):
            if len(para_text) < 20: continue

            potential_events = detect_potential_events(para_text, article_metadata['title'])
            if potential_events:
                paragraph_candidates.append((j, para_text, potential_events))
        candidate_paragraphs += len(paragraph_candidates)
        # Heartbeat for long NER-heavy stretches even when doc-based thresholds are not reached.
        now = time.perf_counter()
        if now - last_progress_ts >= 10:
            print(
                f"⏳ Working... docs={i+1}/{total_docs}, candidates={candidate_paragraphs}, "
                f"events={len(all_processed_events)}",
                flush=True,
            )
            last_progress_ts = now

        batched_texts = [item[1] for item in paragraph_candidates]
        batched_headlines = [article_metadata['title']] * len(paragraph_candidates)
        ner_start = time.perf_counter()
        extracted_locations_batch = extract_locations_batch(batched_texts)
        ner_elapsed_total += time.perf_counter() - ner_start
        ml_start = time.perf_counter()
        ml_predictions = predict_ml_risk_batch(
            batched_headlines, batched_texts, ml_vectorizer, ml_model, ml_label_encoder
        )
        ml_elapsed_total += time.perf_counter() - ml_start

        for idx, (j, para_text, potential_events) in enumerate(paragraph_candidates):
            extracted_locations = extracted_locations_batch[idx] if idx < len(extracted_locations_batch) else []
            ml_info = ml_predictions[idx] if idx < len(ml_predictions) else {
                "ml_risk_label": None,
                "ml_risk_confidence": None,
                "ml_risk_probabilities": None,
            }
            if potential_events or extracted_locations:
                all_processed_events.append({
                    'article_url': article_metadata['url'],
                    'article_source': article_metadata['source'],
                    'article_title': article_metadata['title'],
                    'article_timestamp': article_metadata['timestamp'],
                    'event_text_segment': para_text,
                    'detected_language': article_lang,
                    'potential_event_types': potential_events,
                    'extracted_locations': extracted_locations,
                    'ml_risk_label': ml_info["ml_risk_label"],
                    'ml_risk_confidence': ml_info["ml_risk_confidence"],
                    'ml_risk_probabilities': ml_info["ml_risk_probabilities"],
                    'paragraph_id': j
                })
    processing_elapsed = time.perf_counter() - processing_start

    if save_to_disk:
        output_dir = "data/processed"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "processed_events.jsonl")

        write_start = time.perf_counter()
        with open(output_path, 'w', encoding='utf-8') as f:
            for entry in all_processed_events:
                json.dump(entry, f, ensure_ascii=False)
                f.write('\n')
        write_elapsed = time.perf_counter() - write_start
        print(f"\n✅ Preprocessing complete. Saved {len(all_processed_events)} granular event entries to {output_path}")
    else:
        write_elapsed = 0
        print(f"\n✅ Preprocessing complete. Processed {len(all_processed_events)} granular event entries.")
    
    total_elapsed = time.perf_counter() - total_start
    with_loc = sum(1 for e in all_processed_events if e.get("extracted_locations"))
    if _NER_BATCH_EXCEPTIONS and all_processed_events:
        print(
            f"\n⚠️ NER failed for {_NER_BATCH_EXCEPTIONS} batch(es): all `extracted_locations` will be empty. "
            "Typical cause: PyTorch on AMD GPU (HIP invalid device function). "
            "Re-run preprocessing with: export TORCH_DEVICE=cpu",
            flush=True,
        )
    elif not with_loc and all_processed_events:
        print(
            "\n⚠️ No events have extracted_locations (NER returned no LOC entities). "
            "If you expected place names, confirm NER is not erroring and texts are not stripped of geography.",
            flush=True,
        )
    print("\n⏱️ Timing Summary")
    print(f"   Data load: {load_elapsed:.2f}s")
    print(f"   Processing (incl. language + keyword + NER): {processing_elapsed:.2f}s")
    print(f"   Batched NER only: {ner_elapsed_total:.2f}s")
    print(f"   Batched ML inference only: {ml_elapsed_total:.2f}s")
    print(f"   Output write: {write_elapsed:.2f}s")
    print(f"   Total: {total_elapsed:.2f}s")
    print("\n📊 Throughput Summary")
    print(f"   Documents seen: {docs_processed}")
    print(f"   English documents: {english_docs}")
    print(f"   Candidate paragraphs sent to NER: {candidate_paragraphs}")
    if ner_elapsed_total > 0:
        print(f"   NER paragraphs/sec: {candidate_paragraphs / ner_elapsed_total:.2f}")
    if ml_elapsed_total > 0:
        print(f"   ML inference paragraphs/sec: {candidate_paragraphs / ml_elapsed_total:.2f}")

    return all_processed_events

if __name__ == "__main__":
    process_all_data(save_to_disk=True)