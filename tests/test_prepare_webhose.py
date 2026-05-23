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
    quarter_from_label,
    group_by_quarter,
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


# ── Quarter grouping tests (Task 4) ───────────────────────────────────────────

Q1_ENTRY = {"label": "a.com;T;https://a.com/1;2025-02-15T00:00:00+00:00", "text": "x"}
Q2_ENTRY = {"label": "a.com;T;https://a.com/2;2025-05-01T00:00:00+00:00", "text": "x"}
Q3_ENTRY = {"label": "a.com;T;https://a.com/3;2025-08-20T00:00:00+00:00", "text": "x"}
Q4_ENTRY = {"label": "a.com;T;https://a.com/4;2025-11-01T00:00:00+00:00", "text": "x"}
Q1_2026  = {"label": "a.com;T;https://a.com/5;2026-01-10T00:00:00+00:00", "text": "x"}


def test_quarter_from_label_q1():
    assert quarter_from_label(Q1_ENTRY["label"]) == (2025, 1)


def test_quarter_from_label_q2():
    assert quarter_from_label(Q2_ENTRY["label"]) == (2025, 2)


def test_quarter_from_label_q3():
    assert quarter_from_label(Q3_ENTRY["label"]) == (2025, 3)


def test_quarter_from_label_q4():
    assert quarter_from_label(Q4_ENTRY["label"]) == (2025, 4)


def test_quarter_from_label_2026():
    assert quarter_from_label(Q1_2026["label"]) == (2026, 1)


def test_group_by_quarter_keys():
    grouped = group_by_quarter([Q1_ENTRY, Q2_ENTRY, Q3_ENTRY, Q4_ENTRY, Q1_2026])
    assert (2025, 1) in grouped
    assert (2025, 2) in grouped
    assert (2026, 1) in grouped


def test_group_by_quarter_counts():
    grouped = group_by_quarter([Q1_ENTRY, Q2_ENTRY, Q3_ENTRY, Q4_ENTRY, Q1_2026])
    assert len(grouped[(2025, 1)]) == 1
    assert len(grouped[(2026, 1)]) == 1


def test_write_combined_creates_quarterly_files(tmp_path):
    from scripts.prepare_webhose_data import write_combined
    groups = {
        (2025, 1): [Q1_ENTRY],
        (2025, 3): [Q3_ENTRY, {**Q3_ENTRY, "label": "a.com;T;https://a.com/33;2025-09-01T00:00:00+00:00"}],
    }
    write_combined(groups, tmp_path)
    assert (tmp_path / "all_news_2025_q1.json").exists()
    assert (tmp_path / "all_news_2025_q3.json").exists()
    q1 = json.loads((tmp_path / "all_news_2025_q1.json").read_text())
    assert len(q1) == 1
    assert list(q1[0].keys()) == ["label", "text"]  # webhose_meta stripped


def test_write_combined_strips_webhose_meta(tmp_path):
    from scripts.prepare_webhose_data import write_combined
    entry_with_meta = {**Q1_ENTRY, "webhose_meta": {"locations": ["Taiwan"], "categories": ["Politics"]}}
    write_combined({(2025, 1): [entry_with_meta]}, tmp_path)
    written = json.loads((tmp_path / "all_news_2025_q1.json").read_text())
    assert "webhose_meta" not in written[0]


# ── write_sidecar and iter_webhose_repo tests (Task 5) ─────────────────────────

def test_write_sidecar_creates_jsonl(tmp_path):
    from scripts.prepare_webhose_data import write_sidecar
    sidecars = [
        {"url": "https://a.com/1", "sentiment": "negative", "dataset_source": "webhose_political"},
        {"url": "https://a.com/2", "sentiment": "positive", "dataset_source": "webhose_financial"},
    ]
    write_sidecar(sidecars, tmp_path)
    out = tmp_path / "webhose_metadata.jsonl"
    assert out.exists()
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["url"] == "https://a.com/1"
    assert json.loads(lines[1])["sentiment"] == "positive"


def test_iter_webhose_repo_missing_datasets_returns_empty(tmp_path):
    from scripts.prepare_webhose_data import iter_webhose_repo
    entries, sidecars = iter_webhose_repo(tmp_path, "webhose_political")
    assert entries == []
    assert sidecars == []


def test_iter_webhose_repo_processes_zip(tmp_path):
    from scripts.prepare_webhose_data import iter_webhose_repo
    datasets_dir = tmp_path / "Datasets"
    datasets_dir.mkdir()
    # Build a zip with one 2025 English article
    zip_path = datasets_dir / "Politics_negative_20250112070219.zip"
    buf = io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("folder/article_1.json", json.dumps(SAMPLE))
    zip_path.write_bytes(buf.getvalue())
    entries, sidecars = iter_webhose_repo(tmp_path, "webhose_political")
    assert len(entries) == 1
    assert len(sidecars) == 1
    assert sidecars[0]["dataset_source"] == "webhose_political"
