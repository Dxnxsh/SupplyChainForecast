"""
Tests for the tiered geocoding pipeline:
  - clean_location_string / _reject_reason pre-filter
  - geonamescache tier-1 lookup (_GEONAMES_LOOKUP)
  - geocode_batch deduplication and tier routing
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.geocoding import (
    _GEONAMES_LOOKUP,
    clean_location_string,
    is_geocodable,
    geocode_batch,
)


# ── clean_location_string ────────────────────────────────────────────────────

def test_clean_strips_possessive():
    # "coast" is a noise word, so it also gets stripped
    assert clean_location_string("Taiwan’s coast") == "Taiwan"


def test_clean_strips_possessive_unicode():
    # "factory" is a noise word, so it also gets stripped
    assert clean_location_string("China’s factory") == "China"


def test_clean_strips_noise_word_plant():
    assert clean_location_string("Zhengzhou plant") == "Zhengzhou"


def test_clean_strips_noise_word_facility():
    assert clean_location_string("Austin facility") == "Austin"


def test_clean_strips_noise_word_region():
    assert clean_location_string("Pacific region") == "Pacific"


def test_clean_strips_multiple_noise_words():
    assert clean_location_string("the port terminal") == ""


def test_clean_preserves_plain_city():
    assert clean_location_string("Taipei") == "Taipei"


def test_clean_preserves_country():
    assert clean_location_string("Germany") == "Germany"


# ── is_geocodable / _reject_reason ──────────────────────────────────────────

def test_reject_too_short():
    assert not is_geocodable("US")


def test_reject_contains_digit():
    assert not is_geocodable("Route 66")


def test_reject_known_company_apple():
    assert not is_geocodable("Apple")


def test_reject_known_company_tsmc():
    assert not is_geocodable("TSMC")


def test_reject_noise_word_waters():
    assert not is_geocodable("South China Sea waters")


def test_accept_plain_country():
    assert is_geocodable("Germany")


def test_accept_city():
    assert is_geocodable("Seoul")


def test_accept_three_char_minimum():
    assert is_geocodable("USA")


# ── _GEONAMES_LOOKUP tier-1 ──────────────────────────────────────────────────

def test_geonames_lookup_major_city():
    assert "seoul" in _GEONAMES_LOOKUP
    lat, lon = _GEONAMES_LOOKUP["seoul"]
    assert 37.0 < lat < 38.0
    assert 126.0 < lon < 128.0


def test_geonames_lookup_country_by_name():
    assert "germany" in _GEONAMES_LOOKUP
    lat, lon = _GEONAMES_LOOKUP["germany"]
    assert 50.0 < lat < 55.0


def test_geonames_lookup_country_iso():
    assert "de" in _GEONAMES_LOOKUP


def test_geonames_lookup_taiwan():
    assert "taiwan" in _GEONAMES_LOOKUP


def test_geonames_lookup_china():
    assert "china" in _GEONAMES_LOOKUP


# ── geocode_batch ────────────────────────────────────────────────────────────

def test_geocode_batch_deduplicates_nominatim_calls():
    """The same string appearing twice should only trigger one Nominatim call."""
    with patch("src.geocoding.geocode_location_with_retry") as mock_nominatim:
        mock_nominatim.return_value = (1.0, 2.0)
        mock_nominatim.last_was_cache = False
        # Use a string that won't hit geonamescache
        result = geocode_batch(["Obscureville", "Obscureville"])
    assert mock_nominatim.call_count == 1
    assert result["Obscureville"] == (1.0, 2.0)


def test_geocode_batch_uses_geonames_for_known_city():
    """Seoul should be resolved from _GEONAMES_LOOKUP without any Nominatim call."""
    with patch("src.geocoding.geocode_location_with_retry") as mock_nominatim:
        result = geocode_batch(["Seoul"])
    mock_nominatim.assert_not_called()
    lat, lon = result["Seoul"]
    assert lat is not None and lon is not None


def test_geocode_batch_uses_geonames_for_country():
    with patch("src.geocoding.geocode_location_with_retry") as mock_nominatim:
        result = geocode_batch(["Germany"])
    mock_nominatim.assert_not_called()
    lat, lon = result["Germany"]
    assert lat is not None


def test_geocode_batch_rejects_company_name(tmp_path, monkeypatch):
    monkeypatch.setattr("src.geocoding._REJECTED_LOG_PATH", str(tmp_path / "rej.jsonl"))
    with patch("src.geocoding.geocode_location_with_retry") as mock_nominatim:
        result = geocode_batch(["Apple"])
    mock_nominatim.assert_not_called()
    assert result["Apple"] == (None, None)


def test_geocode_batch_rejects_short_string():
    with patch("src.geocoding.geocode_location_with_retry") as mock_nominatim:
        result = geocode_batch(["LA"])
    mock_nominatim.assert_not_called()
    assert result["LA"] == (None, None)


def test_geocode_batch_returns_none_for_empty_input():
    result = geocode_batch([])
    assert result == {}


def test_geocode_batch_mixed_tier_routing():
    """Seoul hits geonames; Obscureville hits Nominatim; Apple is rejected."""
    with patch("src.geocoding.geocode_location_with_retry") as mock_nominatim:
        mock_nominatim.return_value = (10.0, 20.0)
        mock_nominatim.last_was_cache = False
        result = geocode_batch(["Seoul", "Obscureville", "Apple"])
    assert mock_nominatim.call_count == 1
    assert result["Seoul"] != (None, None)
    assert result["Obscureville"] == (10.0, 20.0)
    assert result["Apple"] == (None, None)


def test_geocode_batch_logs_rejected_to_file(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr("src.geocoding._REJECTED_LOG_PATH", str(tmp_path / "rej.jsonl"))
    with patch("src.geocoding.geocode_location_with_retry"):
        geocode_batch(["TSMC", "LA"])
    lines = (tmp_path / "rej.jsonl").read_text().strip().splitlines()
    raws = {json.loads(l)["raw"] for l in lines}
    assert "TSMC" in raws
    assert "LA" in raws


def test_geocode_batch_cleans_before_lookup():
    """'Taiwan plant' should clean to 'Taiwan' and hit geonamescache."""
    with patch("src.geocoding.geocode_location_with_retry") as mock_nominatim:
        result = geocode_batch(["Taiwan plant"])
    mock_nominatim.assert_not_called()
    assert result["Taiwan plant"] != (None, None)
