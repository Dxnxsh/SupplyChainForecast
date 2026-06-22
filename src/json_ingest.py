"""
Load web_scrape JSON articles, score with the same pipeline as RSS, upsert to PostgreSQL.

Expected JSON: root array of objects with:
  - label: "source;title;url;timestamp" (semicolon-separated, same as preprocessing)
  - text: article body

Usage:
  python -m src.json_ingest
  python -m src.json_ingest --dry-run --limit 20
  python -m src.json_ingest --reprocess-all
  python -m src.json_ingest --validate-artifacts-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

# Silence harmless scikit-learn feature name mismatch warnings
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_web_scrape_entries(directory: str) -> list:
    """Load all *.json lists from data/raw/web_scrape-style folder."""
    from src.preprocessing import load_raw_data

    return load_raw_data(directory)


def entries_to_scored_events(
    entries: list,
    vectorizer,
    model,
    label_encoder=None,
    *,
    limit: int | None = None,
) -> list[dict]:
    """Parse label/text entries and apply legacy classifier.pkl in batches (blazing fast!)."""
    from src.preprocessing import parse_entry_metadata
    from src.rss_ingest import _strip_html
    import numpy as np
    import torch
    from tqdm import tqdm

    events: list[dict] = []
    model_inputs: list[str] = []

    print(f"Preparing inputs for {len(entries)} entries...")
    for entry in tqdm(entries, desc="Preparing Inputs"):
        if limit is not None and len(events) >= limit:
            break
        meta = parse_entry_metadata(entry)
        link = (meta["url"] or "").strip()
        if not link or not link.startswith("http"):
            continue

        title = _strip_html(meta["title"] or "")
        summary = _strip_html(meta["original_text"] or "")
        body_for_model = summary[:300] if summary else title[:300]
        model_input = f"{title} {body_for_model}".strip()
        if len(model_input) < 5:
            continue

        segment = summary if summary else title
        if len(segment) > 12000:
            segment = segment[:12000]

        ev = {
            "article_url": link,
            "article_source": meta["source"] or "Unknown",
            "article_title": title or link,
            "article_timestamp": meta["timestamp"],
            "event_text_segment": segment,
            "potential_event_types": [],
            "extracted_locations": [],
        }
        if entry.get("webhose_meta"):
            ev["webhose_meta"] = entry["webhose_meta"]

        events.append(ev)
        model_inputs.append(model_input)

    if not events:
        return []

    print(f"Transforming text features using TF-IDF for {len(events)} valid entries...")
    X = vectorizer.transform(model_inputs)

    preds = model.predict(X)
    probs = model.predict_proba(X)

    if label_encoder is not None:
        pred_labels = label_encoder.inverse_transform(np.asarray(preds, dtype=int))
        classes = [str(c) for c in label_encoder.classes_]
    else:
        pred_labels = preds
        classes = [str(c) for c in model.classes_]

    ML_TO_RISK = {"HIGH": 85.0, "MEDIUM": 45.0, "LOW": 15.0}

    print("Mapping scores back to events...")
    for idx, ev in enumerate(events):
        pred_label = str(pred_labels[idx])
        prob_row = probs[idx]
        prob_map = {c: round(float(p), 4) for c, p in zip(classes, prob_row)}
        confidence = max(prob_map.values()) if prob_map else None

        ev["ml_risk_label"] = pred_label
        ev["ml_risk_confidence"] = confidence
        ev["ml_risk_probabilities"] = prob_map
        ev["risk_score"] = ML_TO_RISK.get(pred_label.upper(), 0.0)

    return events


def validate_two_stage_artifacts(
    disruption_path: str | None,
    impact_path: str | None,
) -> dict:
    """
    Inspect pickles for categorical_cols / numeric_cols so JSON path matches training.
    Returns a dict suitable for JSON logging.
    """
    from src.rss_ingest import load_disruption_classifier, load_impact_regressor

    report: dict = {}
    if disruption_path:
        p = load_disruption_classifier(disruption_path)
        if not p:
            report["disruption"] = {"error": f"not found or invalid: {disruption_path}"}
        else:
            art = p["artifacts"]
            report["disruption"] = {
                "categorical_cols": art.get("categorical_cols", []),
                "has_text_vectorizer": "text_vectorizer" in art,
                "has_cat_encoder": "cat_encoder" in art,
            }
    if impact_path:
        p = load_impact_regressor(impact_path)
        if not p:
            report["impact"] = {"error": f"not found or invalid: {impact_path}"}
        else:
            art = p["artifacts"]
            report["impact"] = {
                "categorical_cols": art.get("categorical_cols", []),
                "has_numeric_cols": "numeric_cols" in art,
                "numeric_cols": art.get("numeric_cols", []),
                "uses_disruption_probability_feature": p.get(
                    "uses_disruption_probability_feature", False
                ),
            }
            if art.get("numeric_cols"):
                report["impact"]["note"] = (
                    "Regressor expects legacy ml_risk_* / node_criticality-style numerics; "
                    "ensure build_scored_event_dict + enrich_events_for_db populate them."
                )
            else:
                report["impact"]["note"] = (
                    "Slim v2: text + categoricals + predicted_disruption_probability only."
                )
    return report


def _ckpt_path(checkpoint_dir: str, run_id: str, step: str) -> Path:
    return Path(checkpoint_dir) / run_id / f"{step}.jsonl"


def _save_checkpoint(checkpoint_dir: str, run_id: str, step: str, events: list[dict]) -> None:
    p = _ckpt_path(checkpoint_dir, run_id, step)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
    print(f"💾 Checkpoint saved: {p} ({len(events)} events)")


def _load_checkpoint(checkpoint_dir: str, run_id: str, step: str) -> list[dict] | None:
    p = _ckpt_path(checkpoint_dir, run_id, step)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    print(f"♻️  Resumed from checkpoint: {p} ({len(events)} events)")
    return events


def run_json_ingest(
    raw_dir: str,
    *,
    legacy_model_path: str,
    disruption_model_path: str | None,
    impact_model_path: str | None,
    limit: int | None = None,
    skip_db: bool = False,
    skip_temporal: bool = False,
    regenerate_forecasts: bool = True,
    reprocess_all: bool = False,
    run_id: str = "default",
    checkpoint_dir: str | None = None,
) -> int:
    ckpt = checkpoint_dir or os.getenv("CHECKPOINT_DIR", "")

    from src.rss_ingest import (
        enrich_events_for_db,
        load_classifier,
        load_disruption_classifier,
        load_impact_regressor,
    )

    # ── Step 1: score ────────────────────────────────────────────────────────
    batch = _load_checkpoint(ckpt, run_id, "01_scored") if ckpt else None
    if batch is None:
        entries = load_web_scrape_entries(raw_dir)
        if not entries:
            print(f"No entries loaded from {raw_dir}")
            return 0

        vectorizer, model, label_encoder = load_classifier(legacy_model_path)
        batch = entries_to_scored_events(entries, vectorizer, model, label_encoder, limit=limit)
        print(f"Scored {len(batch)} article(s) from JSON (legacy tri-class).")

        engine_tmp = None
        if batch and not reprocess_all:
            from src.load_to_db import filter_new_events_by_url, get_db_engine
            engine_tmp = get_db_engine()
            if engine_tmp:
                batch, nskip = filter_new_events_by_url(engine_tmp, batch)
                if nskip:
                    print(f"Skipped {nskip} item(s) already in database (by article_url).")

        if not batch:
            print("No items to enrich (empty batch or all duplicates).")
            return 0

        if ckpt:
            _save_checkpoint(ckpt, run_id, "01_scored", batch)

    # ── Step 2a: enrich without temporal (NER + geocode + FinBERT + disruption/impact) ──
    pre_temporal = _load_checkpoint(ckpt, run_id, "02a_pre_temporal") if ckpt else None
    if pre_temporal is None:
        disruption_payload = load_disruption_classifier(disruption_model_path)
        if disruption_model_path and not disruption_payload:
            print(f"⚠️ Disruption classifier not found at {disruption_model_path}; continuing without it.")
        impact_payload = load_impact_regressor(impact_model_path)
        if impact_model_path and not impact_payload:
            print(f"⚠️ Impact regressor not found at {impact_model_path}; continuing without it.")

        print(f"Running enrichment on {len(batch)} item(s)...")
        enrich_events_for_db(
            batch,
            disruption_payload,
            impact_payload,
            is_background=False,
            skip_temporal=True,
            verbose=True,
        )
        if ckpt:
            _save_checkpoint(ckpt, run_id, "02a_pre_temporal", batch)
    else:
        batch = pre_temporal

    # ── Step 2b: temporal enrichment ─────────────────────────────────────────
    enriched = _load_checkpoint(ckpt, run_id, "02_enriched") if ckpt else None
    if enriched is None:
        if not skip_temporal:
            from src.temporal_extraction import enrich_events_with_temporal_data
            batch[:] = enrich_events_with_temporal_data(batch)
        enriched = batch
        if ckpt:
            _save_checkpoint(ckpt, run_id, "02_enriched", enriched)
    else:
        batch = enriched

    if skip_db:
        for ev in batch[: min(20, len(batch))]:
            print(
                f"  p_disrupt={ev.get('predicted_disruption_probability')} "
                f"impact={ev.get('predicted_impact_score')} "
                f"node={ev.get('matched_node')} "
                f"{(ev.get('article_title') or '')[:72]}"
            )
        if len(batch) > 20:
            print(f"  ... and {len(batch) - 20} more")
        print(f"Dry-run / skip-db: not writing database ({len(batch)} events).")
        return len(batch)

    # ── Step 3: DB write ─────────────────────────────────────────────────────
    from src.load_to_db import create_tables, get_db_engine, upsert_events

    engine = get_db_engine()
    if not engine:
        print("❌ Database engine not available.")
        return 0
    create_tables(engine)
    upsert_events(engine, batch, recompute_supplier_scores=True)
    print(f"✅ Upserted {len(batch)} event(s).")

    if regenerate_forecasts:
        try:
            from sqlalchemy.orm import sessionmaker
            from src.forecast_snapshots import snapshot_all_nodes_for_date, SOURCE_SCHEDULED
            from datetime import date as _date
            SessionLocal = sessionmaker(bind=engine)
            with SessionLocal() as _sess:
                result = snapshot_all_nodes_for_date(_sess, _date.today(), source=SOURCE_SCHEDULED, method="xgboost")
            print(f"✅ Refreshed XGBoost forecast snapshots (saved: {result['saved']}, failed: {len(result['failed'])}).")
        except Exception as _fe:
            print(f"⚠️  Forecast snapshot refresh failed (non-fatal): {_fe}")

    return len(batch)


def main():
    parser = argparse.ArgumentParser(description="web_scrape JSON → same ML path as RSS → PostgreSQL")
    parser.add_argument(
        "--directory", "--dir",
        dest="dir",
        default=os.getenv("WEB_SCRAPE_DIR", str(PROJECT_ROOT / "data" / "raw" / "web_scrape")),
        help="Directory containing *.json (root array per file)",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("ML_CLASSIFIER_PATH", str(PROJECT_ROOT / "model_training" / "classifier.pkl")),
        help="Legacy tri-class classifier (vectorizer, model)",
    )
    parser.add_argument(
        "--disruption-model",
        default=os.getenv("DISRUPTION_CLASSIFIER_PATH", str(PROJECT_ROOT / "model_training" / "disruption_classifier.pkl")),
        help="Two-stage disruption classifier pickle",
    )
    parser.add_argument(
        "--impact-model",
        default=os.getenv("IMPACT_REGRESSOR_PATH", str(PROJECT_ROOT / "model_training" / "impact_regressor_v2.pkl")),
        help="Two-stage impact regressor pickle",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max articles to process")
    parser.add_argument("--skip-db", action="store_true", help="Enrich only; do not upsert")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Enrich and print sample scores; implies no DB write",
    )
    parser.add_argument(
        "--skip-temporal",
        action="store_true",
        help="Skip temporal enrichment (faster batch)",
    )
    parser.add_argument(
        "--no-forecasts",
        action="store_true",
        help="After DB write, skip generate_all_node_forecasts",
    )
    parser.add_argument(
        "--validate-artifacts-only",
        action="store_true",
        help="Print disruption/impact artifact schema and exit",
    )
    parser.add_argument(
        "--reprocess-all",
        action="store_true",
        help="Do not skip articles already in DB (by article_url); re-enrich and upsert all scored rows",
    )
    args = parser.parse_args()
    os.chdir(PROJECT_ROOT)

    if args.validate_artifacts_only:
        r = validate_two_stage_artifacts(args.disruption_model, args.impact_model)
        print(json.dumps(r, indent=2))
        return

    skip_db = args.skip_db or args.dry_run
    n = run_json_ingest(
        args.dir,
        legacy_model_path=args.model,
        disruption_model_path=args.disruption_model,
        impact_model_path=args.impact_model,
        limit=args.limit,
        skip_db=skip_db,
        skip_temporal=args.skip_temporal,
        regenerate_forecasts=not args.no_forecasts and not skip_db,
        reprocess_all=args.reprocess_all,
    )
    print(f"Done. {n} item(s).")


if __name__ == "__main__":
    main()
