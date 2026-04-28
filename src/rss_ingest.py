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

ingestion_status = {
    "is_running": False,
    "current_step": "Idle",
    "progress_percent": 0,
    "items_processed": 0,
    "total_items": 0,
    "error": None
}

def update_status(is_running=None, current_step=None, progress_percent=None, items_processed=None, total_items=None, error=None):
    if is_running is not None: ingestion_status["is_running"] = is_running
    if current_step is not None: ingestion_status["current_step"] = current_step
    if progress_percent is not None: ingestion_status["progress_percent"] = progress_percent
    if items_processed is not None: ingestion_status["items_processed"] = items_processed
    if total_items is not None: ingestion_status["total_items"] = total_items
    if error is not None: ingestion_status["error"] = error


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
    is_background: bool = False,
) -> int:
    try:
        if is_background:
            update_status(is_running=True, current_step="Fetching RSS Feeds...", progress_percent=5, items_processed=0, total_items=0, error=None)
            
        feeds = load_feeds_config(feeds_path)
        vectorizer, model = load_classifier(model_path)
        batch = fetch_and_build_events(feeds, vectorizer, model)
        
        print(f"Fetched {len(batch)} item(s) from RSS. Running NLP enrichment...")
        if is_background:
            update_status(current_step="Classifying & Extracting Locations...", progress_percent=30, total_items=len(batch))
        
        if batch:
            from src.preprocessing import extract_locations_batch, detect_potential_events
            from src.geocoding import geocode_location_with_retry, save_geocode_cache
            from src.match_events_to_nodes import match_event_to_node
            from src.temporal_extraction import enrich_events_with_temporal_data
            
            # 1. Detect potential event types
            for ev in batch:
                ev['potential_event_types'] = detect_potential_events(ev['event_text_segment'], ev.get('article_title', ''))
                
            # 2. Extract locations using NER
            if is_background:
                update_status(current_step="Extracting geographic locations via NER...", progress_percent=50)
            texts_for_ner = [ev['event_text_segment'] for ev in batch]
            locations_batch = extract_locations_batch(texts_for_ner)
            
            for ev, locs in zip(batch, locations_batch):
                ev['extracted_locations'] = locs
                
            # 3. Geocode and Match
            if is_background:
                update_status(current_step="Geocoding and Matching Nodes...", progress_percent=60)
            import time
            for i, ev in enumerate(batch):
                if ev['extracted_locations']:
                    # Geocode the first primary location
                    lat, lon = geocode_location_with_retry(ev['extracted_locations'][0])
                    ev['latitude'] = lat
                    ev['longitude'] = lon
                    ev['geocoded_location_text'] = ev['extracted_locations'][0] if lat is not None else None
                    time.sleep(1.1) # Respect Nominatim 1 request/sec rate limit
                
                # Match to a supplier node
                ev['matched_node'] = match_event_to_node(ev)
                if is_background:
                    pct = 60 + int((i+1)/len(batch)*30)
                    update_status(progress_percent=pct, items_processed=i+1)
                
            # Save cache to avoid redundant API calls on next ingest
            save_geocode_cache(geocode_location_with_retry.cache)

            # 4. Temporal Extraction
            if is_background:
                update_status(current_step="Extracting Temporal Projections...", progress_percent=85)
            batch = enrich_events_with_temporal_data(batch)

        print(f"Enrichment complete. Preparing to save {len(batch)} item(s).")
        if is_background:
            update_status(current_step="Saving to database...", progress_percent=90)

        if skip_db:
            for ev in batch[:5]:
                print(f"  [{ev['ml_risk_label']}] {ev['article_title'][:80]}")
            if len(batch) > 5:
                print(f"  ... and {len(batch) - 5} more (DB skipped)")
            if is_background:
                update_status(current_step="Idle", progress_percent=100, is_running=False)
            return len(batch)

        from src.load_to_db import get_db_engine, create_tables, upsert_events, get_all_events

        engine = get_db_engine()
        if not engine:
            print("❌ Database engine not available.")
            if is_background:
                update_status(error="Database engine not available.", is_running=False)
            return 0
        create_tables(engine)
        upsert_events(engine, batch, recompute_supplier_scores=True)
        
        # 5. Recompute Forecasts
        if is_background:
            update_status(current_step="Recomputing Hybrid Forecasts...", progress_percent=95)
            
        from src.predictive_forecasting import generate_all_node_forecasts
        all_events = get_all_events(engine)
        if all_events:
            generate_all_node_forecasts(all_events)
        
        if is_background:
            update_status(current_step="Idle", progress_percent=100, is_running=False)
            
        return len(batch)
    except Exception as e:
        if is_background:
            update_status(error=str(e), is_running=False, current_step="Error")
        raise e


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
