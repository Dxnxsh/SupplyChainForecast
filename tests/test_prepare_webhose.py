import io
import json
import sys
import zipfile as _zipfile
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.prepare_webhose_data import (
    normalize_article,
    CATEGORY_EVENT_MAP,
    parse_zip_date,
    extract_articles_from_zip,
    merge_entries,
    _url_from_label,
)

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


# ── Zip extraction tests (Task 2) ──────────────────────────────────────────────

def _make_zip(articles: list[dict]) -> bytes:
    buf = io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        for i, art in enumerate(articles):
            zf.writestr(f"folder/article_{i+1}.json", json.dumps(art))
    return buf.getvalue()


def test_parse_zip_date_politics():
    assert parse_zip_date("Politics_negative_20250112070219.zip") == datetime(2025, 1, 12, tzinfo=timezone.utc)


def test_parse_zip_date_financial():
    assert parse_zip_date("Financial and Economic News_negative_20250119072618.zip") == datetime(2025, 1, 19, tzinfo=timezone.utc)


def test_parse_zip_date_pre2025_still_parses():
    assert parse_zip_date("Politics_negative_20241231070219.zip") == datetime(2024, 12, 31, tzinfo=timezone.utc)


def test_parse_zip_date_no_match_returns_none():
    assert parse_zip_date("random_file.txt") is None


def test_extract_articles_from_zip_returns_dicts():
    articles = [SAMPLE, {**SAMPLE, "url": "https://example.com/2"}]
    zip_bytes = _make_zip(articles)
    buf = io.BytesIO(zip_bytes)
    result = extract_articles_from_zip(buf)
    assert len(result) == 2
    assert result[0]["url"] == SAMPLE["url"]


def test_extract_articles_from_zip_skips_invalid_json():
    buf = io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("folder/article_1.json", "not json{{{")
        zf.writestr("folder/article_2.json", json.dumps(SAMPLE))
    buf.seek(0)
    result = extract_articles_from_zip(buf)
    assert len(result) == 1


# ── Merge / deduplication tests (Task 3) ──────────────────────────────────────

SCRAPE_ENTRY = {
    "label": "guardian.com;Old headline;https://rawstory.com/article;2025-01-12T21:33:00+00:00",
    "text": "Old text",
}
WEBHOSE_ENTRY = {
    "label": "rawstory.com;Some headline;https://rawstory.com/article;2025-01-12T21:33:00+00:00",
    "text": "Article body...",
    "webhose_meta": {"locations": ["Taiwan"], "categories": ["Politics"]},
}
UNIQUE_SCRAPE = {
    "label": "bbc.com;Different;https://bbc.com/unique;2025-02-01T00:00:00+00:00",
    "text": "Unique scrape text",
}


def test_url_from_label():
    assert _url_from_label(SCRAPE_ENTRY["label"]) == "https://rawstory.com/article"


def test_merge_webhose_wins_on_conflict():
    merged = merge_entries([SCRAPE_ENTRY, UNIQUE_SCRAPE], [WEBHOSE_ENTRY])
    by_url = {_url_from_label(e["label"]): e for e in merged}
    result = by_url["https://rawstory.com/article"]
    assert result["text"] == "Article body..."
    assert "webhose_meta" in result


def test_merge_keeps_unique_scrape_entries():
    merged = merge_entries([SCRAPE_ENTRY, UNIQUE_SCRAPE], [WEBHOSE_ENTRY])
    urls = {_url_from_label(e["label"]) for e in merged}
    assert "https://bbc.com/unique" in urls


def test_merge_no_duplicates():
    merged = merge_entries([SCRAPE_ENTRY, UNIQUE_SCRAPE], [WEBHOSE_ENTRY])
    urls = [_url_from_label(e["label"]) for e in merged]
    assert len(urls) == len(set(urls))


def test_merge_webhose_only_entries_included():
    webhose_only = {**WEBHOSE_ENTRY, "label": "x.com;New;https://x.com/new;2025-03-01T00:00:00+00:00"}
    merged = merge_entries([], [webhose_only])
    urls = {_url_from_label(e["label"]) for e in merged}
    assert "https://x.com/new" in urls


# ── load_web_scrape_entries tests (Task 3) ─────────────────────────────────────

def test_load_web_scrape_entries_reads_json_files(tmp_path):
    from scripts.prepare_webhose_data import load_web_scrape_entries
    entries = [SCRAPE_ENTRY, UNIQUE_SCRAPE]
    (tmp_path / "batch.json").write_text(json.dumps(entries), encoding="utf-8")
    result = load_web_scrape_entries(tmp_path)
    assert len(result) == 2
    assert result[0]["label"] == SCRAPE_ENTRY["label"]


def test_load_web_scrape_entries_missing_dir_returns_empty(tmp_path):
    from scripts.prepare_webhose_data import load_web_scrape_entries
    result = load_web_scrape_entries(tmp_path / "nonexistent")
    assert result == []


def test_load_web_scrape_entries_skips_non_list_json(tmp_path):
    from scripts.prepare_webhose_data import load_web_scrape_entries
    (tmp_path / "bad.json").write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    result = load_web_scrape_entries(tmp_path)
    assert result == []
