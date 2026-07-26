"""Offline gazetteer geocoding (rebuild of the broken Phase 3.2 placeholder). Uses
geonamescache's bundled country/city data plus a small hand-curated table of maritime
chokepoints relevant to the shipping_chokepoints sector. No network calls (unlike Nominatim),
so no rate limits and safe to run on every live ingest cycle.

Each resolved place carries a confidence score (0-1) reflecting how the match was made —
an exact chokepoint/country match scores highest, an ambiguous city name (multiple
same-named cities worldwide) scores lowest. This is the confidence signal
scripts/build_ui_snapshot.py's map_points() filters on.
"""

from __future__ import annotations

import geonamescache

_gc = geonamescache.GeonamesCache()

# Hand-curated: these are the specific maritime chokepoints the sector definitions
# (scripts/build_ui_snapshot.py::META) call out, but they're straits/canals/seas, not
# countries or cities, so geonamescache has no entry for them.
CHOKEPOINTS: dict[str, tuple[str, float, float]] = {
    "strait of hormuz": ("Strait of Hormuz", 26.6, 56.5),
    "hormuz": ("Strait of Hormuz", 26.6, 56.5),
    "bab-el-mandeb": ("Bab-el-Mandeb", 12.6, 43.3),
    "bab el mandeb": ("Bab-el-Mandeb", 12.6, 43.3),
    "suez canal": ("Suez Canal", 30.0, 32.5),
    "suez": ("Suez Canal", 30.0, 32.5),
    "red sea": ("Red Sea", 20.0, 38.0),
    "strait of malacca": ("Strait of Malacca", 2.8, 101.0),
    "malacca strait": ("Strait of Malacca", 2.8, 101.0),
    "panama canal": ("Panama Canal", 9.08, -79.68),
    "strait of gibraltar": ("Strait of Gibraltar", 35.95, -5.6),
    "english channel": ("English Channel", 50.0, 1.0),
    "taiwan strait": ("Taiwan Strait", 24.0, 119.5),
}

# Generic/continental terms that would otherwise spuriously match an obscure same-named
# town (e.g. "Asia" matches a small town in the Philippines) — these are almost always used
# in their generic sense in supply-chain news, not as a proper noun for that town.
GENERIC_BLOCKLIST = {
    "asia", "africa", "europe", "america", "americas", "north america", "south america",
    "middle east", "the middle east", "west", "the west", "east", "the east",
    "eastern europe", "western europe", "southeast asia", "asia-pacific", "asia pacific",
}

_COUNTRIES = _gc.get_countries_by_names()
_COUNTRY_INDEX = {name.lower(): c for name, c in _COUNTRIES.items()}

_CITY_INDEX: dict[str, list[dict]] = {}
for _city in _gc.get_cities().values():
    _CITY_INDEX.setdefault(_city["name"].lower(), []).append(_city)

_COUNTRY_COORDS: dict[str, tuple[float, float]] = {}
for _name, _c in _COUNTRIES.items():
    _cap_matches = _CITY_INDEX.get((_c.get("capital") or "").lower())
    if _cap_matches:
        _cap = max(_cap_matches, key=lambda x: x["population"])
        _COUNTRY_COORDS[_c["iso"]] = (_cap["latitude"], _cap["longitude"])


def resolve_place(name: str, label: str = "LOC") -> dict | None:
    """Resolve one extracted place name to {"lat", "lon", "confidence", "matched_name"},
    or None if it doesn't match anything in the gazetteer."""
    key = name.strip().lower()
    if key in GENERIC_BLOCKLIST:
        return None
    if key.startswith("the "):
        key = key[4:]
    if not key or key in GENERIC_BLOCKLIST:
        return None

    if key in CHOKEPOINTS:
        display_name, lat, lon = CHOKEPOINTS[key]
        return {"lat": lat, "lon": lon, "confidence": 0.95, "matched_name": display_name}

    if key in _COUNTRY_INDEX:
        country = _COUNTRY_INDEX[key]
        coords = _COUNTRY_COORDS.get(country["iso"])
        if coords:
            confidence = 0.9 if label == "GPE" else 0.8
            return {"lat": coords[0], "lon": coords[1], "confidence": confidence, "matched_name": country["name"]}

    candidates = _CITY_INDEX.get(key)
    if candidates:
        best = max(candidates, key=lambda c: c["population"])
        confidence = 0.85 if len(candidates) == 1 else 0.6
        if label == "GPE":
            confidence = min(0.95, confidence + 0.05)
        return {"lat": best["latitude"], "lon": best["longitude"], "confidence": confidence, "matched_name": best["name"]}

    return None


def geocode_batch(entities_per_doc: list[list[tuple[str, str]]]) -> list[dict | None]:
    """For each document's list of (entity_text, label) candidates (in extraction order),
    return the first resolvable place, or None if nothing in the list resolves."""
    out = []
    for ents in entities_per_doc:
        hit = None
        for name, label in ents:
            hit = resolve_place(name, label)
            if hit:
                break
        out.append(hit)
    return out
