# src/match_events_to_nodes.py
"""
This script matches geocoded events to supplier nodes based on location proximity.
It adds the 'matched_node' field to events.
"""

import json
import os
from math import radians, sin, cos, sqrt, atan2

# Supplier nodes with their locations (from load_to_db.py)
SUPPLIER_NODES = {
    "TSMC_Hsinchu": {"latitude": 24.8016, "longitude": 120.9716, "country": "Taiwan", "criticality": 5},
    "Foxconn_Zhengzhou": {"latitude": 34.7466, "longitude": 113.6253, "country": "China", "criticality": 5},
    "Port_of_Long_Beach": {"latitude": 33.7542, "longitude": -118.2165, "country": "USA", "criticality": 4},
    "Albemarle_Chile": {"latitude": -23.5869, "longitude": -68.1533, "country": "Chile", "criticality": 3},
    "CATL_Ningde": {"latitude": 26.6577, "longitude": 119.5262, "country": "China", "criticality": 4},
    "Tesla_Berlin": {"latitude": 52.4045, "longitude": 13.7845, "country": "Germany", "criticality": 3},
}

# Target locations that events might reference (from geocoding.py)
# Enhanced with more keywords to capture unmatched events
TARGET_LOCATIONS_KEYWORDS = {
    'Taiwan': ['Taiwan', 'Taipei', 'Hsinchu', 'Kaohsiung', 'TSMC', 'semiconductor', 'chip manufacturing', 'Taiwan Strait'],
    'China': ['China', 'Chinese', 'Beijing', 'Shanghai', 'Shenzhen', 'Guangzhou', 'Zhengzhou', 'Ningde', 'Foxconn', 'CATL', 'Henan'],
    # Keep Strategy 1 focused on geographic anchors; generic logistics terms are handled in fallback scoring.
    'USA': ['USA', 'United States', 'California', 'Long Beach', 'Los Angeles', 'West Coast', 'California coast', 'Port Authority'],
    'Germany': ['Germany', 'German', 'Berlin', 'Munich', 'Hamburg', 'Tesla', 'Brandenburg', 'Gigafactory'],
    'Chile': ['Chile', 'Chilean', 'Santiago', 'Atacama', 'Albemarle', 'lithium', 'South America'],
    'Hong Kong': ['Hong Kong', 'HK', 'Hongkong'],
    'Europe': ['Europe', 'European', 'EU', 'Germany', 'Berlin'],
}


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on Earth (in km).
    """
    R = 6371  # Earth's radius in kilometers
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c
    
    return distance


def match_event_to_node(event):
    """
    Matches an event to the nearest supplier node based on:
    1. Location keywords match (country/region) - checks extracted locations, geocoded text, AND article text
    2. Geographic distance (if coordinates available)
    3. Fallback: Most events likely match to a default node based on sector
    
    Returns the matched node name or None.
    """
    extracted_locations = event.get('extracted_locations', [])
    event_lat = event.get('latitude')
    event_lon = event.get('longitude')
    geocoded_text = event.get('geocoded_location_text', '')
    
    # Strategy 1: Match by location keywords
    # Check extracted location, geocoded location, article title, and event text
    article_title = event.get('article_title', '').lower()
    event_text_segment = event.get('event_text_segment', '').lower()
    
    # Build comprehensive search text
    all_location_texts = extracted_locations + [geocoded_text, article_title, event_text_segment]
    
    for location_text in all_location_texts:
        if not location_text:
            continue
            
        location_lower = str(location_text).lower()
        
        # Try to match to a specific country
        for country, keywords in TARGET_LOCATIONS_KEYWORDS.items():
            if any(keyword.lower() in location_lower for keyword in keywords):
                # Find a node in this country
                matching_nodes = [node_name for node_name, node_data in SUPPLIER_NODES.items() 
                                if node_data['country'] == country]
                if matching_nodes:
                    # If multiple nodes in the country, prefer the one with highest criticality
                    best_node = max(matching_nodes, 
                                  key=lambda n: SUPPLIER_NODES[n]['criticality'])
                    return best_node
    
    # Strategy 2: Match by geographic proximity (if we have coordinates)
    # Use a tiered distance threshold: prefer closer nodes, but relax threshold if needed
    if event_lat is not None and event_lon is not None:
        closest_node = None
        min_distance = float('inf')
        
        for node_name, node_data in SUPPLIER_NODES.items():
            distance = haversine_distance(
                event_lat, event_lon,
                node_data['latitude'], node_data['longitude']
            )
            
            if distance < min_distance:
                min_distance = distance
                closest_node = node_name
        
        # Tiered distance threshold:
        # - If close match (< 500km), use it
        # - If reasonable match (< 2000km), use it
        # - If only moderate match (< 4000km) and we have no better option, use it
        if min_distance < 500:
            return closest_node
        elif min_distance < 2000:
            return closest_node
        elif min_distance < 4000 and closest_node:
            # Only use if no keyword match found above
            return closest_node
    
    # Strategy 3: Fallback based on event type
    # If no geographic match, try to infer from event type and keywords
    # BUT: Only use fallback if we have strong confidence (multiple matching keywords)
    event_text_lower = event_text_segment.lower() if event_text_segment else ""
    article_lower = article_title.lower() if article_title else ""
    combined_text = (event_text_lower + " " + article_lower).lower()
    
    # Prefer explicit node anchors (company/facility names) before generic category fallback.
    node_anchor_keywords = {
        'TSMC_Hsinchu': ['tsmc', 'hsinchu', 'taiwan strait', 'wafer fab'],
        'Foxconn_Zhengzhou': ['foxconn', 'zhengzhou', 'hon hai'],
        'CATL_Ningde': ['catl', 'ningde', 'ev battery'],
        'Port_of_Long_Beach': ['long beach', 'los angeles port', 'port authority', 'la port', 'california port'],
        'Albemarle_Chile': ['albemarle', 'atacama', 'lithium brine', 'chilean lithium'],
        'Tesla_Berlin': ['tesla', 'gigafactory', 'brandenburg', 'berlin plant'],
    }

    node_anchor_scores = {
        node: sum(1 for word in keywords if word in combined_text)
        for node, keywords in node_anchor_keywords.items()
    }
    best_anchor_node = max(node_anchor_scores, key=node_anchor_scores.get)
    if node_anchor_scores[best_anchor_node] > 0:
        return best_anchor_node

    # Count how many keywords match for each category
    manufacturing_keywords = ['manufacturing', 'factory', 'production', 'fab']
    logistics_keywords = ['port', 'shipping', 'logistics', 'cargo', 'container', 'freight', 'maritime']
    mining_keywords = ['mining', 'lithium', 'rare earth', 'mineral', 'extraction']
    chip_keywords = ['chip', 'semiconductor', 'processor', 'wafer']
    
    manufacturing_score = sum(1 for word in manufacturing_keywords if word in combined_text)
    logistics_score = sum(1 for word in logistics_keywords if word in combined_text)
    mining_score = sum(1 for word in mining_keywords if word in combined_text)
    chip_score = sum(1 for word in chip_keywords if word in combined_text)
    
    # Only apply fallback if we have strong evidence (at least 2+ keyword matches)
    max_score = max(manufacturing_score, logistics_score, mining_score, chip_score)
    
    if max_score >= 2:
        if chip_score == max_score:
            return 'TSMC_Hsinchu'
        elif mining_score == max_score:
            return 'Albemarle_Chile'
        elif logistics_score == max_score:
            # Avoid over-assigning global logistics events to Long Beach unless text contains US/West Coast anchors.
            us_port_anchors = ['usa', 'united states', 'california', 'long beach', 'los angeles', 'west coast', 'port authority']
            has_us_anchor = any(word in combined_text for word in us_port_anchors)
            if has_us_anchor:
                return 'Port_of_Long_Beach'
            return None
        elif manufacturing_score == max_score:
            # Manufacturing: prefer Tesla for EV/automotive, Foxconn otherwise
            if any(word in combined_text for word in ['ev', 'electric', 'automotive', 'vehicle', 'tesla']):
                return 'Tesla_Berlin'
            else:
                return 'Foxconn_Zhengzhou'
    
    return None


def load_geocoded_events(filepath="data/processed/geocoded_events.jsonl"):
    """Load geocoded events from JSONL file."""
    if not os.path.exists(filepath):
        print(f"❌ Error: Geocoded events file not found at {filepath}")
        return []
    
    print(f"Loading geocoded events from {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        events = [json.loads(line) for line in f]
    print(f"✅ Loaded {len(events)} geocoded events")
    return events


def save_matched_events(events, output_path="data/processed/matched_events.jsonl"):
    """Save events with matched_node field to JSONL file."""
    print(f"💾 Saving {len(events)} matched events to {output_path}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for event in events:
            json.dump(event, f, ensure_ascii=False)
            f.write('\n')
    print(f"✅ Matched events saved to {output_path}")


def main():
    """Main function to match events to nodes."""
    # Load geocoded events
    events = load_geocoded_events()
    if not events:
        print("No events to process.")
        return
    
    # Match each event to a node
    matched_count = 0
    unmatched_count = 0
    
    print(f"\n🔍 Matching {len(events)} events to supplier nodes...")
    for i, event in enumerate(events):
        if i % 100 == 0:
            print(f"  Processing event {i+1}/{len(events)}...")
        
        matched_node = match_event_to_node(event)
        event['matched_node'] = matched_node
        
        if matched_node:
            matched_count += 1
        else:
            unmatched_count += 1
    
    print(f"\n📊 Matching Results:")
    print(f"  ✅ Matched: {matched_count} events")
    print(f"  ❌ Unmatched: {unmatched_count} events")
    print(f"  📈 Match rate: {matched_count/len(events)*100:.1f}%")
    
    # Save the matched events
    save_matched_events(events)
    
    # Print distribution by node
    print(f"\n📍 Events by Node:")
    node_counts = {}
    for event in events:
        node = event.get('matched_node', 'Unmatched')
        node_counts[node] = node_counts.get(node, 0) + 1
    
    for node, count in sorted(node_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {node}: {count} events")


if __name__ == "__main__":
    main()
