# src/geocoding.py

import json
import os
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError

# --- Configuration ---
NOMINATIM_USER_AGENT = "supply-chain-disruption-forecaster-fyp" # Be respectful and set a unique user agent
NOMINATIM_TIMEOUT = 10 # seconds
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2 # seconds

# --- Geocoding Setup ---
nominatim_geolocator = Nominatim(user_agent=NOMINATIM_USER_AGENT, timeout=NOMINATIM_TIMEOUT)

# --- Default Coordinates for fallback (Optional, can be removed if you only want explicitly geocoded points) ---
TARGET_LOCATIONS_COORDINATES = {
    "TSMC_Hsinchu": {"lat": 24.8016, "lon": 120.9716},
    "Foxconn_Zhengzhou": {"lat": 34.7466, "lon": 113.6253},
    "Port_of_Long_Beach": {"lat": 33.7542, "lon": -118.2165},
    "Albemarle_Chile": {"lat": -23.5869, "lon": -68.1533}, # Salar de Atacama
    "CATL_Ningde": {"lat": 26.6577, "lon": 119.5262},
    "Tesla_Berlin": {"lat": 52.4045, "lon": 13.7845}, # Grünheide
}

# --- Helper Function for Geocoding with Retry ---
def geocode_location_with_retry(location_name):
    """
    Attempts to geocode a location name with retries for network issues.
    Returns (latitude, longitude) or (None, None) if unsuccessful.
    """
    if not location_name:
        return None, None

    # Simple cache to avoid re-querying the same location within a single run
    if location_name.lower() in geocode_location_with_retry.cache:
        cached_result = geocode_location_with_retry.cache[location_name.lower()]
        # print(f"  Cache hit for '{location_name}': {cached_result}")
        return cached_result if cached_result else (None, None)

    for attempt in range(RETRY_ATTEMPTS):
        try:
            # print(f"  Attempt {attempt + 1} to geocode: {location_name}")
            location = nominatim_geolocator.geocode(location_name)
            if location:
                # print(f"  ✅ Geocoded '{location_name}' to ({location.latitude}, {location.longitude})")
                coords = (location.latitude, location.longitude)
                geocode_location_with_retry.cache[location_name.lower()] = coords # Cache success
                return coords
            else:
                # print(f"  🤷 Nominatim found no results for: {location_name}")
                geocode_location_with_retry.cache[location_name.lower()] = None # Cache failure
                return None, None # Explicitly return None if no location found
        except GeocoderTimedOut:
            print(f"⚠️ Geocoding service timed out for '{location_name}' (Attempt {attempt + 1}/{RETRY_ATTEMPTS}). Retrying...")
            time.sleep(RETRY_DELAY)
        except (GeocoderUnavailable, GeocoderServiceError) as e:
            print(f"❌ Geocoding service unavailable or error for '{location_name}' (Attempt {attempt + 1}/{RETRY_ATTEMPTS}): {e}. Retrying...")
            time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"❌ An unexpected error occurred during geocoding for '{location_name}': {e}")
            geocode_location_with_retry.cache[location_name.lower()] = None # Cache failure
            return None, None # Don't retry for unexpected errors
    
    print(f"❌ Failed to geocode '{location_name}' after {RETRY_ATTEMPTS} attempts.")
    geocode_location_with_retry.cache[location_name.lower()] = None # Cache failure
    return None, None

# Initialize the cache as an attribute of the function
geocode_location_with_retry.cache = {}

# --- Core Geocoding Logic ---
def load_scored_data(filepath="data/processed/scored_events.jsonl"):
    """Loads scored event data."""
    if not os.path.exists(filepath):
        print(f"❌ Error: Scored data file not found at {filepath}")
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f]

def geocode_events(scored_events):
    """
    Geocodes event locations using Nominatim and adds latitude/longitude to events.
    Prioritizes 'matched_node' then 'extracted_locations'.
    **Skips events entirely if no location text can be found.**
    """
    print(f"🌍 Starting geocoding for {len(scored_events)} scored events...")
    geocoded_events = []
    skipped_count = 0
    geocoded_count = 0
    
    # Reset cache for each run
    geocode_location_with_retry.cache = {} 

    for i, event in enumerate(scored_events):
        matched_node = event.get('matched_node')
        extracted_locations = event.get('extracted_locations') # This is a list

        location_to_geocode = None

        # --- <<< NEW: Determine Location & Skip Logic >>> ---
        # Priority 1: Use matched_node if available and not empty
        if matched_node:
            location_to_geocode = matched_node
        # Priority 2: If no valid matched_node, use the first extracted_location if available
        elif extracted_locations and isinstance(extracted_locations, list) and len(extracted_locations) > 0 and extracted_locations[0]:
            location_to_geocode = extracted_locations[0] # Take the first location

        # --- <<< If NO location text found, skip this event entirely >>> ---
        if not location_to_geocode:
            skipped_count += 1
            # print(f"  Skipping event (URL: {event.get('article_url')}) due to missing location text.")
            continue # Go to the next event in the scored_events list

        # --- If location text exists, proceed with geocoding ---
        latitude, longitude = geocode_location_with_retry(location_to_geocode)

        # Use fallback coordinates ONLY if primary geocoding fails AND a matched node exists
        if (latitude is None or longitude is None) and matched_node and matched_node in TARGET_LOCATIONS_COORDINATES:
            fallback_coords = TARGET_LOCATIONS_COORDINATES[matched_node]
            latitude, longitude = fallback_coords['lat'], fallback_coords['lon']
            # print(f"   -> Geocoding failed for '{location_to_geocode}', using fallback coordinates for node '{matched_node}'")

        # Add geocoding results to the event dictionary
        event['latitude'] = latitude
        event['longitude'] = longitude
        event['geocoded_location_text'] = location_to_geocode if latitude is not None else None # Store what was attempted/successful

        # Add the event (with potentially null lat/lon if fallback also failed) to the final list
        geocoded_events.append(event)

        if latitude is not None and longitude is not None:
            geocoded_count += 1
        # else: # No need to print warning here if fallback was intended or no coords found
            # print(f"⚠️ Could not geocode or find fallback for event (URL: {event.get('article_url')}, Location Text: {location_to_geocode}). Lat/Lon set to None.")

        # Add a small delay between requests to be polite to Nominatim
        time.sleep(1.1) # Slightly more than 1 second to be safe

        if (i + 1) % 50 == 0: # Print progress less frequently
            print(f"   Processed {i+1}/{len(scored_events)} events...")

    print(f"\n✅ Geocoding complete.")
    print(f"   Successfully geocoded (or used fallback for) {geocoded_count} events.")
    print(f"   Skipped {skipped_count} events due to missing location text.")
    print(f"   Total events in output: {len(geocoded_events)}")
    return geocoded_events

def save_geocoded_data(geocoded_events, output_path="data/processed/geocoded_events.jsonl"):
    """Saves the geocoded events to a new JSONL file."""
    print(f"💾 Saving {len(geocoded_events)} geocoded events to {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        for event in geocoded_events:
            json.dump(event, f, ensure_ascii=False)
            f.write('\n')
    print(f"✅ Geocoded data saved.")

if __name__ == "__main__":
    output_path = "data/processed/geocoded_events.jsonl"
    
    # Check if geocoded data already exists
    if os.path.exists(output_path):
        print(f"🔍 Found existing geocoded data at {output_path}")
        
        # Check if the file has content
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_lines = f.readlines()
                existing_count = len(existing_lines)
            
            if existing_count > 0:
                print(f"   ✅ File contains {existing_count} geocoded events")
                response = input("\n⚠️  Geocoded data already exists. Re-geocode anyway? (y/N): ").strip().lower()
                
                if response != 'y':
                    print("\n⏭️  Skipping geocoding. Using existing geocoded_events.jsonl")
                    print("   To force re-geocoding, delete the file or answer 'y' to the prompt.")
                    exit(0)
                else:
                    print("\n♻️  Re-geocoding all events...")
            else:
                print("   ⚠️  File exists but is empty. Will geocode now.")
        except Exception as e:
            print(f"   ⚠️  Error reading existing file: {e}. Will geocode now.")
    
    # Proceed with geocoding
    scored_data = load_scored_data()
    if scored_data:
        geocoded_results = geocode_events(scored_data)
        save_geocoded_data(geocoded_results, output_path)
    else:
        print("🤷 No scored data to geocode.")