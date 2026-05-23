"""
Prepare Webhose political/financial news datasets for pipeline ingestion.

Usage:
    venv311/bin/python scripts/prepare_webhose_data.py
    venv311/bin/python scripts/prepare_webhose_data.py \
        --political-repo data/raw/webhose_political \
        --financial-repo data/raw/webhose_financial
"""
from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CUTOFF = datetime(2025, 1, 1, tzinfo=timezone.utc)

CATEGORY_EVENT_MAP: dict[str, str] = {
    "Economy, Business and Finance": "Demand_Supply_Shift",
    "Politics": "Political_Regulatory",
    "Politics->government": "Political_Regulatory",
    "Politics->political parties": "Political_Regulatory",
    "Disasters and Accidents": "Natural_Disaster",
    "Labor": "Labor_Issue",
    "Labor Issues": "Labor_Issue",
    "Technology": "Cyber_Attack",
    "Cyber": "Cyber_Attack",
    "Transport": "Logistics_Issue",
    "Logistics": "Logistics_Issue",
    "Industry": "Industrial_Accident",
    "Manufacturing": "Industrial_Accident",
}

_ZIP_DATE_RE = re.compile(r"(\d{8})\d{6}\.zip$")


def parse_zip_date(filename: str) -> Optional[datetime]:
    """Extract the date from a Webhose zip filename. Returns UTC datetime or None."""
    m = _ZIP_DATE_RE.search(filename)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def extract_articles_from_zip(file_obj) -> list[dict]:
    """Read all .json files from an open zip file object. Skips invalid JSON."""
    articles = []
    with zipfile.ZipFile(file_obj) as zf:
        for name in zf.namelist():
            if not name.endswith(".json"):
                continue
            try:
                data = json.loads(zf.read(name).decode("utf-8", errors="replace"))
                if isinstance(data, dict):
                    articles.append(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
    return articles


def _parse_utc(ts: str) -> Optional[datetime]:
    """Parse ISO 8601 timestamp string → UTC-aware datetime. Returns None on failure."""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def normalize_article(
    article: dict, dataset_source: str
) -> Optional[tuple[dict, dict]]:
    """
    Convert a Webhose article dict to (pipeline_entry, sidecar_dict).
    Returns None if the article should be skipped (non-English or pre-2025).
    """
    if article.get("language", "").lower() != "english":
        return None

    published_raw = article.get("published", "")
    dt = _parse_utc(published_raw)
    if dt is None or dt < CUTOFF:
        return None

    url = article.get("url", "").strip()
    title = article.get("title", "").strip()
    text = article.get("text", "").strip()
    thread = article.get("thread", {})
    source = thread.get("site", "unknown")
    published_utc = dt.isoformat()

    title_safe = title.replace(";", " ")
    label = f"{source};{title_safe};{url};{published_utc}"

    entities = article.get("entities", {})
    locations = [loc.get("name") for loc in entities.get("locations", []) if loc.get("name")]
    organizations = [
        {"name": org["name"], "sentiment": org.get("sentiment", "none")}
        for org in entities.get("organizations", [])
        if org.get("name")
    ]

    raw_categories = article.get("categories", [])
    raw_topics = article.get("topics") or []

    pipeline_entry = {
        "label": label,
        "text": text,
        "webhose_meta": {
            "locations": locations,
            "categories": raw_categories,
        },
    }

    sidecar = {
        "url": url,
        "sentiment": article.get("sentiment", ""),
        "categories": raw_categories,
        "topics": raw_topics,
        "entities_locations": [{"name": n} for n in locations],
        "entities_organizations": organizations,
        "domain_rank": thread.get("domain_rank"),
        "source_country": thread.get("country", ""),
        "dataset_source": dataset_source,
    }

    return pipeline_entry, sidecar


def _url_from_label(label: str) -> str:
    """Extract URL (3rd semicolon-separated field) from a label string."""
    parts = label.split(";")
    return parts[2] if len(parts) > 2 else ""


def load_web_scrape_entries(scrape_dir: Path) -> list[dict]:
    """Load all *.json files from data/raw/web_scrape/ into a flat list."""
    entries = []
    if not scrape_dir.exists():
        return entries
    for path in sorted(scrape_dir.glob("*.json")):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            cleaned = re.sub(r"[\x00-\x1f]", "", raw)
            data = json.loads(cleaned)
            if isinstance(data, list):
                entries.extend(data)
        except Exception as exc:
            print(f"⚠️  Could not load {path.name}: {exc}")
    return entries


def merge_entries(scrape_entries: list[dict], webhose_entries: list[dict]) -> list[dict]:
    """
    Merge web_scrape and Webhose entries, deduplicating by URL.
    Webhose wins on conflict.
    """
    merged: dict[str, dict] = {}
    for entry in scrape_entries:
        url = _url_from_label(entry.get("label", ""))
        if url:
            merged[url] = entry
    for entry in webhose_entries:
        url = _url_from_label(entry.get("label", ""))
        if url:
            merged[url] = entry  # Webhose overwrites
    return list(merged.values())


def quarter_from_label(label: str) -> Optional[tuple[int, int]]:
    """Return (year, quarter) parsed from the timestamp in a label string."""
    parts = label.split(";")
    if len(parts) < 4:
        return None
    dt = _parse_utc(parts[3])
    if dt is None:
        return None
    q = (dt.month - 1) // 3 + 1
    return (dt.year, q)


def group_by_quarter(entries: list[dict]) -> dict[tuple[int, int], list[dict]]:
    """Group entries into {(year, quarter): [entries]} buckets."""
    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    skipped = 0
    for entry in entries:
        key = quarter_from_label(entry.get("label", ""))
        if key is None:
            skipped += 1
            continue
        groups[key].append(entry)
    if skipped:
        print(f"⚠️  Skipped {skipped} entries with unparseable timestamps.")
    return dict(groups)


def write_combined(
    groups: dict[tuple[int, int], list[dict]],
    out_dir: Path,
) -> None:
    """Write one JSON file per quarter to out_dir. Strips webhose_meta before writing."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for (year, quarter), entries in sorted(groups.items()):
        filename = out_dir / f"all_news_{year}_q{quarter}.json"
        # Strip webhose_meta — pipeline only needs label + text
        clean_entries = [{"label": e["label"], "text": e["text"]} for e in entries if e.get("label") and "text" in e]
        filename.write_text(json.dumps(clean_entries, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✅ Wrote {len(clean_entries):,} articles → {filename.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Webhose datasets for pipeline ingestion.")
    parser.add_argument(
        "--political-repo",
        default=str(PROJECT_ROOT / "data" / "raw" / "webhose_political"),
        help="Path to Webhose political news repo directory",
    )
    parser.add_argument(
        "--financial-repo",
        default=str(PROJECT_ROOT / "data" / "raw" / "webhose_financial"),
        help="Path to Webhose financial news repo directory",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "data" / "raw" / "combined"),
        help="Output directory for normalized JSON files",
    )
    args = parser.parse_args()

    repos = [
        (Path(args.political_repo), "webhose_political"),
        (Path(args.financial_repo), "webhose_financial"),
    ]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for repo_path, dataset_source in repos:
        if not repo_path.exists():
            print(f"[SKIP] Repo not found: {repo_path}")
            continue

        entries = []
        skipped = 0

        json_files = list(repo_path.rglob("*.json"))
        zip_files = list(repo_path.rglob("*.zip"))

        def process_article(article_dict: dict) -> None:
            nonlocal skipped
            result = normalize_article(article_dict, dataset_source)
            if result is None:
                skipped += 1
            else:
                entries.append(result[0])

        for jf in json_files:
            try:
                with open(jf, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        process_article(item)
                elif isinstance(data, dict):
                    process_article(data)
            except Exception as e:
                print(f"[WARN] Failed to read {jf}: {e}")

        for zf in zip_files:
            try:
                with zipfile.ZipFile(zf) as z:
                    for name in z.namelist():
                        if name.endswith(".json"):
                            with z.open(name) as f:
                                data = json.load(f)
                            if isinstance(data, list):
                                for item in data:
                                    process_article(item)
                            elif isinstance(data, dict):
                                process_article(data)
            except Exception as e:
                print(f"[WARN] Failed to read {zf}: {e}")

        out_file = output_dir / f"{dataset_source}_normalized.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

        print(f"[{dataset_source}] Written {len(entries)} articles to {out_file} (skipped {skipped})")


if __name__ == "__main__":
    main()
