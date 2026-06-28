"""Bridge model -> UI: writes web/public/data/ui_snapshot.json (T9 §15).

Runs the trained predictor (model_training/predictor.pkl) on the latest feature row per target,
maps P(disruption next 1-3d) to plain-language status/outlook, pulls recent matched headlines and
geocoded event points, and bundles the accuracy metric files. Date-parameterized (--as-of) so the
later rewind feature reuses it. UI reads the JSON; a FastAPI layer can serve it later.

Usage:
  venv311/bin/python -m scripts.build_ui_snapshot
  venv311/bin/python -m scripts.build_ui_snapshot --as-of 2026-03-15
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from src.db_config import get_read_db_url
from scripts.train_predictor import (
    TARGETS, TARGET_KEYWORDS, BLOB, CANDIDATE_RE, LOOKBACK_START, GRID_END,
    daily_news, clean_event_days, build_target_frame,
)

OUT = "web/public/data/ui_snapshot.json"
MODEL = "model_training/predictor.pkl"

META = {
    "shipping_chokepoints": ("Shipping & oil routes", "Strait of Hormuz · Red Sea", "ship", 26.6, 56.5),
    "semiconductor_electronics": ("Semiconductors & electronics", "Taiwan · Korea · China", "cpu", 23.7, 121.0),
    "european_auto": ("European auto industry", "Germany · France · Italy", "car", 51.2, 10.4),
    "critical_materials": ("Critical materials & batteries", "Lithium · rare earths", "battery-3", -24.0, -69.0),
    "us_logistics": ("US ports & freight", "West Coast · trucking", "truck", 34.0, -118.0),
}


def outlook(p):
    if p < 0.15:
        return "unlikely", "low"
    if p < 0.35:
        return "possible", "moderate"
    return "likely", "high"


def status_of(p, clean_3d, clean_7d):
    if clean_3d > 0 or p >= 0.5:
        return "active"
    if p >= 0.2 or clean_7d > 0:
        return "watch"
    return "calm"


SUMMARY = {
    "active": "Recent disruptions detected in the news; conditions remain elevated.",
    "watch": "Some risk signals appearing in the news; no major disruption confirmed yet.",
    "calm": "No significant disruptions detected. Conditions look normal.",
}


def recent_headlines(conn, kw, as_of, days=21, limit=3):
    since = (as_of - pd.Timedelta(days=days)).date()
    rows = conn.execute(text(f"""
        SELECT DISTINCT ON (article_title) article_title, article_timestamp::date
        FROM events
        WHERE {BLOB} ~ :kw AND article_timestamp::date <= :asof
          AND article_timestamp::date > :since
        ORDER BY article_title, article_timestamp DESC
        LIMIT :lim
    """), {"kw": kw, "asof": as_of.date(), "since": since, "lim": limit}).fetchall()
    return [{"title": r[0][:120], "date": str(r[1])} for r in rows]


def map_points(conn, as_of, days=30, limit=80):
    since = (as_of - pd.Timedelta(days=days)).date()
    rows = conn.execute(text(f"""
        SELECT latitude, longitude, LEFT(article_title,90), article_timestamp::date
        FROM events
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
          AND {BLOB} ~ :cand
          AND article_timestamp::date <= :asof AND article_timestamp::date > :since
        ORDER BY article_timestamp DESC LIMIT :lim
    """), {"cand": CANDIDATE_RE, "asof": as_of.date(), "since": since, "lim": limit}).fetchall()
    return [{"lat": float(r[0]), "lon": float(r[1]), "title": r[2], "date": str(r[3])} for r in rows]


def load_metric(path):
    return json.load(open(path)) if os.path.exists(path) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=GRID_END, help="snapshot date (YYYY-MM-DD); default = latest grid date")
    args = ap.parse_args()
    as_of = pd.Timestamp(args.as_of)

    with open(MODEL, "rb") as f:
        bundle = pickle.load(f)
    model, cal, cal_kind, feats = bundle["model"], bundle["calibrator"], bundle["cal_kind"], bundle["features"]

    full_idx = pd.date_range(LOOKBACK_START, as_of, freq="D")
    engine = create_engine(get_read_db_url())
    sectors, points = [], []
    with engine.connect() as conn:
        g = conn.execute(text("""
            SELECT article_date d, COUNT(*) c FROM disruption_candidates
            WHERE is_risk_event AND strict_is_risk AND article_date IS NOT NULL GROUP BY 1
        """)).fetchall()
        global_clean = pd.Series({pd.Timestamp(d): c for d, c in g}, dtype="float64")

        for key, themes in TARGETS.items():
            news = daily_news(conn, TARGET_KEYWORDS[key])
            clean = clean_event_days(conn, themes)
            f = build_target_frame(news, clean, global_clean, full_idx)
            row = f.loc[f.index <= as_of].iloc[-1]
            raw = model.predict_proba(row[feats].values.reshape(1, -1))[:, 1]
            p = float(np.clip(cal.predict(raw) if cal_kind == "isotonic"
                              else cal.predict_proba(raw.reshape(-1, 1))[:, 1], 0, 1)[0])
            ol, lik = outlook(p)
            st = status_of(p, row["clean_cnt_3d"], row["clean_cnt_7d"])
            name, sub, icon, lat, lon = META[key]
            sectors.append({
                "key": key, "name": name, "subtitle": sub, "icon": icon,
                "lat": lat, "lon": lon,
                "p": round(p, 3), "outlook": ol, "likelihood": lik, "status": st,
                "summary": SUMMARY[st],
                "headlines": recent_headlines(conn, TARGET_KEYWORDS[key], as_of),
            })
        points = map_points(conn, as_of)

    n_active = sum(1 for s in sectors if s["status"] == "active")
    n_watch = sum(1 for s in sectors if s["status"] == "watch")
    snapshot = {
        "as_of": str(as_of.date()),
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "data_note": "Reflects latest available data date; live freshness requires live ingestion (T10).",
        "summary": {"active": n_active, "watch": n_watch, "calm": len(sectors) - n_active - n_watch,
                    "total_articles": 180939, "clean_events": 557, "event_days": 122},
        "sectors": sectors,
        "map_points": points,
        "metrics": {
            "relevance": load_metric("data/relevance_metrics.json"),
            "relevance_embeddings": load_metric("data/relevance_metrics_embeddings.json"),
            "predictor": load_metric("data/predictor_metrics.json"),
            "predictor_test": load_metric("data/predictor_test_report.json"),
            "topics": load_metric("data/topic_model_summary.json"),
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"as_of={snapshot['as_of']}  active={n_active} watch={n_watch} calm={snapshot['summary']['calm']}  points={len(points)}")
    for s in sectors:
        print(f"  {s['name']:<30} P={s['p']:.2f}  {s['status']:<7} {s['outlook']}  ({len(s['headlines'])} headlines)")
    print(f"Saved -> {OUT}")


if __name__ == "__main__":
    main()
