# src/geocoding.py

from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError

# --- Configuration ---
NOMINATIM_USER_AGENT = "supply-chain-disruption-forecaster-fyp"
NOMINATIM_TIMEOUT = 10
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2

nominatim_geolocator = Nominatim(user_agent=NOMINATIM_USER_AGENT, timeout=NOMINATIM_TIMEOUT)

# --- Default Coordinates for fallback ---
TARGET_LOCATIONS_COORDINATES = {
    "TSMC_Hsinchu": {"lat": 24.8016, "lon": 120.9716},
    "Foxconn_Zhengzhou": {"lat": 34.7466, "lon": 113.6253},
    "Port_of_Long_Beach": {"lat": 33.7542, "lon": -118.2165},
    "Albemarle_Chile": {"lat": -23.5869, "lon": -68.1533},
    "CATL_Ningde": {"lat": 26.6577, "lon": 119.5262},
    "Tesla_Berlin": {"lat": 52.4045, "lon": 13.7845},
}

CACHE_FILE = "data/geocode_cache.json"
_REJECTED_LOG_PATH = "data/geocode_rejected.jsonl"

# ── Pre-filter constants ─────────────────────────────────────────────────────

_KNOWN_COMPANIES = frozenset({
    "apple", "samsung", "tsmc", "foxconn", "tesla", "nvidia", "intel", "amd",
    "qualcomm", "broadcom", "microsoft", "google", "amazon", "meta", "huawei",
    "catl", "albemarle", "bosch", "volkswagen", "toyota", "ford", "gm",
    "general motors", "sony", "lg", "sk hynix", "micron",
})

_NOISE_WORDS = frozenset({
    "plant", "facility", "factory", "port", "terminal", "region", "area",
    "waters", "province", "prefecture", "the", "sector", "zone", "district",
    "coast", "border", "sea", "ocean", "bay",
})

_NOISE_WORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _NOISE_WORDS) + r")\b",
    re.IGNORECASE,
)

_DIGIT_RE = re.compile(r"\d")


def clean_location_string(raw: str) -> str:
    """Strip possessives and noise words from a raw NER location string."""
    s = raw.replace("'s", "").replace("’s", "")
    tokens = [t for t in s.split() if t.lower() not in _NOISE_WORDS]
    return " ".join(tokens).strip()


def _reject_reason(raw: str) -> Optional[str]:
    """Return a rejection reason if the raw string should not be geocoded, else None."""
    if len(raw) < 3:
        return "too_short"
    if _DIGIT_RE.search(raw):
        return "contains_digits"
    if raw.lower() in _KNOWN_COMPANIES:
        return "known_company"
    if _NOISE_WORD_RE.search(raw):
        return "noise_word"
    return None


def is_geocodable(s: str) -> bool:
    return _reject_reason(s) is None


def _log_rejected(raw: str, reason: str) -> None:
    os.makedirs(os.path.dirname(_REJECTED_LOG_PATH), exist_ok=True)
    with open(_REJECTED_LOG_PATH, "a", encoding="utf-8") as f:
        json.dump({"raw": raw, "reason": reason}, f)
        f.write("\n")


# ── geonamescache tier-1 lookup ──────────────────────────────────────────────

def _build_geonames_lookup() -> dict[str, tuple[float, float]]:
    """
    Build a name->coords dict from geonamescache at module load time.
    Covers cities (highest-population wins), alternate names for cities >100k,
    and country names resolved via their capital city.
    """
    try:
        import geonamescache
    except ImportError:
        return {}

    gc = geonamescache.GeonamesCache()
    cities = gc.get_cities()
    countries = gc.get_countries()

    lookup: dict[str, tuple[float, float]] = {}
    _city_pop: dict[str, int] = {}

    for city in cities.values():
        key = city["name"].lower()
        pop = city.get("population") or 0
        if key not in _city_pop or pop > _city_pop[key]:
            lookup[key] = (city["latitude"], city["longitude"])
            _city_pop[key] = pop

    # Alternate names for major cities only (keeps lookup size reasonable)
    for city in cities.values():
        if (city.get("population") or 0) > 100_000:
            for alt in city.get("alternatenames") or []:
                key = alt.lower()
                if key not in lookup:
                    lookup[key] = (city["latitude"], city["longitude"])

    # Country names + ISO codes via capital city coords
    for country in countries.values():
        capital = country.get("capital", "")
        cap_coords = lookup.get(capital.lower())
        if not cap_coords:
            continue
        for key in (
            country["name"].lower(),
            country["iso"].lower(),
            country.get("fips", "").lower(),
        ):
            if key and key not in lookup:
                lookup[key] = cap_coords

    return lookup


_GEONAMES_LOOKUP: dict[str, tuple[float, float]] = _build_geonames_lookup()


# ── File-backed cache ────────────────────────────────────────────────────────

def load_geocode_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_geocode_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


# ── Nominatim with retry ─────────────────────────────────────────────────────

def geocode_location_with_retry(
    location_name: str,
) -> tuple[Optional[float], Optional[float]]:
    """
    Geocode via Nominatim with in-process + file cache.
    Rate-limits itself: sleeps 1.1 s only when an actual Nominatim call is made.
    """
    if not location_name:
        return None, None

    key = location_name.lower()
    if key in geocode_location_with_retry.cache:
        cached = geocode_location_with_retry.cache[key]
        geocode_location_with_retry.last_was_cache = True
        return cached if cached else (None, None)

    geocode_location_with_retry.last_was_cache = False
    for attempt in range(RETRY_ATTEMPTS):
        try:
            location = nominatim_geolocator.geocode(location_name)
            if location:
                coords: tuple[float, float] = (location.latitude, location.longitude)
                geocode_location_with_retry.cache[key] = coords
            else:
                geocode_location_with_retry.cache[key] = None
                coords = (None, None)
            time.sleep(1.1)  # Nominatim ToS: max 1 req/s
            return coords
        except GeocoderTimedOut:
            print(f"⚠️ Geocoding timed out for '{location_name}' (attempt {attempt + 1}/{RETRY_ATTEMPTS}). Retrying...")
            time.sleep(RETRY_DELAY)
        except (GeocoderUnavailable, GeocoderServiceError) as e:
            print(f"❌ Geocoder unavailable for '{location_name}' (attempt {attempt + 1}/{RETRY_ATTEMPTS}): {e}. Retrying...")
            time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"❌ Unexpected geocoding error for '{location_name}': {e}")
            geocode_location_with_retry.cache[key] = None
            return None, None

    print(f"❌ Failed to geocode '{location_name}' after {RETRY_ATTEMPTS} attempts.")
    geocode_location_with_retry.cache[key] = None
    return None, None


geocode_location_with_retry.cache = load_geocode_cache()
geocode_location_with_retry.last_was_cache = False


# ── Batch geocoder (pre-deduplication + tiered lookup) ───────────────────────

def geocode_batch(
    location_strings: list[str],
    *,
    verbose: bool = False,
) -> dict[str, tuple[Optional[float], Optional[float]]]:
    """
    Geocode a list of location strings with full deduplication.

    Each unique string is resolved exactly once through:
      1. Pre-filter (reject noise/digits/companies — logged to geocode_rejected.jsonl)
      2. geonamescache tier-1 lookup (instant, no network)
      3. Nominatim (file cache + 1.1 s rate limit, only for unknowns)

    Returns {original_string: (lat, lon)} for every input string.
    """
    unique = list(dict.fromkeys(s for s in location_strings if s))
    results: dict[str, tuple[Optional[float], Optional[float]]] = {}

    geonames_hits = 0
    nominatim_calls = 0
    rejected = 0
    cache_hits = 0

    for raw in unique:
        # Hard rejects that survive cleaning: digits, known companies, too short
        hard_reason = _reject_reason(raw)
        if hard_reason and hard_reason != "noise_word":
            results[raw] = (None, None)
            rejected += 1
            _log_rejected(raw, hard_reason)
            continue

        cleaned = clean_location_string(raw)
        if not cleaned or len(cleaned) < 3:
            results[raw] = (None, None)
            rejected += 1
            _log_rejected(raw, "empty_after_clean")
            continue

        tier1 = _GEONAMES_LOOKUP.get(cleaned.lower())
        if tier1:
            results[raw] = tier1
            geonames_hits += 1
            continue

        lat, lon = geocode_location_with_retry(cleaned)
        results[raw] = (lat, lon)
        was_cache = getattr(geocode_location_with_retry, "last_was_cache", False)
        if was_cache is True:
            cache_hits += 1
        else:
            nominatim_calls += 1

    if nominatim_calls and isinstance(geocode_location_with_retry.cache, dict):
        save_geocode_cache(geocode_location_with_retry.cache)

    if verbose:
        print(
            f"[geocode_batch] {len(unique)} unique strings → "
            f"{geonames_hits} geonames, {cache_hits} file-cache, "
            f"{nominatim_calls} Nominatim, {rejected} rejected"
        )

    return results


# ── Batch pipeline entry point ───────────────────────────────────────────────

def load_scored_data(filepath: str = "data/processed/scored_events.jsonl") -> list:
    if not os.path.exists(filepath):
        print(f"❌ Error: Scored data file not found at {filepath}")
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def geocode_events(scored_events: list) -> list:
    """
    Geocode all events using pre-deduplication + tiered lookup.
    Events with no extracted location pass through with lat/lon unset.
    """
    print(f"🌍 Starting geocoding for {len(scored_events)} scored events...")
    geocode_location_with_retry.cache = load_geocode_cache()

    loc_strings = [
        ev["extracted_locations"][0]
        for ev in scored_events
        if ev.get("extracted_locations") and ev["extracted_locations"][0]
    ]
    coords_map = geocode_batch(loc_strings, verbose=True)

    geocoded_count = 0
    no_location_count = 0
    for ev in scored_events:
        locs = ev.get("extracted_locations")
        if locs and locs[0]:
            lat, lon = coords_map.get(locs[0], (None, None))
            ev["latitude"] = lat
            ev["longitude"] = lon
            ev["geocoded_location_text"] = locs[0] if lat is not None else None
            if lat is not None:
                geocoded_count += 1
        else:
            ev["latitude"] = None
            ev["longitude"] = None
            ev["geocoded_location_text"] = None
            no_location_count += 1

    print(
        f"\n✅ Geocoding complete. {geocoded_count} with coordinates, "
        f"{no_location_count} with no NER location."
    )
    return scored_events


def save_geocoded_data(
    geocoded_events: list,
    output_path: str = "data/processed/geocoded_events.jsonl",
) -> None:
    print(f"💾 Saving {len(geocoded_events)} geocoded events to {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        for event in geocoded_events:
            json.dump(event, f, ensure_ascii=False)
            f.write("\n")
    print("✅ Geocoded data saved.")


if __name__ == "__main__":
    output_path = "data/processed/geocoded_events.jsonl"

    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing_count = sum(1 for _ in f)
            if existing_count > 0:
                print(f"🔍 Found {existing_count} existing geocoded events.")
                response = input("⚠️  Re-geocode anyway? (y/N): ").strip().lower()
                if response != "y":
                    print("⏭️  Skipping geocoding.")
                    exit(0)
        except Exception as e:
            print(f"⚠️  Error reading existing file: {e}. Will geocode now.")

    scored_data = load_scored_data()
    if scored_data:
        geocoded_results = geocode_events(scored_data)
        save_geocoded_data(geocoded_results, output_path)
    else:
        print("🤷 No scored data to geocode.")
