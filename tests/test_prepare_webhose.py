import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.prepare_webhose_data import normalize_article, CATEGORY_EVENT_MAP

SAMPLE = {
    "thread": {"site": "rawstory.com", "country": "US", "domain_rank": 3187},
    "url": "https://rawstory.com/article",
    "published": "2025-01-12T23:33:00.000+02:00",
    "title": "Some headline",
    "text": "Article body...",
    "language": "english",
    "sentiment": "negative",
    "categories": ["Politics", "Economy, Business and Finance"],
    "topics": ["Politics->political parties"],
    "entities": {
        "persons": [],
        "organizations": [{"name": "TSMC", "sentiment": "negative"}],
        "locations": [{"name": "Taiwan"}],
    },
}


def test_normalize_article_label_format():
    entry, _ = normalize_article(SAMPLE, "webhose_political")
    parts = entry["label"].split(";")
    assert parts[0] == "rawstory.com"
    assert parts[1] == "Some headline"
    assert parts[2] == "https://rawstory.com/article"
    # timestamp must be UTC ISO
    assert "+00:00" in parts[3] or parts[3].endswith("Z")


def test_normalize_article_text():
    entry, _ = normalize_article(SAMPLE, "webhose_political")
    assert entry["text"] == "Article body..."


def test_normalize_article_webhose_meta_locations():
    entry, _ = normalize_article(SAMPLE, "webhose_political")
    assert entry["webhose_meta"]["locations"] == ["Taiwan"]


def test_normalize_article_webhose_meta_categories():
    entry, _ = normalize_article(SAMPLE, "webhose_political")
    assert "Politics" in entry["webhose_meta"]["categories"]
    assert "Economy, Business and Finance" in entry["webhose_meta"]["categories"]


def test_normalize_article_skips_non_english():
    article = {**SAMPLE, "language": "french"}
    assert normalize_article(article, "webhose_political") is None


def test_normalize_article_skips_pre_2025():
    article = {**SAMPLE, "published": "2024-12-31T23:59:00.000+00:00"}
    assert normalize_article(article, "webhose_political") is None


def test_normalize_article_sidecar_fields():
    _, sidecar = normalize_article(SAMPLE, "webhose_political")
    assert sidecar["url"] == "https://rawstory.com/article"
    assert sidecar["sentiment"] == "negative"
    assert sidecar["dataset_source"] == "webhose_political"
    assert sidecar["domain_rank"] == 3187
    assert sidecar["source_country"] == "US"
    assert {"name": "TSMC", "sentiment": "negative"} in sidecar["entities_organizations"]
    assert {"name": "Taiwan"} in sidecar["entities_locations"]


def test_category_event_map_has_required_keys():
    required = [
        "Economy, Business and Finance",
        "Politics",
        "Disasters and Accidents",
        "Labor",
        "Technology",
        "Transport",
        "Industry",
    ]
    for key in required:
        assert key in CATEGORY_EVENT_MAP, f"Missing key: {key}"
