"""
Fetch live news from RSS feeds, score with ML classifier, upsert into PostgreSQL.

Configuration:
  - RSS_FEEDS_PATH: JSON file listing feeds (default: config/rss_feeds.json)
  - ML_CLASSIFIER_PATH: pickle with (vectorizer, model) (default: model_training/classifier.pkl)
  - DB_CONNECTION_STRING: same as load_to_db

Run once:
  python -m src.rss_ingest

Poll loop (seconds between full poll):
  python -m src.rss_ingest --interval 600
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import sys
import time
from email.utils import parsedate_to_datetime
from pathlib import Path

# Project root on sys.path when run as script or module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ML_TO_RISK = {"HIGH": 25.0, "MEDIUM": 12.0, "LOW": 3.0}


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_classifier(model_path: str):
    path = Path(model_path)
    if not path.is_file():
        raise FileNotFoundError(f"Classifier not found: {path}")
    with path.open("rb") as f:
        vectorizer, model = pickle.load(f)
    return vectorizer, model


def load_feeds_config(config_path: str) -> list[dict]:
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"RSS config not found: {path}\n"
            f"Copy config/rss_feeds.example.json to {path} and edit URLs."
        )
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("RSS config must be a JSON array of {url, source} objects")
    return data


def _entry_timestamp(entry) -> str | None:
    if getattr(entry, "published", None):
        return str(entry.published)
    if getattr(entry, "updated", None):
        return str(entry.updated)
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", entry.published_parsed)
        except Exception:
            pass
    return None


def feed_entry_to_event_dict(entry, source_name: str, vectorizer, model) -> dict | None:
    link = (getattr(entry, "link", None) or getattr(entry, "id", None) or "").strip()
    if not link or not link.startswith("http"):
        return None

    title = _strip_html(getattr(entry, "title", "") or "")
    summary_raw = (
        getattr(entry, "summary", None)
        or getattr(entry, "description", None)
        or ""
    )
    summary = _strip_html(summary_raw)
    body_for_model = summary[:300] if summary else title[:300]
    model_input = f"{title} {body_for_model}".strip()
    if len(model_input) < 5:
        return None

    X = vectorizer.transform([model_input])
    pred = str(model.predict(X)[0])
    prob_row = model.predict_proba(X)[0]
    classes = list(model.classes_)
    prob_map = {c: round(float(p), 4) for c, p in zip(classes, prob_row)}
    confidence = max(prob_map.values()) if prob_map else None

    ts_raw = _entry_timestamp(entry)
    segment = summary if summary else title
    if len(segment) > 12000:
        segment = segment[:12000]

    return {
        "article_url": link,
        "article_source": source_name,
        "article_title": title or link,
        "article_timestamp": ts_raw,
        "event_text_segment": segment,
        "potential_event_types": [],
        "extracted_locations": [],
        "matched_node": None,
        "risk_score": ML_TO_RISK.get(pred.upper(), 0.0),
        "latitude": None,
        "longitude": None,
        "temporal_info": None,
        "ml_risk_label": pred.upper() if pred.upper() in ML_TO_RISK else pred,
        "ml_risk_confidence": confidence,
        "ml_risk_probabilities": prob_map,
    }


def fetch_and_build_events(feeds: list[dict], vectorizer, model) -> list[dict]:
    import feedparser

    events: list[dict] = []
    for feed_cfg in feeds:
        url = feed_cfg.get("url")
        source = feed_cfg.get("source") or feed_cfg.get("name") or "RSS"
        if not url:
            continue
        parsed = feedparser.parse(url)
        if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
            print(f"⚠️ Feed parse issue for {url}: {getattr(parsed, 'bozo_exception', 'unknown')}")
            continue
        for entry in parsed.entries or []:
            ev = feed_entry_to_event_dict(entry, source, vectorizer, model)
            if ev:
                events.append(ev)
    return events


def run_once(
    feeds_path: str,
    model_path: str,
    skip_db: bool,
) -> int:
    feeds = load_feeds_config(feeds_path)
    vectorizer, model = load_classifier(model_path)
    batch = fetch_and_build_events(feeds, vectorizer, model)
    print(f"Collected {len(batch)} item(s) from RSS.")

    if skip_db:
        for ev in batch[:5]:
            print(f"  [{ev['ml_risk_label']}] {ev['article_title'][:80]}")
        if len(batch) > 5:
            print(f"  ... and {len(batch) - 5} more (DB skipped)")
        return len(batch)

    from src.load_to_db import get_db_engine, create_tables, upsert_events

    engine = get_db_engine()
    if not engine:
        print("❌ Database engine not available.")
        return 0
    create_tables(engine)
    upsert_events(engine, batch, recompute_supplier_scores=True)
    return len(batch)


def main():
    parser = argparse.ArgumentParser(description="RSS → ML → PostgreSQL")
    parser.add_argument(
        "--feeds",
        default=os.getenv("RSS_FEEDS_PATH", str(PROJECT_ROOT / "config" / "rss_feeds.json")),
        help="Path to JSON feed list",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("ML_CLASSIFIER_PATH", str(PROJECT_ROOT / "model_training" / "classifier.pkl")),
        help="Classifier pickle path",
    )
    parser.add_argument("--interval", type=int, default=0, help="If >0, re-run every N seconds")
    parser.add_argument("--skip-db", action="store_true", help="Only fetch + score; do not write DB")
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)

    if args.interval and args.interval > 0:
        while True:
            try:
                run_once(args.feeds, args.model, args.skip_db)
            except KeyboardInterrupt:
                print("\nStopped.")
                sys.exit(0)
            except Exception as e:
                print(f"❌ Run failed: {e}")
            time.sleep(args.interval)
    else:
        try:
            n = run_once(args.feeds, args.model, args.skip_db)
            print(f"Done. Processed {n} item(s).")
        except Exception as e:
            print(f"❌ {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
