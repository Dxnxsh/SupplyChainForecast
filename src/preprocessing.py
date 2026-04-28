# src/preprocessing.py

import json
import os
import pickle
import re
import time
import spacy
import torch
from langdetect import detect
from transformers import pipeline

# Import default user agent from config
#from config.config import DEFAULT_USER_AGENT

# --- Performance Configuration ---
NER_BATCH_SIZE = int(os.getenv("NER_BATCH_SIZE", "32"))
ML_CLASSIFIER_PATH = os.getenv("ML_CLASSIFIER_PATH", "model_training/classifier.pkl")


def _select_torch_device():
    """Select the best available torch device for transformers pipeline."""
    if torch.cuda.is_available():
        return 0, "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps", "mps"
    return -1, "cpu"


def load_ml_classifier(model_path=ML_CLASSIFIER_PATH):
    """Load the trained ML classifier tuple (vectorizer, model)."""
    if not os.path.exists(model_path):
        print(f"⚠️ ML classifier not found at {model_path}. Continuing without ML labels.")
        return None, None
    try:
        with open(model_path, "rb") as f:
            vectorizer, model = pickle.load(f)
        print(f"✅ ML risk classifier loaded from {model_path}")
        return vectorizer, model
    except Exception as e:
        print(f"⚠️ Failed to load ML classifier: {e}")
        print("   Continuing without ML risk labels.")
        return None, None


# --- Global NLP Model Initialization ---
# This section loads the models into memory once when the script starts.
try:
    nlp_spacy = spacy.load("en_core_web_sm")
    print("spaCy model 'en_core_web_sm' loaded. 📚")
except Exception as e:
    print(f"❌ Error loading spaCy model: {e}")
    print("Please run: python -m spacy download en_core_web_sm")
    exit()

try:
    ner_device, ner_device_name = _select_torch_device()
    print("Loading Hugging Face NER model (dbmdz/bert-large-cased-finetuned-conll03-english)...")
    ner_pipeline = pipeline(
        "ner",
        model="dbmdz/bert-large-cased-finetuned-conll03-english",
        grouped_entities=True,
        device=ner_device
    )
    print(f"Hugging Face NER model loaded on {ner_device_name.upper()} with batch size {NER_BATCH_SIZE}. 🤖")
except Exception as e:
    print(f"❌ Error loading Hugging Face NER model: {e}")
    print("Check internet connection and ensure `transformers` and `torch` are installed.")
    exit()

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

def detect_potential_events(text):
    """Identifies potential event categories based on keyword matching."""
    detected_events = []
    lower_text = text.lower()
    for event, keywords in EVENT_KEYWORDS.items():
        if any(_keyword_matches(lower_text, keyword) for keyword in keywords):
            detected_events.append(event)
    return list(set(detected_events))

def extract_locations_batch(texts):
    """Extract location entities for a list of texts using batched inference."""
    if not texts:
        return []
    try:
        predictions = ner_pipeline(texts, batch_size=NER_BATCH_SIZE)
        all_locations = []
        for entities in predictions:
            locations = [entity['word'] for entity in entities if entity.get('entity_group') == 'LOC']
            all_locations.append(list(set(locations)))
        return all_locations
    except Exception:
        return [[] for _ in texts]


def predict_ml_risk_batch(headlines, texts, vectorizer, model):
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
        model_inputs = [f"{h} {t[:300]}" for h, t in zip(headlines, texts)]
        X = vectorizer.transform(model_inputs)
        preds = model.predict(X)
        probs = model.predict_proba(X)
        classes = list(model.classes_)
        outputs = []
        for pred, prob in zip(preds, probs):
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

def process_all_data():
    """Main function to run the full preprocessing pipeline."""
    total_start = time.perf_counter()
    load_start = time.perf_counter()
    raw_entries = load_raw_data(directory="data/raw/web_scrape")
    load_elapsed = time.perf_counter() - load_start
    ml_vectorizer, ml_model = load_ml_classifier()
    all_processed_events = []
    docs_processed = 0
    english_docs = 0
    candidate_paragraphs = 0
    ner_elapsed_total = 0.0
    ml_elapsed_total = 0.0

    processing_start = time.perf_counter()
    for i, raw_entry in enumerate(raw_entries):
        if i % 100 == 0:
            print(f"🔄 Processing document {i+1}/{len(raw_entries)}...")
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

            potential_events = detect_potential_events(para_text)
            if potential_events:
                paragraph_candidates.append((j, para_text, potential_events))
        candidate_paragraphs += len(paragraph_candidates)

        batched_texts = [item[1] for item in paragraph_candidates]
        batched_headlines = [article_metadata['title']] * len(paragraph_candidates)
        ner_start = time.perf_counter()
        extracted_locations_batch = extract_locations_batch(batched_texts)
        ner_elapsed_total += time.perf_counter() - ner_start
        ml_start = time.perf_counter()
        ml_predictions = predict_ml_risk_batch(
            batched_headlines, batched_texts, ml_vectorizer, ml_model
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

    output_dir = "data/processed"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "processed_events.jsonl")

    write_start = time.perf_counter()
    with open(output_path, 'w', encoding='utf-8') as f:
        for entry in all_processed_events:
            json.dump(entry, f, ensure_ascii=False)
            f.write('\n')
    write_elapsed = time.perf_counter() - write_start
    total_elapsed = time.perf_counter() - total_start

    print(f"\n✅ Preprocessing complete. Saved {len(all_processed_events)} granular event entries to {output_path}")
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

if __name__ == "__main__":
    process_all_data()