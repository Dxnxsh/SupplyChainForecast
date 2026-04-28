# src/risk_scoring.py

import json
import os
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# --- NLP Model Initialization ---
analyzer = SentimentIntensityAnalyzer()

# --- Configuration: Scoring Logic ---
SCORE_WEIGHTS = {
    'Natural_Disaster': 10,
    'Industrial_Accident': 9,
    'Political_Regulatory': 8,
    'Logistics_Issue': 7,
    'Cyber_Attack': 8,
    'Labor_Issue': 6,
    'Demand_Supply_Shift': 5,
}

# Keywords to ensure the event is supply chain relevant
SUPPLY_CHAIN_CONTEXT_KEYWORDS = [
    'supply chain', 'logistics', 'shipping', 'freight', 'cargo', 'port', 'harbor',
    'factory', 'plant', 'manufacturing', 'production', 'assembly',
    'export', 'import', 'trade', 'customs', 'border', 'shipment',
    'warehouse', 'distribution', 'supplier', 'component', 'material',
    'semiconductor', 'chip', 'battery', 'electric vehicle' # Added more specific industry terms
]

CONCRETE_DISRUPTION_KEYWORDS = [
    'strike', 'walkout', 'shutdown', 'closed', 'halted', 'delay', 'delays', 'fire',
    'explosion', 'spill', 'outage', 'shortage', 'blockade', 'embargo', 'sanction',
    'tariff', 'hack', 'cyberattack', 'ransomware', 'breach', 'earthquake', 'flood',
    'storm', 'hurricane', 'typhoon', 'wildfire', 'accident', 'disruption', 'recall',
    'port congestion', 'port closure', 'trade war', 'export ban', 'import restrictions'
]

NON_SUPPLY_CHAIN_CONTENT_KEYWORDS = [
    'festival', 'theatre', 'theater', 'play', 'poetry', 'poem', 'novel', 'art',
    'music', 'film', 'movie', 'book', 'review', 'commentary', 'opinion', 'literary',
    'shakespeare'
]

# Keywords that suggest the article is about commentary or future possibility, not direct action
COMMENTARY_VERBS = [
    'says', 'said', 'thinks', 'believes', 'argues', 'suggests', 'warns',
    'commented', 'stated', 'announced', 'claims', 'accused', 'told',
    'expects', 'predicts', 'forecasts', 'speculates' # Added more commentary verbs
]

# Keywords that intensify the severity of an event
INTENSIFIER_KEYWORDS = {
    "severe": 2, "major": 2, "catastrophic": 3, "complete shutdown": 3,
    "blockade": 2, "prolonged": 1, "critical": 1, "crisis": 1, "emergency": 1,
    "crippling": 2, "devastating": 3, "disruptive": 1, "severe shortage": 2
}

# Keywords indicating the urgency of the event
URGENCY_KEYWORDS = {
    'high': ['now', 'breaking', 'underway', 'halted', 'closed', 'on fire', 'evacuated', 'immediate', 'has stopped', 'shut down'],
    'medium': ['developing', 'escalating', 'worsening', 'ongoing', 'approaching', 'expected to'],
    'low': ['planned', 'potential', 'threatens', 'could', 'may', 'scheduled for', 'next week', 'next month', 'considering', 'analysts believe']
}

# --- Helper Functions for Scoring ---
def _contains_any_keyword(text, keywords):
    return any(keyword in text for keyword in keywords)


def get_sentiment_modifier(text):
    """Returns a modifier based on sentiment compound score. Negative sentiment boosts risk, positive reduces it."""
    score = analyzer.polarity_scores(text)['compound']
    if score <= -0.5: return 1.5  # Very negative: +50%
    if score <= -0.1: return 1.2  # Negative: +20%
    if score >= 0.5: return 0.5   # Very positive (e.g., "strike resolved"): -50%
    return 1.0                    # Neutral

def get_urgency_modifier(text):
    """Returns a modifier based on urgency keywords. High urgency boosts risk, low reduces it."""
    lower_text = text.lower()
    if any(keyword in lower_text for keyword in URGENCY_KEYWORDS['high']): return 1.25
    if any(keyword in lower_text for keyword in URGENCY_KEYWORDS['medium']): return 1.1
    if any(keyword in lower_text for keyword in URGENCY_KEYWORDS['low']): return 0.7
    return 1.0

# --- Core Scoring Logic ---
def load_filtered_data(filepath="data/processed/filtered_events.jsonl"):
    """Loads the filtered event data."""
    if not os.path.exists(filepath):
        print(f"❌ Error: Filtered data file not found at {filepath}")
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f]


def calculate_relevance_score(event):
    """Scores how directly an event is relevant to supply chain risk."""
    event_text = event.get('event_text_segment', '').lower()
    article_title = event.get('article_title', '').lower()
    extracted_locations = event.get('extracted_locations') or []
    matched_node = event.get('matched_node')
    event_types = event.get('potential_event_types', [])
    combined_text = f"{article_title} {event_text}".strip()

    if not event_text:
        return 0.0

    disruption_hit = _contains_any_keyword(combined_text, CONCRETE_DISRUPTION_KEYWORDS)
    context_hit = _contains_any_keyword(combined_text, SUPPLY_CHAIN_CONTEXT_KEYWORDS)
    specificity_hit = bool(extracted_locations) or bool(matched_node)
    event_type_hit = bool(event_types)

    if _contains_any_keyword(combined_text, NON_SUPPLY_CHAIN_CONTENT_KEYWORDS) and not disruption_hit:
        return 0.0

    if not any([context_hit, disruption_hit, specificity_hit, event_type_hit]):
        return 0.0

    relevance_score = 0.0
    if context_hit:
        relevance_score += 35.0
    if event_type_hit:
        relevance_score += 25.0
    if disruption_hit:
        relevance_score += 30.0
    if specificity_hit:
        relevance_score += 10.0

    if _contains_any_keyword(event_text, COMMENTARY_VERBS) and not disruption_hit:
        relevance_score *= 0.8

    return round(min(100.0, relevance_score), 2)


def calculate_severity_score(event):
    """Calculates severity once relevance is established."""
    event_text = event.get('event_text_segment', '').lower()
    article_title = event.get('article_title', '').lower()
    event_types = event.get('potential_event_types', [])
    combined_text = f"{article_title} {event_text}".strip()
    disruption_hit = _contains_any_keyword(combined_text, CONCRETE_DISRUPTION_KEYWORDS)

    if not event_text or not event_types:
        return 0.0

    base_score = sum(SCORE_WEIGHTS.get(etype, 0) for etype in event_types)
    if base_score == 0:
        return 0.0

    sentiment_mod = get_sentiment_modifier(event_text)
    urgency_mod = get_urgency_modifier(event_text)
    score_with_mods = base_score * sentiment_mod * urgency_mod

    intensifier_boost = sum(boost for keyword, boost in INTENSIFIER_KEYWORDS.items() if keyword in event_text)
    score_with_boost = score_with_mods + intensifier_boost

    if any(verb in event_text for verb in COMMENTARY_VERBS):
        score_with_boost *= 0.7

    if not disruption_hit:
        score_with_boost *= 0.8

    # Broad geopolitical or macro headlines should not reach the top risk band
    # unless they contain a concrete disruption signal.
    if not disruption_hit:
        if 'Political_Regulatory' in event_types and 'Natural_Disaster' in event_types:
            score_with_boost = min(score_with_boost, 6.5)
        elif 'Political_Regulatory' in event_types:
            score_with_boost = min(score_with_boost, 7.0)
        elif 'Natural_Disaster' in event_types:
            score_with_boost = min(score_with_boost, 8.0)
        elif 'Labor_Issue' in event_types:
            score_with_boost = min(score_with_boost, 7.5)
        else:
            score_with_boost = min(score_with_boost, 9.5)

    return round(max(0, score_with_boost), 2)


def calculate_risk_components(event):
    """Returns relevance, severity, and final risk score for an event."""
    relevance_score = calculate_relevance_score(event)
    severity_score = calculate_severity_score(event)
    risk_score = round(severity_score * (relevance_score / 100.0), 2)

    return {
        'risk_relevance_score': relevance_score,
        'risk_severity_score': severity_score,
        'risk_score': risk_score,
    }

def calculate_risk_score(event):
    """Calculates the final risk score for backward compatibility."""
    return calculate_risk_components(event)['risk_score']

def score_all_events(events):
    """Iterates through all filtered events and calculates a risk score for each."""
    print(f"📈 Calculating enhanced risk scores for {len(events)} events...")
    for event in events:
        event.update(calculate_risk_components(event))
    print("✅ Risk scoring complete.")
    return events

def save_scored_data(scored_events, output_path="data/processed/scored_events.jsonl"):
    """Saves the events with their calculated risk scores."""
    print(f"💾 Saving {len(scored_events)} scored events to {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        for entry in scored_events:
            json.dump(entry, f, ensure_ascii=False)
            f.write('\n')
    print(f"✅ Scored data saved.")

if __name__ == "__main__":
    filtered_events = load_filtered_data()
    
    if filtered_events:
        scored_events = score_all_events(filtered_events)
        
        # Optional: Print some high-scoring events for quick validation
        # high_risk_events = sorted([e for e in scored_events if e['risk_score'] > 0], key=lambda x: x['risk_score'], reverse=True)
        # print("\nTop 5 High-Risk Events (after enhanced scoring):")
        # for event in high_risk_events[:5]:
        #     print(f"  Score: {event['risk_score']:.1f}, Node: {event['matched_node']}, Types: {event['potential_event_types']}, Text: {event['event_text_segment'][:150]}...")

        save_scored_data(scored_events)
    else:
        print("🤷 No filtered events loaded, skipping risk scoring.")