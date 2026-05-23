"""
Fetch live news from RSS feeds, score with ML classifier, upsert into PostgreSQL.

Configuration:
  - RSS_FEEDS_PATH: JSON file listing feeds (default: config/rss_feeds.json)
  - ML_CLASSIFIER_PATH: pickle with (vectorizer, model[, LabelEncoder]) (default: model_training/classifier.pkl)
  - DB_CONNECTION_STRING: active Postgres (src/db_config.py)

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
import gc
from email.utils import parsedate_to_datetime
from pathlib import Path

import numpy as np
from scipy import sparse

# Project root on sys.path when run as script or module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_WEBHOSE_CATEGORY_EVENT_MAP: dict[str, str] = {
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


def _event_types_from_webhose_meta(webhose_meta: dict | None) -> list[str]:
    """Map Webhose categories to pipeline event types. Returns [] when meta is absent."""
    if not webhose_meta:
        return []
    types = []
    for cat in webhose_meta.get("categories") or []:
        mapped = _WEBHOSE_CATEGORY_EVENT_MAP.get(cat)
        if mapped and mapped not in types:
            types.append(mapped)
    return types


ML_TO_RISK = {"HIGH": 85.0, "MEDIUM": 45.0, "LOW": 15.0}

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
        payload = pickle.load(f)
    if isinstance(payload, tuple) and len(payload) == 3:
        return payload[0], payload[1], payload[2]
    if isinstance(payload, tuple) and len(payload) == 2:
        return payload[0], payload[1], None
    raise ValueError(f"Expected 2- or 3-tuple in classifier pickle: {path}")


def load_impact_regressor(model_path: str | None):
    if not model_path:
        return None
    path = Path(model_path)
    if not path.is_file():
        return None
    with path.open("rb") as f:
        payload = pickle.load(f)
    if not isinstance(payload, dict) or "model" not in payload or "artifacts" not in payload:
        raise ValueError(f"Invalid impact regressor artifact format: {path}")
    return payload


def load_disruption_classifier(model_path: str | None):
    if not model_path:
        return None
    path = Path(model_path)
    if not path.is_file():
        return None
    with path.open("rb") as f:
        payload = pickle.load(f)
    if not isinstance(payload, dict) or "model" not in payload or "artifacts" not in payload:
        raise ValueError(f"Invalid disruption classifier artifact format: {path}")
    return payload


def _event_to_shared_features(event: dict, artifacts: dict):
    text_vectorizer = artifacts["text_vectorizer"]
    cat_encoder = artifacts["cat_encoder"]
    categorical_cols = artifacts.get("categorical_cols", [])

    text_input = [
        ((event.get("article_title") or "") + " " + (event.get("event_text_segment") or "")[:700]).strip()
    ]
    cat_row = [[(event.get(col) or "") for col in categorical_cols]]
    X_text = text_vectorizer.transform(text_input)
    X_cat = cat_encoder.transform(cat_row)
    return sparse.hstack([X_text, X_cat], format="csr")


def _event_to_impact_features(event: dict, artifacts: dict, disruption_probability: float | None):
    # Backward compatibility for first regressor version.
    if "numeric_cols" not in artifacts:
        base = _event_to_shared_features(event, artifacts)
        if disruption_probability is None:
            disruption_probability = 0.0
        return sparse.hstack([base, sparse.csr_matrix([[float(disruption_probability)]])], format="csr")

    text_input = (
        (event.get("article_title") or "")
        + " "
        + (event.get("event_text_segment") or "")[:600]
    )
    text_input = [text_input]

    categorical_cols = artifacts.get("categorical_cols", [])
    numeric_cols = artifacts.get("numeric_cols", [])
    cat_encoder = artifacts["cat_encoder"]
    text_vectorizer = artifacts["text_vectorizer"]

    node_criticality = float(event.get("node_criticality") or 1.0)
    prob_map = event.get("ml_risk_probabilities") or {}

    event_for_features = {
        "article_source": event.get("article_source") or "",
        "matched_node": event.get("matched_node") or "",
        "ml_risk_label": event.get("ml_risk_label") or "UNKNOWN",
        "node_criticality": node_criticality,
        "ml_risk_confidence": float(event.get("ml_risk_confidence") or 0.0),
        "ml_prob_low": float(prob_map.get("LOW", 0.0)),
        "ml_prob_medium": float(prob_map.get("MEDIUM", 0.0)),
        "ml_prob_high": float(prob_map.get("HIGH", 0.0)),
    }

    X_text = text_vectorizer.transform(text_input)
    X_cat = cat_encoder.transform([[event_for_features.get(c, "") for c in categorical_cols]])
    X_num = sparse.csr_matrix([[float(event_for_features.get(c, 0.0)) for c in numeric_cols]])
    return sparse.hstack([X_text, X_cat, X_num], format="csr")


def attach_predicted_impact_scores(events: list[dict], impact_payload: dict) -> None:
    if not events:
        return
    model = impact_payload["model"]
    artifacts = impact_payload["artifacts"]
    for event in events:
        try:
            features = _event_to_impact_features(
                event,
                artifacts,
                disruption_probability=event.get("predicted_disruption_probability"),
            )
            predicted = float(model.predict(features)[0])
            event["predicted_impact_score"] = round(max(0.0, predicted), 3)
        except Exception as exc:
            event["predicted_impact_score"] = None
            print(f"⚠️ Impact prediction skipped for event: {exc}")


def attach_finbert_sentiment(events: list[dict]) -> None:
    """Populate sentiment_label / sentiment_score (FinBERT default; USE_FINBERT_RISK=0 skips)."""
    from src.sentiment_finbert import batch_analyze_finbert, finbert_enabled

    if not finbert_enabled() or not events:
        return
    texts = [
        ((e.get("article_title") or "") + " " + (e.get("event_text_segment") or ""))[:4000]
        for e in events
    ]
    try:
        outs = batch_analyze_finbert(texts)
        for e, o in zip(events, outs):
            e["sentiment_label"] = o["sentiment_label"]
            e["sentiment_score"] = o["sentiment_score"]
    except Exception as exc:
        print(f"⚠️ FinBERT sentiment skipped: {exc}")


def apply_batch_disruption_and_impact(events: list[dict]) -> None:
    """
    Run the same XGBoost disruption + impact heads as RSS on batch-pipeline events
    (call after match_node, optionally after temporal). Loads paths from env or defaults.
    Skips quietly if pickles are missing. Does not re-run FinBERT (risk_scoring sets sentiment).
    """
    if not events:
        return
    disruption_path = os.getenv(
        "DISRUPTION_CLASSIFIER_PATH",
        str(PROJECT_ROOT / "model_training" / "disruption_classifier.pkl"),
    )
    impact_path = os.getenv(
        "IMPACT_REGRESSOR_PATH",
        str(PROJECT_ROOT / "model_training" / "impact_regressor_v2.pkl"),
    )
    disruption_payload = None
    impact_payload = None
    try:
        disruption_payload = load_disruption_classifier(disruption_path)
        impact_payload = load_impact_regressor(impact_path)
        if not disruption_payload and not impact_payload:
            print(
                "ℹ️ Skipping disruption/impact: no valid pickles "
                f"(disruption={disruption_path!s}, impact={impact_path!s})."
            )
            return
        try:
            from src.load_to_db import SUPPLIER_NODES
        except Exception:
            SUPPLIER_NODES = {}
        for ev in events:
            node = ev.get("matched_node")
            ev["node_criticality"] = (
                SUPPLIER_NODES.get(node, {}).get("criticality", 1) if node else 1
            )
        if disruption_payload:
            attach_disruption_probabilities(events, disruption_payload)
        if impact_payload:
            attach_predicted_impact_scores(events, impact_payload)
    finally:
        if disruption_payload:
            del disruption_payload
        if impact_payload:
            del impact_payload
        gc.collect()


def attach_disruption_probabilities(events: list[dict], classifier_payload: dict) -> None:
    if not events:
        return
    model = classifier_payload["model"]
    artifacts = classifier_payload["artifacts"]
    for event in events:
        try:
            features = _event_to_shared_features(event, artifacts)
            prob = float(model.predict_proba(features)[0][1])
            event["predicted_disruption_probability"] = round(prob, 4)
        except Exception as exc:
            event["predicted_disruption_probability"] = None
            print(f"⚠️ Disruption classification skipped for event: {exc}")


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


def build_scored_event_dict(
    article_url: str,
    article_source: str,
    article_title: str,
    article_timestamp: str | None,
    event_text_segment: str,
    vectorizer,
    model,
    label_encoder=None,
) -> dict | None:
    """
    Legacy tri-class risk + ml_risk_* fields from classifier.pkl (same as RSS items).
    Used by feed_entry_to_event_dict and web_scrape JSON ingestion.
    """
    link = (article_url or "").strip()
    if not link or not link.startswith("http"):
        return None

    title = _strip_html(article_title or "")
    summary = _strip_html(event_text_segment or "")
    body_for_model = summary[:300] if summary else title[:300]
    model_input = f"{title} {body_for_model}".strip()
    if len(model_input) < 5:
        return None

    X = vectorizer.transform([model_input])
    raw_pred = model.predict(X)[0]
    if label_encoder is not None:
        pred = str(label_encoder.inverse_transform(np.asarray([raw_pred], dtype=int))[0])
        classes = [str(c) for c in label_encoder.classes_]
    else:
        pred = str(raw_pred)
        classes = [str(c) for c in model.classes_]
    prob_row = model.predict_proba(X)[0]
    prob_map = {c: round(float(p), 4) for c, p in zip(classes, prob_row)}
    confidence = max(prob_map.values()) if prob_map else None

    segment = summary if summary else title
    if len(segment) > 12000:
        segment = segment[:12000]

    return {
        "article_url": link,
        "article_source": article_source or "Unknown",
        "article_title": title or link,
        "article_timestamp": article_timestamp,
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
        "predicted_disruption_probability": None,
        "predicted_impact_score": None,
    }


def feed_entry_to_event_dict(entry, source_name: str, vectorizer, model, label_encoder=None) -> dict | None:
    link = (getattr(entry, "link", None) or getattr(entry, "id", None) or "").strip()
    title = _strip_html(getattr(entry, "title", "") or "")
    summary_raw = (
        getattr(entry, "summary", None)
        or getattr(entry, "description", None)
        or ""
    )
    summary = _strip_html(summary_raw)
    ts_raw = _entry_timestamp(entry)
    return build_scored_event_dict(
        link,
        source_name,
        title,
        ts_raw,
        summary if summary else title,
        vectorizer,
        model,
        label_encoder,
    )


def enrich_events_for_db(
    batch: list[dict],
    disruption_payload: dict | None,
    impact_payload: dict | None,
    *,
    is_background: bool = False,
    skip_temporal: bool = False,
    verbose: bool = False,
) -> list[dict]:
    """
    Shared pipeline: keywords, NER locations, geocode, node match, optional temporal,
    node_criticality, disruption + impact models. Mutates events in place.
    """
    if not batch:
        return batch

    n = len(batch)

    def log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    from src.preprocessing import NER_BATCH_SIZE, extract_locations_batch, detect_potential_events
    from src.geocoding import geocode_location_with_retry, save_geocode_cache
    from src.match_events_to_nodes import match_event_to_node

    log(f"[enrich] 1/5 keywords + event types ({n} articles)")
    for ev in batch:
        text_types = detect_potential_events(
            ev["event_text_segment"], ev.get("article_title", "")
        )
        meta_types = _event_types_from_webhose_meta(ev.get("webhose_meta"))
        ev["potential_event_types"] = list(dict.fromkeys(meta_types + text_types))

    if is_background:
        update_status(current_step="Extracting geographic locations via NER...", progress_percent=50)

    log(f"[enrich] 2/5 NER locations (batch size {NER_BATCH_SIZE}, device see preprocessing startup)")
    texts_for_ner = [ev["event_text_segment"] for ev in batch]
    locations_batch = extract_locations_batch(texts_for_ner)
    for ev, locs in zip(batch, locations_batch):
        pre_locs = (ev.get("webhose_meta") or {}).get("locations") or []
        ev["extracted_locations"] = list(dict.fromkeys(pre_locs + locs))

    if is_background:
        update_status(current_step="Geocoding and Matching Nodes...", progress_percent=60)

    log(f"[enrich] 3/5 geocode + supplier match ({n} articles, ~1.1s between geocoder calls when needed)")
    step = 1 if n <= 100 else max(1, n // 25)
    for i, ev in enumerate(batch):
        if ev["extracted_locations"]:
            lat, lon = geocode_location_with_retry(ev["extracted_locations"][0])
            ev["latitude"] = lat
            ev["longitude"] = lon
            ev["geocoded_location_text"] = ev["extracted_locations"][0] if lat is not None else None
            time.sleep(1.1)

        ev["matched_node"] = match_event_to_node(ev)
        if verbose and ((i + 1) % step == 0 or i == n - 1):
            log(
                f"  ... {i + 1}/{n}  node={ev.get('matched_node')!r} "
                f"lat={ev.get('latitude')} lon={ev.get('longitude')}"
            )
        if is_background:
            pct = 60 + int((i + 1) / n * 30)
            update_status(progress_percent=pct, items_processed=i + 1)

    save_geocode_cache(geocode_location_with_retry.cache)

    if not skip_temporal:
        if is_background:
            update_status(current_step="Extracting Temporal Projections...", progress_percent=85)
        log(f"[enrich] 4/5 temporal enrichment")
        from src.temporal_extraction import enrich_events_with_temporal_data

        batch[:] = enrich_events_with_temporal_data(batch)
    else:
        log("[enrich] 4/5 temporal skipped (--skip-temporal)")

    if impact_payload or disruption_payload:
        try:
            from src.load_to_db import SUPPLIER_NODES

            for ev in batch:
                node = ev.get("matched_node")
                ev["node_criticality"] = (
                    SUPPLIER_NODES.get(node, {}).get("criticality", 1) if node else 1
                )
        except Exception:
            for ev in batch:
                ev["node_criticality"] = 1

    log("[enrich] 5/5 FinBERT (optional) + disruption + impact models")
    attach_finbert_sentiment(batch)
    if disruption_payload:
        attach_disruption_probabilities(batch, disruption_payload)
    if impact_payload:
        attach_predicted_impact_scores(batch, impact_payload)

    log("[enrich] done")
    return batch


def fetch_and_build_events(feeds: list[dict], vectorizer, model, label_encoder=None) -> list[dict]:
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
            ev = feed_entry_to_event_dict(entry, source, vectorizer, model, label_encoder)
            if ev:
                events.append(ev)
    return events


def run_once(
    feeds_path: str,
    model_path: str,
    disruption_model_path: str | None,
    impact_model_path: str | None,
    skip_db: bool,
    is_background: bool = False,
) -> int:
    vectorizer, model, label_encoder = None, None, None
    disruption_payload = None
    impact_payload = None
    try:
        if is_background:
            update_status(is_running=True, current_step="Fetching RSS Feeds...", progress_percent=5, items_processed=0, total_items=0, error=None)
            
        feeds = load_feeds_config(feeds_path)
        vectorizer, model, label_encoder = load_classifier(model_path)
        disruption_payload = load_disruption_classifier(disruption_model_path)
        if disruption_model_path and not disruption_payload:
            print(f"⚠️ Disruption classifier not found at {disruption_model_path}; continuing without it.")
        impact_payload = load_impact_regressor(impact_model_path)
        if impact_model_path and not impact_payload:
            print(f"⚠️ Impact regressor not found at {impact_model_path}; continuing without it.")
        batch = fetch_and_build_events(feeds, vectorizer, model, label_encoder)
        print(f"Fetched {len(batch)} item(s) from RSS.")

        engine = None
        if batch:
            from src.load_to_db import get_db_engine, filter_new_events_by_url

            engine = get_db_engine()
            if engine:
                batch, nskip = filter_new_events_by_url(engine, batch)
                if nskip:
                    print(f"Skipped {nskip} item(s) already in database (by article_url).")

        if not batch:
            print("No items to enrich (empty feed or all duplicates).")
            if is_background:
                update_status(current_step="Idle", progress_percent=100, is_running=False)
            return 0

        print(f"Enriching {len(batch)} new item(s)...")
        if is_background:
            update_status(
                current_step="Classifying & Extracting Locations...",
                progress_percent=30,
                total_items=len(batch),
            )
        enrich_events_for_db(
            batch,
            disruption_payload,
            impact_payload,
            is_background=is_background,
            skip_temporal=False,
            verbose=not is_background,
        )

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

        from src.load_to_db import create_tables, upsert_events, get_all_events

        if engine is None:
            from src.load_to_db import get_db_engine as _get_engine

            engine = _get_engine()
        if not engine:
            print("❌ Database engine not available.")
            if is_background:
                update_status(error="Database engine not available.", is_running=False)
            return 0
        create_tables(engine)
        upsert_events(engine, batch, recompute_supplier_scores=True)
        
        # 5. Refresh XGBoost forecast snapshots for today
        if is_background:
            update_status(current_step="Refreshing forecast snapshots...", progress_percent=95)

        try:
            from sqlalchemy.orm import sessionmaker
            from src.forecast_snapshots import snapshot_all_nodes_for_date, SOURCE_SCHEDULED
            from datetime import date as _date
            SessionLocal = sessionmaker(bind=engine)
            with SessionLocal() as _sess:
                snapshot_all_nodes_for_date(_sess, _date.today(), source=SOURCE_SCHEDULED, method="xgboost")
        except Exception as _fe:
            print(f"⚠️  Forecast snapshot refresh failed (non-fatal): {_fe}")
        
        if is_background:
            update_status(current_step="Idle", progress_percent=100, is_running=False)
            
        return len(batch)
    except Exception as e:
        if is_background:
            update_status(error=str(e), is_running=False, current_step="Error")
        raise e
    finally:
        # --- Memory Cleanup ---
        # 1. Unload Transformer models (FinBERT, NER, spaCy)
        try:
            from src.sentiment_finbert import unload_finbert
            from src.preprocessing import unload_ner
            from src.temporal_extraction import unload_nlp
            unload_finbert()
            unload_ner()
            unload_nlp()
        except ImportError:
            pass

        # 2. Clear local XGBoost model objects
        print("📉 Clearing local XGBoost models and vectorizers...")
        if 'vectorizer' in locals():
            print(f"  - Deleting vectorizer")
            del vectorizer
        if 'model' in locals():
            print(f"  - Deleting model")
            del model
        if 'label_encoder' in locals():
            print(f"  - Deleting label_encoder")
            del label_encoder
        if 'disruption_payload' in locals():
            print(f"  - Deleting disruption_payload")
            del disruption_payload
        if 'impact_payload' in locals():
            print(f"  - Deleting impact_payload")
            del impact_payload
        
        # 3. Force multiple garbage collection passes
        gc.collect()
        gc.collect()
        gc.collect()
        
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                try:
                    import torch
                    torch.mps.empty_cache()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            import psutil
            import os
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / (1024 * 1024)
            print(f"📊 Current Resident Memory (RSS): {mem_mb:.2f} MB")
        except (ImportError, Exception):
            pass

        print("✅ RSS pipeline memory cleanup complete.")


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
    parser.add_argument(
        "--impact-model",
        default=os.getenv("IMPACT_REGRESSOR_PATH", str(PROJECT_ROOT / "model_training" / "impact_regressor_v2.pkl")),
        help="Optional impact regressor pickle path",
    )
    parser.add_argument(
        "--disruption-model",
        default=os.getenv("DISRUPTION_CLASSIFIER_PATH", str(PROJECT_ROOT / "model_training" / "disruption_classifier.pkl")),
        help="Optional disruption classifier pickle path",
    )
    parser.add_argument("--interval", type=int, default=0, help="If >0, re-run every N seconds")
    parser.add_argument("--skip-db", action="store_true", help="Only fetch + score; do not write DB")
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)

    if args.interval and args.interval > 0:
        while True:
            try:
                run_once(args.feeds, args.model, args.disruption_model, args.impact_model, args.skip_db)
            except KeyboardInterrupt:
                print("\nStopped.")
                sys.exit(0)
            except Exception as e:
                print(f"❌ Run failed: {e}")
            time.sleep(args.interval)
    else:
        try:
            n = run_once(args.feeds, args.model, args.disruption_model, args.impact_model, args.skip_db)
            print(f"Done. Processed {n} item(s).")
        except Exception as e:
            print(f"❌ {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
