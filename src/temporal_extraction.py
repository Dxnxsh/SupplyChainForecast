# src/temporal_extraction.py
"""
Extracts temporal information from news articles to identify WHEN predicted events will occur.
This enables forecasting based on warnings about upcoming hurricanes, strikes, etc.
"""

import json
import os
import re
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta
import spacy

# Load spaCy model for NER (Named Entity Recognition)
try:
    nlp = spacy.load("en_core_web_sm")
except:
    print("⚠️  Warning: spaCy model not loaded. Run: python -m spacy download en_core_web_sm")
    nlp = None

# --- Temporal Keywords and Patterns ---

# Keywords indicating forward-looking/predictive content
PREDICTIVE_INDICATORS = [
    'forecast', 'forecasted', 'forecasting', 'predicted', 'predicting', 'prediction',
    'expected', 'expecting', 'expects', 'projected', 'projection',
    'anticipated', 'anticipate', 'anticipating', 'upcoming', 'approaching',
    'scheduled', 'planned', 'warned', 'warning', 'alert', 'threatens',
    'could hit', 'may strike', 'likely to', 'is set to', 'preparing for',
    'bracing for', 'expected to impact', 'could affect', 'poised to',
    'hurricane path', 'storm track', 'heading toward', 'moving toward'
]

# Stronger phrases that indicate forward-looking intent in event context.
STRONG_PREDICTIVE_PATTERNS = [
    r'\bexpected to\b', r'\bset to\b', r'\blikely to\b', r'\bmay\b', r'\bcould\b',
    r'\bupcoming\b', r'\bforecast\b', r'\bprojected\b', r'\bplanned\b', r'\bscheduled\b',
    r'\bwill\b'
]

HISTORICAL_CONTEXT_PATTERNS = [
    r'\blast year\b', r'\byears ago\b', r'\bcentury\b', r'\bsince\b',
    r'\bin\s+\d{4}\b', r'\bpreviously\b', r'\bearlier\b', r'\bhad been\b'
]

# Keep temporal projections close to operational forecasting horizon.
MAX_PREDICTION_DAYS = 60

# Keywords for different time horizons
TIME_HORIZON_KEYWORDS = {
    'immediate': {
        'keywords': ['today', 'tonight', 'this morning', 'this afternoon', 'this evening', 
                    'now', 'currently', 'at this moment', 'breaking', 'just now'],
        'days_offset': 0
    },
    'very_short': {
        'keywords': ['tomorrow', 'by tomorrow', 'tomorrow morning', 'tomorrow evening'],
        'days_offset': 1
    },
    'short': {
        'keywords': ['next week', 'early next week', 'late next week', 'coming week',
                    'this week', 'end of week', 'by friday', 'within days'],
        'days_offset': 3  # Average for "next week"
    },
    'medium': {
        'keywords': ['next month', 'coming month', 'in the coming weeks', 'within weeks',
                    'early next month', 'end of month', 'by end of'],
        'days_offset': 14  # 2 weeks
    },
    'long': {
        'keywords': ['next quarter', 'coming months', 'later this year', 'by year end',
                    'in the fall', 'in winter', 'in spring', 'in summer'],
        'days_offset': 60  # 2 months
    }
}

# Specific date patterns (regex)
DATE_PATTERNS = [
    # Format: "July 15", "December 3", etc.
    r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b',
    # Format: "July 15, 2025", "Dec 3, 2024"
    r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b',
    # Format: "15 July", "3 December"
    r'\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b',
    # Format: "2025-07-15", "2024-12-03"
    r'\b\d{4}-\d{2}-\d{2}\b',
    # Format: "07/15/2025", "12/3/2024"
    r'\b\d{1,2}/\d{1,2}/\d{4}\b',
]

# Event-specific temporal patterns
EVENT_TEMPORAL_PATTERNS = {
    'Natural_Disaster': [
        r'hurricane\s+\w+\s+(?:is\s+)?(?:expected|forecast|predicted)\s+to\s+(?:make\s+landfall|hit|strike)\s+(?:on|by)?\s*([^.]+)',
        r'storm\s+(?:expected|forecast|projected)\s+to\s+(?:arrive|reach|hit)\s+(?:on|by)?\s*([^.]+)',
        r'typhoon\s+\w+\s+(?:approaching|heading\s+toward)\s+.*?(?:on|by)\s+([^.]+)',
        r'earthquake\s+(?:predicted|forecast)\s+(?:for|on)\s+([^.]+)',
    ],
    'Labor_Issue': [
        r'strike\s+(?:scheduled|planned|set)\s+(?:for|to\s+begin)\s+(?:on)?\s*([^.]+)',
        r'workers\s+(?:will|to)\s+strike\s+(?:on|starting)\s+([^.]+)',
        r'union\s+(?:plans|threatens)\s+(?:to\s+)?strike\s+(?:on|by)\s+([^.]+)',
        r'walkout\s+(?:planned|scheduled)\s+(?:for|on)\s+([^.]+)',
    ],
    'Political_Regulatory': [
        r'(?:sanctions|tariffs|regulations?)\s+(?:will|to)\s+(?:take\s+effect|be\s+implemented)\s+(?:on|by)\s+([^.]+)',
        r'(?:law|policy|rule)\s+(?:goes|takes)\s+into\s+effect\s+(?:on)?\s*([^.]+)',
        r'(?:ban|restriction)\s+(?:begins|starts|effective)\s+(?:on)?\s*([^.]+)',
    ],
    'Logistics_Issue': [
        r'port\s+(?:closure|shutdown)\s+(?:scheduled|planned|expected)\s+(?:for|on)\s+([^.]+)',
        r'blockade\s+(?:expected|planned|threatened)\s+(?:for|on)\s+([^.]+)',
        r'shipment\s+(?:delays?|disruption)\s+(?:expected|anticipated)\s+(?:until|through)\s+([^.]+)',
    ]
}


def extract_dates_with_spacy(text):
    """Extract dates using spaCy NER."""
    if not nlp:
        return []
    
    doc = nlp(text)
    dates = []
    for ent in doc.ents:
        if ent.label_ == "DATE":
            dates.append(ent.text)
    return dates


def extract_dates_with_regex(text):
    """Extract dates using regex patterns."""
    dates = []
    for pattern in DATE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        dates.extend(matches)
    return dates


def parse_relative_date(text, reference_date=None):
    """
    Attempts to parse relative dates like 'next week', 'tomorrow', etc.
    Returns a datetime object or None.
    """
    if reference_date is None:
        reference_date = datetime.now()
    
    text_lower = text.lower()
    
    # Check time horizon keywords
    for horizon, config in TIME_HORIZON_KEYWORDS.items():
        for keyword in config['keywords']:
            if keyword in text_lower:
                return reference_date + timedelta(days=config['days_offset'])
    
    return None


def parse_absolute_date(date_string, reference_date=None):
    """
    Attempts to parse absolute dates like 'July 15, 2025' or '2025-07-15'.
    Returns a datetime object or None.
    """
    if reference_date is None:
        reference_date = datetime.now()
    
    try:
        # Try using dateutil parser (very flexible)
        parsed_date = date_parser.parse(date_string, fuzzy=True, default=reference_date)
        
        # If year wasn't specified and date is in the past, assume next year
        if parsed_date < reference_date and parsed_date.year == reference_date.year:
            parsed_date = parsed_date.replace(year=parsed_date.year + 1)
        
        return parsed_date
    except:
        return None


def _is_useful_temporal_phrase(phrase, reference_date):
    """Filter noisy temporal phrases that usually create false future dates."""
    if not phrase:
        return False

    p = phrase.strip().lower()
    if not p:
        return False

    # Skip ages and generic numerics frequently captured by NER.
    if re.fullmatch(r'\d{1,3}', p) or re.fullmatch(r'\d{1,3}-year-old', p):
        return False

    # Skip historical references.
    if any(token in p for token in ['ago', 'last year', 'century', 'invasion', 'war']):
        return False

    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', p)
    if year_match:
        year = int(year_match.group(1))
        if year < reference_date.year:
            return False

    return True


def extract_event_temporal_context(event):
    """
    Extracts temporal information from an event to determine WHEN it's predicted to occur.
    Returns a dictionary with temporal metadata.
    """
    text = event.get('event_text_segment', '')
    event_types = event.get('potential_event_types', [])
    article_timestamp = event.get('article_timestamp')
    
    # Determine reference date (when the article was published)
    if article_timestamp:
        try:
            reference_date = datetime.fromisoformat(article_timestamp.replace('Z', '+00:00'))
        except:
            reference_date = datetime.now()
    else:
        reference_date = datetime.now()
    
    temporal_info = {
        'is_predictive': False,
        'predicted_date': None,
        'predicted_date_confidence': 'none',  # none, low, medium, high
        'time_horizon': 'unknown',  # immediate, short, medium, long
        'days_until_event': None,
        'extracted_temporal_phrases': []
    }
    
    # Check if article contains predictive language
    text_lower = text.lower()
    indicator_hit = any(indicator in text_lower for indicator in PREDICTIVE_INDICATORS)
    strong_future_hit = any(re.search(pattern, text_lower) for pattern in STRONG_PREDICTIVE_PATTERNS)
    historical_context_hit = sum(1 for pattern in HISTORICAL_CONTEXT_PATTERNS if re.search(pattern, text_lower))

    if indicator_hit and strong_future_hit and historical_context_hit <= 2:
        temporal_info['is_predictive'] = True
    
    # Extract dates using multiple methods
    extracted_dates = []
    
    # Method 1: spaCy NER
    spacy_dates = extract_dates_with_spacy(text)
    extracted_dates.extend(spacy_dates)
    
    # Method 2: Regex patterns
    regex_dates = extract_dates_with_regex(text)
    extracted_dates.extend(regex_dates)
    
    # Method 3: Event-specific patterns
    for event_type in event_types:
        if event_type in EVENT_TEMPORAL_PATTERNS:
            for pattern in EVENT_TEMPORAL_PATTERNS[event_type]:
                matches = re.findall(pattern, text, re.IGNORECASE)
                extracted_dates.extend(matches)
    
    extracted_dates = [d for d in extracted_dates if _is_useful_temporal_phrase(d, reference_date)]
    temporal_info['extracted_temporal_phrases'] = list(set(extracted_dates))
    
    # Try to parse the extracted dates
    parsed_dates = []
    for date_str in extracted_dates:
        # Try absolute date parsing first
        abs_date = parse_absolute_date(date_str, reference_date)
        if abs_date:
            parsed_dates.append(abs_date)
            continue
        
        # Try relative date parsing
        rel_date = parse_relative_date(date_str, reference_date)
        if rel_date:
            parsed_dates.append(rel_date)
    
    # If we found dates, use the earliest near-future date within operational window.
    future_dates = [
        d for d in parsed_dates
        if d >= reference_date and (d - reference_date).days <= MAX_PREDICTION_DAYS
    ]
    if future_dates:
        predicted_date = min(future_dates)
        temporal_info['predicted_date'] = predicted_date.isoformat()
        temporal_info['days_until_event'] = (predicted_date - reference_date).days
        
        # Determine confidence based on how we found the date
        if len(extracted_dates) > 1:
            temporal_info['predicted_date_confidence'] = 'high'
        else:
            temporal_info['predicted_date_confidence'] = 'medium'
        
        # Determine time horizon
        days_until = temporal_info['days_until_event']
        if days_until <= 1:
            temporal_info['time_horizon'] = 'immediate'
        elif days_until <= 7:
            temporal_info['time_horizon'] = 'short'
        elif days_until <= 30:
            temporal_info['time_horizon'] = 'medium'
        else:
            temporal_info['time_horizon'] = 'long'
    
    # If no specific dates found but is predictive, use time horizon keywords
    elif temporal_info['is_predictive']:
        for horizon, config in TIME_HORIZON_KEYWORDS.items():
            if any(keyword in text_lower for keyword in config['keywords']):
                temporal_info['time_horizon'] = horizon
                days_offset = config['days_offset']
                predicted_date = reference_date + timedelta(days=days_offset)
                temporal_info['predicted_date'] = predicted_date.isoformat()
                temporal_info['days_until_event'] = days_offset
                temporal_info['predicted_date_confidence'] = 'low'
                break
    
    return temporal_info


def enrich_events_with_temporal_data(events):
    """
    Enriches all events with temporal extraction data.
    """
    print(f"🕐 Extracting temporal information from {len(events)} events...")
    
    enriched_events = []
    predictive_count = 0
    
    for event in events:
        temporal_info = extract_event_temporal_context(event)
        event['temporal_info'] = temporal_info
        
        if temporal_info['is_predictive']:
            predictive_count += 1
        
        enriched_events.append(event)
    
    print(f"✅ Temporal extraction complete. Found {predictive_count} predictive events.")
    return enriched_events


def save_temporal_enriched_data(events, output_path="data/processed/temporal_enriched_events.jsonl"):
    """Saves events with temporal information."""
    print(f"💾 Saving {len(events)} temporally enriched events to {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        for event in events:
            json.dump(event, f, ensure_ascii=False)
            f.write('\n')
    print(f"✅ Temporal data saved.")


def load_matched_events(filepath="data/processed/matched_events.jsonl"):
    """Loads matched events (post node-matching step)."""
    if not os.path.exists(filepath):
        print(f"❌ Error: Matched events file not found at {filepath}")
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f]


if __name__ == "__main__":
    # Load matched events (includes matched_node from step 5)
    scored_events = load_matched_events()

    if scored_events:
        # Enrich with temporal data
        enriched_events = enrich_events_with_temporal_data(scored_events)
        
        # Save enriched data
        save_temporal_enriched_data(enriched_events)
        
        # Print some examples of predictive events
        predictive_events = [e for e in enriched_events if e['temporal_info']['is_predictive']]
        print(f"\n📊 Found {len(predictive_events)} predictive/forward-looking events")
        
        if predictive_events:
            print("\n🔮 Example Predictive Events:")
            for event in predictive_events[:5]:
                print(f"\n  Node: {event.get('matched_node', 'N/A')}")
                print(f"  Types: {event.get('potential_event_types', [])}")
                print(f"  Predicted Date: {event['temporal_info'].get('predicted_date', 'Unknown')}")
                print(f"  Days Until: {event['temporal_info'].get('days_until_event', 'Unknown')}")
                print(f"  Time Horizon: {event['temporal_info'].get('time_horizon', 'Unknown')}")
                print(f"  Confidence: {event['temporal_info'].get('predicted_date_confidence', 'Unknown')}")
                print(f"  Text: {event.get('event_text_segment', '')[:200]}...")
    else:
        print("🤷 No scored events found. Run risk_scoring.py first.")

