# src/preprocessing.py

import json
import os
import re
import spacy
from langdetect import detect
from transformers import pipeline
from datetime import datetime

# Import default user agent from config
#from config.config import DEFAULT_USER_AGENT

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
    print("Loading Hugging Face NER model (dbmdz/bert-large-cased-finetuned-conll03-english)...")
    ner_pipeline = pipeline("ner", model="dbmdz/bert-large-cased-finetuned-conll03-english", grouped_entities=True)
    print("Hugging Face NER model loaded. 🤖")
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
        if any(keyword in lower_text for keyword in keywords):
            detected_events.append(event)
    return list(set(detected_events))

def extract_locations(text):
    """Extracts location entities using the pre-trained NER model."""
    try:
        entities = ner_pipeline(text)
        locations = [entity['word'] for entity in entities if entity['entity_group'] == 'LOC']
        return list(set(locations))
    except Exception:
        return []

# --- Main Orchestration Function ---

def process_all_data():
    """Main function to run the full preprocessing pipeline."""
    raw_entries = load_raw_data(directory="data/raw/web_scrape")
    all_processed_events = []

    for i, raw_entry in enumerate(raw_entries):
        if i % 100 == 0:
            print(f"🔄 Processing document {i+1}/{len(raw_entries)}...")

        article_metadata = parse_entry_metadata(raw_entry)
        full_text = article_metadata.get('original_text', '')

        if not full_text: continue

        paragraphs = split_into_paragraphs(full_text)

        if not paragraphs: continue

        for j, para_text in enumerate(paragraphs):
            if len(para_text) < 20: continue

            lang = detect_language(para_text)
            if lang != 'en': continue

            potential_events = detect_potential_events(para_text)
            extracted_locations = extract_locations(para_text)

            if potential_events or extracted_locations:
                all_processed_events.append({
                    'article_url': article_metadata['url'],
                    'article_source': article_metadata['source'],
                    'article_title': article_metadata['title'],
                    'article_timestamp': article_metadata['timestamp'],
                    'event_text_segment': para_text,
                    'detected_language': lang,
                    'potential_event_types': potential_events,
                    'extracted_locations': extracted_locations,
                    'paragraph_id': j
                })

    output_dir = "data/processed"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "processed_events.jsonl")

    with open(output_path, 'w', encoding='utf-8') as f:
        for entry in all_processed_events:
            json.dump(entry, f, ensure_ascii=False)
            f.write('\n')

    print(f"\n✅ Preprocessing complete. Saved {len(all_processed_events)} granular event entries to {output_path}")

if __name__ == "__main__":
    process_all_data()