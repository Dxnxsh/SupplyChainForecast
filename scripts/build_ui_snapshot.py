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
import xgboost as xgb
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
    if p >= 0.25:
        return "active"
    if p >= 0.10 or clean_3d >= 5:
        return "watch"
    return "calm"


TREND_DAYS = 30


FEATURE_PHRASES = {
    "vol_1d": "news volume spiked in the last day",
    "vol_3d": "news volume rose over the last 3 days",
    "vol_7d": "news volume rose over the last week",
    "vol_14d": "news volume has stayed elevated for two weeks",
    "sent_mean_3d": "average sentiment turned negative over 3 days",
    "sent_mean_7d": "average sentiment turned negative over the past week",
    "sent_min_3d": "a sharply negative story appeared in the last 3 days",
    "sent_min_7d": "a sharply negative story appeared this week",
    "sent_delta_3d": "sentiment shifted sharply",
    "kw_hits_1d": "risk-keyword mentions rose today",
    "kw_hits_3d": "risk-keyword mentions rose over 3 days",
    "clean_cnt_3d": "confirmed disruption events rose over 3 days",
    "clean_cnt_7d": "confirmed disruption events rose over the week",
    "clean_cnt_14d": "confirmed disruption events have stayed elevated for two weeks",
    "days_since_clean": "a confirmed disruption happened recently",
    "cross_clean_3d": "disruptions are rising in other sectors too",
    "dow": "day-of-week pattern in the historical data",
    "is_weekend": "weekend timing pattern in the historical data",
}

TOP_DRIVERS_N = 3


def top_drivers(model, feats, row):
    """Plain-language phrases for the top positive XGBoost pred_contribs on this row —
    the features actually pushing today's prediction toward disruption, not just globally
    important features."""
    dmat = xgb.DMatrix(row[feats].values.reshape(1, -1), feature_names=feats)
    contribs = model.get_booster().predict(dmat, pred_contribs=True)[0][:-1]  # drop bias term
    ranked = sorted(zip(feats, contribs), key=lambda x: x[1], reverse=True)
    phrases = []
    for name, val in ranked:
        if val <= 0 or len(phrases) >= TOP_DRIVERS_N:
            break
        phrase = FEATURE_PHRASES.get(name)
        if phrase:
            phrases.append(phrase)
    return phrases


def smoothed_series(model, cal, cal_kind, feats, tail):
    """3-day-trailing-smoothed calibrated P for each row of `tail`, in chronological order."""
    raw_ps = []
    for _, r in tail.iterrows():
        raw_i = model.predict_proba(r[feats].values.reshape(1, -1))[:, 1]
        p_i = float(np.clip(cal.predict(raw_i) if cal_kind == "isotonic"
                            else cal.predict_proba(raw_i.reshape(-1, 1))[:, 1], 0, 1)[0])
        raw_ps.append(p_i)
    return [float(np.mean(raw_ps[max(0, i - 2):i + 1])) for i in range(len(raw_ps))]


SUMMARY = {
    "active": "Recent disruptions detected in the news; conditions remain elevated.",
    "watch": "Some risk signals appearing in the news; no major disruption confirmed yet.",
    "calm": "No significant disruptions detected. Conditions look normal.",
}


def recent_headlines(conn, themes, kw, as_of, days=120, limit=3):
    since = (as_of - pd.Timedelta(days=days)).date()
    rows = conn.execute(text("""
        SELECT dc.article_title, dc.article_date, dc.article_url
        FROM disruption_candidates dc
        WHERE dc.is_risk_event AND dc.strict_is_risk
          AND dc.article_date <= :asof
          AND dc.article_date > :since
          AND dc.themes->>0 = ANY(:themes)
          AND (dc.model NOT LIKE 'emb-%' OR lower(dc.article_title) ~ :kw)
        ORDER BY dc.article_date DESC
        LIMIT :lim
    """), {"asof": as_of.date(), "since": since, "themes": themes,
           "kw": kw, "lim": limit}).fetchall()
    return [{"title": r[0][:120], "date": str(r[1]), "url": r[2]} for r in rows]


MIN_GEOCODE_CONFIDENCE = 0.65


def map_points(conn, as_of, days=30, limit=80):
    # geocode_confidence is only populated by the rebuilt spaCy+gazetteer geocoder (see
    # src/preprocessing.py, src/geocoding.py); older rows geocoded before that rebuild have
    # NULL confidence and are kept (dedup is the only filter available for them), but new
    # low-confidence matches (ambiguous city names) are dropped outright.
    since = (as_of - pd.Timedelta(days=days)).date()
    rows = conn.execute(text(f"""
        SELECT lat, lon, title, dt FROM (
            SELECT DISTINCT ON (latitude, longitude)
                   latitude AS lat, longitude AS lon,
                   LEFT(article_title, 90) AS title,
                   article_timestamp AS ts, article_timestamp::date AS dt
            FROM events
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
              AND (geocode_confidence IS NULL OR geocode_confidence >= :min_conf)
              AND {BLOB} ~ :cand
              AND article_timestamp::date <= :asof AND article_timestamp::date > :since
            ORDER BY latitude, longitude, article_timestamp DESC
        ) deduped
        ORDER BY ts DESC LIMIT :lim
    """), {"cand": CANDIDATE_RE, "asof": as_of.date(), "since": since, "lim": limit,
           "min_conf": MIN_GEOCODE_CONFIDENCE}).fetchall()
    return [{"lat": float(r[0]), "lon": float(r[1]), "title": r[2], "date": str(r[3])} for r in rows]


def load_metric(path):
    return json.load(open(path)) if os.path.exists(path) else None


LOW_DATA_TRAIN_POS = 30  # below this many training-positive days, flag as limited history


def data_confidence_of(train_pos):
    if train_pos is None:
        return "unknown"
    return "limited" if train_pos < LOW_DATA_TRAIN_POS else "normal"


def live_summary(conn):
    """Live dataset counts — replaces the hardcoded numbers."""
    total = conn.execute(text("SELECT COUNT(*) FROM events")).scalar() or 0
    clean = conn.execute(text(
        "SELECT COUNT(*) FROM disruption_candidates WHERE is_risk_event AND strict_is_risk"
    )).scalar() or 0
    event_days = conn.execute(text(
        "SELECT COUNT(DISTINCT article_date) FROM disruption_candidates "
        "WHERE is_risk_event AND strict_is_risk AND article_date IS NOT NULL"
    )).scalar() or 0
    return int(total), int(clean), int(event_days)


def load_feed(path="data/live_feed.json", limit=120) -> list:
    if not os.path.exists(path):
        return []
    try:
        entries = json.load(open(path))
        return entries[:limit]
    except Exception:
        return []


def max_db_date(conn) -> str | None:
    row = conn.execute(text("SELECT MAX(article_timestamp)::date FROM events")).fetchone()
    return str(row[0]) if row and row[0] else None


ALERT_STATE_PATH = "data/alert_state.json"
ALERTS_LOG_PATH = "data/alerts.json"
MAX_ALERTS = 200


def record_status_transitions(sectors, as_of):
    """Append an in-app alert for any sector whose status changed since the last
    live snapshot build. Only call this for live (non-rewind) runs — historical
    --as-of backfills would otherwise pollute the alert log with fake transitions."""
    prev_state = load_metric(ALERT_STATE_PATH) or {}
    alerts = load_metric(ALERTS_LOG_PATH) or []

    new_alerts = []
    for s in sectors:
        prev_status = prev_state.get(s["key"])
        if prev_status and prev_status != s["status"]:
            new_alerts.append({
                "id": f"{s['key']}-{pd.Timestamp.utcnow().isoformat()}",
                "ts": pd.Timestamp.utcnow().isoformat(),
                "as_of": str(as_of.date()),
                "sector_key": s["key"],
                "sector_name": s["name"],
                "from_status": prev_status,
                "to_status": s["status"],
                "p": s["p"],
                "headline": s["headlines"][0] if s["headlines"] else None,
            })
        prev_state[s["key"]] = s["status"]

    if new_alerts:
        alerts = (new_alerts + alerts)[:MAX_ALERTS]
        with open(ALERTS_LOG_PATH, "w") as f:
            json.dump(alerts, f, indent=2)

    with open(ALERT_STATE_PATH, "w") as f:
        json.dump(prev_state, f, indent=2)

    return new_alerts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None,
                    help="snapshot date (YYYY-MM-DD); default = max(article_timestamp) from DB")
    args = ap.parse_args()

    with open(MODEL, "rb") as f:
        bundle = pickle.load(f)
    model, cal, cal_kind, feats = bundle["model"], bundle["calibrator"], bundle["cal_kind"], bundle["features"]

    engine = create_engine(get_read_db_url())
    with engine.connect() as conn:
        db_max = max_db_date(conn)

    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
    elif db_max:
        as_of = pd.Timestamp(db_max)
    else:
        as_of = pd.Timestamp(GRID_END)

    full_idx = pd.date_range(LOOKBACK_START, as_of, freq="D")
    predictor_metrics = load_metric("data/predictor_metrics.json") or {}
    per_target = predictor_metrics.get("per_target", {})
    sectors, points = [], []
    with engine.connect() as conn:
        g = conn.execute(text("""
            SELECT article_date d, COUNT(*) c FROM disruption_candidates
            WHERE is_risk_event AND strict_is_risk AND article_date IS NOT NULL GROUP BY 1
        """)).fetchall()
        global_clean = pd.Series({pd.Timestamp(d): c for d, c in g}, dtype="float64")

        for key, themes in TARGETS.items():
            news = daily_news(conn, TARGET_KEYWORDS[key], end=str(as_of.date()))
            clean = clean_event_days(conn, themes)
            f = build_target_frame(news, clean, global_clean, full_idx)
            # Smooth P over a 3-day trailing window to reduce single-day jitter; keep
            # enough history to also expose a TREND_DAYS-long smoothed trend line.
            tail = f.loc[f.index <= as_of].iloc[-(TREND_DAYS + 2):]
            smoothed = smoothed_series(model, cal, cal_kind, feats, tail)
            p = smoothed[-1]
            trend = [{"date": str(tail.index[i].date()), "p": round(smoothed[i], 3)}
                     for i in range(len(tail))][-TREND_DAYS:]
            row = tail.iloc[-1]
            ol, lik = outlook(p)
            st = status_of(p, row["clean_cnt_3d"], row["clean_cnt_7d"])
            name, sub, icon, lat, lon = META[key]
            train_pos = per_target.get(key, {}).get("train_pos")
            sectors.append({
                "key": key, "name": name, "subtitle": sub, "icon": icon,
                "lat": lat, "lon": lon,
                "p": round(p, 3), "outlook": ol, "likelihood": lik, "status": st,
                "summary": SUMMARY[st],
                "headlines": recent_headlines(conn, themes, TARGET_KEYWORDS[key], as_of),
                "data_confidence": data_confidence_of(train_pos),
                "train_pos": train_pos,
                "trend": trend,
                "drivers": top_drivers(model, feats, row) if st != "calm" else [],
            })
        points = map_points(conn, as_of)
        total_articles, clean_events, event_days = live_summary(conn)

    if not args.as_of:
        record_status_transitions(sectors, as_of)

    n_active = sum(1 for s in sectors if s["status"] == "active")
    n_watch = sum(1 for s in sectors if s["status"] == "watch")

    # Live feed[] block — written by ingest_live each cycle
    feed = load_feed()

    snapshot = {
        "as_of": str(as_of.date()),
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "data_note": (
            "Live — updated each ingestion cycle (T10)."
            if db_max and db_max >= str(as_of.date())
            else "Reflects latest available data date; run ingest_live to update."
        ),
        "summary": {
            "active": n_active, "watch": n_watch,
            "calm": len(sectors) - n_active - n_watch,
            "total_articles": total_articles,
            "clean_events": clean_events,
            "event_days": event_days,
        },
        "sectors": sectors,
        "map_points": points,
        "feed": feed,
        "metrics": {
            "relevance": load_metric("data/relevance_metrics.json"),
            "relevance_embeddings": load_metric("data/relevance_metrics_embeddings.json"),
            "predictor": load_metric("data/predictor_metrics.json"),
            "predictor_test": load_metric("data/predictor_test_report.json"),
            "topics": load_metric("data/topic_model_summary.json"),
            "external_validation": load_metric("data/external_validation.json"),
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
