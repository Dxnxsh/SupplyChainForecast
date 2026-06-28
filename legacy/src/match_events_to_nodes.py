# src/match_events_to_nodes.py
"""
This script matches geocoded events to supplier nodes based on location proximity.
It adds the 'matched_node' field to events.
"""

import json
import os
from math import radians, sin, cos, sqrt, atan2

from src.load_to_db import SUPPLIER_NODES

# Target locations that events might reference (from geocoding.py)
# Enhanced with more keywords to capture unmatched events
TARGET_LOCATIONS_KEYWORDS = {
    'Taiwan': ['Taiwan', 'Taipei', 'Hsinchu', 'Kaohsiung', 'TSMC', 'semiconductor', 'chip manufacturing', 'Taiwan Strait'],
    'China': ['China', 'Chinese', 'Beijing', 'Shanghai', 'Shenzhen', 'Guangzhou', 'Zhengzhou', 'Ningde', 'Foxconn', 'CATL', 'Henan', 'Nanjing', 'Wuhan', 'Xinyu', 'Ganfeng'],
    'USA': ['USA', 'United States', 'California', 'Long Beach', 'Los Angeles', 'West Coast', 'California coast', 'Port Authority', 'Kentucky', 'Harrodsburg', 'Boise', 'Idaho', 'Austin', 'Texas', 'San Jose', 'Nevada', 'Sparks'],
    'Germany': ['Germany', 'German', 'Berlin', 'Munich', 'Hamburg', 'Tesla', 'Brandenburg', 'Gigafactory', 'Friedrichshafen', 'Stuttgart'],
    'Chile': ['Chile', 'Chilean', 'Santiago', 'Atacama', 'Albemarle', 'lithium', 'South America'],
    'South Korea': ['South Korea', 'Korea', 'Korean', 'Seoul', 'Icheon', 'Samsung', 'Hynix'],
    'Japan': ['Japan', 'Japanese', 'Tokyo', 'Kumamoto', 'Kyoto', 'Sony', 'Murata', 'Kioxia'],
    'Vietnam': ['Vietnam', 'Vietnamese', 'Hanoi', 'Bac Giang', 'Bac Ninh', 'Luxshare', 'Goertek'],
    'Netherlands': ['Netherlands', 'Dutch', 'Eindhoven', 'NXP'],
    'Switzerland': ['Switzerland', 'Swiss', 'Geneva', 'STMicroelectronics', 'STMicro'],
    'Philippines': ['Philippines', 'Manila', 'Amkor'],
    'Italy': ['Italy', 'Italian', 'Bergamo', 'Brembo'],
    'France': ['France', 'French', 'Paris', 'Valeo'],
    'Hong Kong': ['Hong Kong', 'HK', 'Hongkong'],
    'Europe': ['Europe', 'European', 'EU', 'Germany', 'Berlin', 'Netherlands', 'Switzerland', 'Italy', 'France'],
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
    Matches an event to supplier nodes based on:
    1. Specific Anchors (keywords)
    2. Geographic Proximity (within 800km)
    3. Country Fallback (if no specific matches found)
    
    Returns a list of matched node names.
    """
    matched_nodes = set()
    
    article_title = event.get('article_title', '').lower()
    event_text_segment = event.get('event_text_segment', '').lower()
    combined_text = f"{article_title} {event_text_segment}".lower()
    
    import re
    
    # Strategy 1: Specific Node Anchors
    node_anchor_keywords = {
        'TSMC_Hsinchu': ['tsmc', 'hsinchu', 'taiwan strait', 'wafer fab'],
        'Foxconn_Zhengzhou': ['foxconn', 'zhengzhou', 'hon hai'],
        'CATL_Ningde': ['catl', 'ningde', 'ev battery'],
        'Port_of_Long_Beach': ['long beach', 'los angeles port', 'port authority', 'la port', 'california port'],
        'Albemarle_Chile': ['albemarle', 'atacama', 'lithium brine', 'chilean lithium'],
        'Tesla_Berlin': ['tesla', 'gigafactory', 'brandenburg', 'berlin plant'],
        'Pegatron_Shanghai': ['pegatron', 'shanghai fab'],
        'Samsung_Display_Seoul': ['samsung display', 'samsung oled'],
        'Sony_Kumamoto': ['sony semiconductor', 'sony sensor', 'kumamoto fab'],
        'Corning_Kentucky': ['corning glass', 'harrodsburg'],
        'SK_Hynix_Icheon': ['hynix', 'icheon fab'],
        'Micron_Boise': ['micron', 'boise fab'],
        'Cirrus_Logic_Austin': ['cirrus logic'],
        'NXP_Eindhoven': ['nxp', 'eindhoven'],
        'STMicro_Geneva': ['stmicroelectronics', 'geneva fab'],
        'Broadcom_San_Jose': ['broadcom'],
        'Kioxia_Tokyo': ['kioxia'],
        'Luxshare_Bac_Giang': ['luxshare', 'bac giang'],
        'GoerTek_Bac_Ninh': ['goertek', 'bac ninh'],
        'Murata_Kyoto': ['murata'],
        'Varta_Ellwangen': ['varta', 'ellwangen'],
        'Inventec_Taipei': ['inventec'],
        'Amkor_Manila': ['amkor', 'manila packaging'],
        'LG_Energy_Nanjing': ['lg energy', 'nanjing battery'],
        'Panasonic_Nevada': ['panasonic gigafactory', 'panasonic nevada'],
        'ZF_Friedrichshafen': ['zf friedrichshafen', 'zf powertrain'],
        'Bosch_Stuttgart': ['bosch stuttgart', 'bosch sensor'],
        'Brembo_Bergamo': ['brembo brake'],
        'Valeo_Paris': ['valeo hvac', 'valeo thermal'],
        'Ganfeng_Lithium_Xinyu': ['ganfeng lithium', 'xinyu'],
    }
    
    for node, keywords in node_anchor_keywords.items():
        for word in keywords:
            # Use regex word boundaries to prevent substring matches (e.g. 'usa' in 'thousands')
            pattern = r'\b' + re.escape(word) + r'\b'
            if re.search(pattern, combined_text):
                matched_nodes.add(node)
                break
            
    # Strategy 2: Geographic Proximity
    event_lat = event.get('latitude')
    event_lon = event.get('longitude')
    if event_lat is not None and event_lon is not None:
        for node_name, node_data in SUPPLIER_NODES.items():
            dist = haversine_distance(event_lat, event_lon, node_data['latitude'], node_data['longitude'])
            if dist <= 800:
                matched_nodes.add(node_name)
                
    # Strategy 3: Country Fallback (ONLY if no specific matches found)
    if not matched_nodes:
        # Rely primarily on extracted_locations to avoid parsing sidebar junk in combined_text
        extracted_locations = [str(loc).lower() for loc in event.get('extracted_locations', [])]
        search_texts = extracted_locations if extracted_locations else [combined_text]
        
        matched_countries = set()
        for country, keywords in TARGET_LOCATIONS_KEYWORDS.items():
            for text_blob in search_texts:
                for k in keywords:
                    pattern = r'\b' + re.escape(k.lower()) + r'\b'
                    if re.search(pattern, text_blob):
                        matched_countries.add(country)
                        break
                if country in matched_countries:
                    break
        
        for country in matched_countries:
            for node_name, node_data in SUPPLIER_NODES.items():
                if node_data['country'] == country:
                    matched_nodes.add(node_name)
                    
    return list(matched_nodes)


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


def match_all_events(events):
    """Match a list of events to supplier nodes."""
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
    if len(events) > 0:
        print(f"  📈 Match rate: {matched_count/len(events)*100:.1f}%")
        
    return events


def main():
    """Main function to match events to nodes."""
    # Load geocoded events
    events = load_geocoded_events()
    if not events:
        print("No events to process.")
        return
    
    # Match each event to a node
    matched_events = match_all_events(events)
    
    # Save the matched events
    save_matched_events(matched_events)
    
    # Print distribution by node
    print(f"\n📍 Events by Node:")
    node_counts = {}
    for event in matched_events:
        node = event.get('matched_node', 'Unmatched')
        node_counts[node] = node_counts.get(node, 0) + 1
    
    for node, count in sorted(node_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {node}: {count} events")


if __name__ == "__main__":
    main()
