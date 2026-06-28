# src/filter_events.py

import json
import os
import re

# --- Configuration for Filtering ---

# Keywords that MUST be present to consider an event supply chain relevant
# These are broad categories, more specific context keywords are in risk_scoring.py
SUPPLY_CHAIN_PRIMARY_KEYWORDS = [
    'supply chain', 'logistics', 'shipping', 'freight', 'cargo', 'port', 'harbor',
    'factory', 'plant', 'manufacturing', 'production', 'assembly',
    'export', 'import', 'trade', 'customs', 'border', 'shipment',
    'warehouse', 'distribution', 'supplier', 'component', 'material', 'semiconductor',
    'oil', 'gas', 'metal', 'mine', 'farm', 'food', 'retail', 'e-commerce',
    'delivery', 'transport', 'road', 'rail', 'air'
]

# Keywords/Phrases indicating the article is NOT about a *current, concrete* event
# These suggest speculation, opinion, debate, future plans, or general commentary.
# Add more as you identify patterns in irrelevant articles.
SPECULATIVE_OR_OPINION_KEYWORDS = [
    'could impact', 'might affect', 'potential impact', 'likely to', 'unlikely to',
    'should be', 'ought to be', 'needs to be', 'calls for', 'debate over',
    'opinion on', 'analysis of', 'future of', 'question of', 'is it ethical',
    'will X happen', 'how to solve', 'examines whether', 'considering a',
    'proposes to', 'think about', 'asks if', 'discussion around', 'commentary',
    'foreseeable', 'speculation', 'speculates', 'could lead to', 'may lead to',
    'what if', 'outlook for', 'prediction', 'prognosis', 'consequences of',
    'ramifications of', 'argument for', 'argument against', 'blog post',
    'editorial', 'review of', 'examining the', 'deliberate', 'ponder'
]

# Keywords/Phrases in the article title or URL that indicate it's not a real event
TITLE_URL_NEGATIVE_FILTERS = [
    'opinion', 'analysis', 'debate', 'explainer', 'comment', 'outlook',
    'review', 'podcast', 'video', 'newsletter', 'faq', 'guide', 'blog', 'column'
]

SUSPICIOUS_NON_SUPPLY_CHAIN_CONTEXT = [
    'festival', 'theatre', 'theater', 'play', 'poem', 'poetry', 'novel', 'fiction',
    'art', 'arts', 'music', 'film', 'movie', 'book', 'literary', 'shakespeare'
]

DIRECT_DISRUPTION_KEYWORDS = [
    'strike', 'walkout', 'shutdown', 'closed', 'halted', 'delay', 'delays', 'fire',
    'explosion', 'spill', 'outage', 'shortage', 'blockade', 'embargo', 'sanction',
    'tariff', 'hack', 'cyberattack', 'ransomware', 'breach', 'earthquake', 'flood',
    'storm', 'hurricane', 'typhoon', 'wildfire', 'accident', 'disruption', 'recall'
]


def _contains_keyword(text, keyword):
    if ' ' in keyword:
        return keyword in text
    return re.search(rf'\b{re.escape(keyword)}\b', text) is not None


# --- Helper Functions ---
def is_irrelevant_speculation_or_opinion(event_text_segment, article_title):
    """
    Checks if the article's text or title suggests it's speculative, opinion-based,
    or not about a concrete, unfolding event.
    """
    text_lower = event_text_segment.lower()
    title_lower = article_title.lower() if article_title else ""

    # Check for speculative/opinion keywords in the main text
    if any(keyword in text_lower for keyword in SPECULATIVE_OR_OPINION_KEYWORDS):
        return True

    # Check for negative filters in the title/URL (less common but effective for specific sources)
    if any(keyword in title_lower for keyword in TITLE_URL_NEGATIVE_FILTERS):
        return True

    if any(keyword in text_lower for keyword in SUSPICIOUS_NON_SUPPLY_CHAIN_CONTEXT) and not any(
        keyword in text_lower for keyword in ('factory fire', 'port congestion', 'shipping', 'freight', 'cargo', 'shutdown', 'strike')
    ):
        return True
        
    return False

def has_supply_chain_context(event_text_segment, article_title=""):
    """
    Checks if the article has strong enough keywords to be considered supply chain relevant.
    This acts as a basic filter to reduce noise before detailed risk scoring.
    """
    text_lower = f"{article_title} {event_text_segment}".lower().strip()
    if any(_contains_keyword(text_lower, keyword) for keyword in SUPPLY_CHAIN_PRIMARY_KEYWORDS):
        return True
    return False


def has_direct_disruption_signal(event_text_segment, article_title=""):
    text_lower = f"{article_title} {event_text_segment}".lower().strip()
    return any(_contains_keyword(text_lower, keyword) for keyword in DIRECT_DISRUPTION_KEYWORDS)

# --- Core Filtering Logic ---
def load_preprocessed_data(filepath="data/processed/processed_events.jsonl"):
    """Loads preprocessed article data."""
    if not os.path.exists(filepath):
        print(f"❌ Error: Preprocessed data file not found at {filepath}")
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f]

def filter_events(preprocessed_articles):
    """
    Filters articles based on:
    1. Presence of supply chain related keywords.
    2. Absence of speculative or opinion-based language.
    3. Presence of identified event types.
    """
    print(f"📊 Starting to filter {len(preprocessed_articles)} preprocessed articles...")
    filtered_events = []
    
    for article in preprocessed_articles:
        text_segment = article.get('event_text_segment', '')
        potential_event_types = article.get('potential_event_types', [])
        article_title = article.get('article_title', '')
        article_url = article.get('article_url', '') # Use for debugging, not direct filtering here currently

        # Filter 1: Must have at least one recognized event type
        if not potential_event_types:
            # print(f"  Skipping (no event type): {article_title[:70]}...")
            continue

        # Filter 2: Must contain supply chain context, or a direct disruption signal paired with a real event type.
        if not has_supply_chain_context(text_segment, article_title):
            if not (potential_event_types and has_direct_disruption_signal(text_segment, article_title)):
                # print(f"  Skipping (no SC context): {article_title[:70]}...")
                continue

        # Filter 3: New - Must NOT be overly speculative or opinionated
        if is_irrelevant_speculation_or_opinion(text_segment, article_title):
            # print(f"  Skipping (speculative/opinion): {article_title[:70]}...")
            continue
            
        filtered_events.append(article)
    
    print(f"✅ Filtering complete. {len(filtered_events)} events passed filters.")
    return filtered_events

def save_filtered_data(filtered_events, output_path="data/processed/filtered_events.jsonl"):
    """Saves the filtered events to a new JSONL file."""
    print(f"💾 Saving {len(filtered_events)} filtered events to {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        for event in filtered_events:
            json.dump(event, f, ensure_ascii=False)
            f.write('\n')
    print(f"✅ Filtered data saved.")

if __name__ == "__main__":
    preprocessed_data = load_preprocessed_data()
    if preprocessed_data:
        filtered_results = filter_events(preprocessed_data)
        save_filtered_data(filtered_results)
    else:
        print("🤷 No preprocessed data to filter.")