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

def calculate_risk_score(event):
    """Calculates an enhanced risk score incorporating context, sentiment, and urgency."""
    event_text = event.get('event_text_segment', '').lower()
    article_title = event.get('article_title', '').lower()
    event_types = event.get('potential_event_types', [])
    combined_text = f"{article_title} {event_text}".strip()

    if not event_text:
        return 0.0

    if any(keyword in combined_text for keyword in NON_SUPPLY_CHAIN_CONTENT_KEYWORDS) and not any(
        keyword in combined_text for keyword in CONCRETE_DISRUPTION_KEYWORDS
    ):
        return 0.0

    # 1. Context Check: Must be related to supply chain to have any score
    if not any(keyword in combined_text for keyword in SUPPLY_CHAIN_CONTEXT_KEYWORDS):
        return 0.0

    # 1b. Require a concrete disruption signal, not just a generic supply-chain noun.
    if not any(keyword in combined_text for keyword in CONCRETE_DISRUPTION_KEYWORDS):
        return 0.0

    # 2. Base Score from Event Types (sum of weights for all identified types)
    base_score = sum(SCORE_WEIGHTS.get(etype, 0) for etype in event_types)
    if base_score == 0:
        return 0.0 # No recognized event types means no inherent risk

    # 3. Apply Multipliers: Sentiment and Urgency
    sentiment_mod = get_sentiment_modifier(event_text)
    urgency_mod = get_urgency_modifier(event_text)
    score_with_mods = base_score * sentiment_mod * urgency_mod

    # 4. Additive Boosts: Intensifiers
    intensifier_boost = sum(boost for keyword, boost in INTENSIFIER_KEYWORDS.items() if keyword in event_text)
    score_with_boost = score_with_mods + intensifier_boost

    # 5. Penalties: Commentary Language
    # If the article uses a lot of commentary verbs, it might be less about direct action.
    if any(verb in event_text for verb in COMMENTARY_VERBS):
        final_score = score_with_boost * 0.7 # Reduce score by 30% if it's commentary. Adjust as needed.
    else:
        final_score = score_with_boost

    # Ensure score is non-negative and round for cleaner values
    return round(max(0, final_score), 2)

def score_all_events(events):
    """Iterates through all filtered events and calculates a risk score for each."""
    print(f"📈 Calculating enhanced risk scores for {len(events)} events...")
    for event in events:
        event['risk_score'] = calculate_risk_score(event)
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