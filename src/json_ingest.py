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
from pathlib import Path

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
    """Parse label/text entries and apply legacy classifier.pkl (same as RSS)."""
    from src.preprocessing import parse_entry_metadata
    from src.rss_ingest import build_scored_event_dict

    events: list[dict] = []
    for entry in entries:
        if limit is not None and len(events) >= limit:
            break
        meta = parse_entry_metadata(entry)
        ev = build_scored_event_dict(
            meta["url"],
            meta["source"],
            meta["title"],
            meta["timestamp"],
            meta["original_text"] or "",
            vectorizer,
            model,
            label_encoder,
        )
        if ev:
            events.append(ev)
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
) -> int:
    from src.rss_ingest import (
        enrich_events_for_db,
        load_classifier,
        load_disruption_classifier,
        load_impact_regressor,
    )

    entries = load_web_scrape_entries(raw_dir)
    if not entries:
        print(f"No entries loaded from {raw_dir}")
        return 0

    vectorizer, model, label_encoder = load_classifier(legacy_model_path)
    disruption_payload = load_disruption_classifier(disruption_model_path)
    if disruption_model_path and not disruption_payload:
        print(f"⚠️ Disruption classifier not found at {disruption_model_path}; continuing without it.")
    impact_payload = load_impact_regressor(impact_model_path)
    if impact_model_path and not impact_payload:
        print(f"⚠️ Impact regressor not found at {impact_model_path}; continuing without it.")

    batch = entries_to_scored_events(entries, vectorizer, model, label_encoder, limit=limit)
    print(f"Scored {len(batch)} article(s) from JSON (legacy tri-class).")

    engine = None
    if batch and not reprocess_all:
        from src.load_to_db import filter_new_events_by_url, get_db_engine

        engine = get_db_engine()
        if engine:
            batch, nskip = filter_new_events_by_url(engine, batch)
            if nskip:
                print(f"Skipped {nskip} item(s) already in database (by article_url).")

    if not batch:
        print("No items to enrich (empty batch or all duplicates).")
        return 0

    print(f"Running enrichment on {len(batch)} item(s)...")
    enrich_events_for_db(
        batch,
        disruption_payload,
        impact_payload,
        is_background=False,
        skip_temporal=skip_temporal,
        verbose=True,
    )

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

    from src.load_to_db import create_tables, get_db_engine, get_all_events, upsert_events

    if engine is None:
        engine = get_db_engine()
    if not engine:
        print("❌ Database engine not available.")
        return 0
    create_tables(engine)
    upsert_events(engine, batch, recompute_supplier_scores=True)
    print(f"✅ Upserted {len(batch)} event(s).")

    if regenerate_forecasts:
        from src.predictive_forecasting import generate_all_node_forecasts

        all_events = get_all_events(engine)
        if all_events:
            generate_all_node_forecasts(all_events)
            print("✅ Regenerated hybrid forecast files.")

    return len(batch)


def main():
    parser = argparse.ArgumentParser(description="web_scrape JSON → same ML path as RSS → PostgreSQL")
    parser.add_argument(
        "--dir",
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
