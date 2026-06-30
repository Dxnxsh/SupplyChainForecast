"""FastAPI backend — serves live snapshots and supports date rewind.

Endpoints:
  GET /api/snapshot          → current snapshot (latest DB date)
  GET /api/snapshot?as_of=2026-06-01  → rewind to that date
  POST /api/ingest           → trigger one RSS ingest cycle
  GET /api/health            → {"ok": true, "db_max": "..."}

Run:
  venv311/bin/python -m uvicorn src.api:app --reload --port 8000
"""

from __future__ import annotations

import json
import os
import pickle
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(".env")

import numpy as np
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

from src.db_config import get_read_db_url
from scripts.train_predictor import (
    TARGETS, TARGET_KEYWORDS, BLOB, CANDIDATE_RE, LOOKBACK_START, GRID_END,
    daily_news, clean_event_days, build_target_frame,
)
from scripts.build_ui_snapshot import (
    META, SUMMARY, outlook, status_of, recent_headlines, map_points,
    live_summary, load_feed, max_db_date, load_metric,
)

app = FastAPI(title="Disruption Monitor API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_PATH = "model_training/predictor.pkl"

_model_cache = {}


def _load_model():
    if "bundle" not in _model_cache:
        with open(MODEL_PATH, "rb") as f:
            _model_cache["bundle"] = pickle.load(f)
    return _model_cache["bundle"]


def _build_snapshot(as_of: pd.Timestamp) -> dict:
    bundle = _load_model()
    model, cal, cal_kind, feats = bundle["model"], bundle["calibrator"], bundle["cal_kind"], bundle["features"]

    engine = create_engine(get_read_db_url())
    full_idx = pd.date_range(LOOKBACK_START, as_of, freq="D")
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
            tail = f.loc[f.index <= as_of].iloc[-3:]
            ps = []
            for _, r in tail.iterrows():
                raw_i = model.predict_proba(r[feats].values.reshape(1, -1))[:, 1]
                p_i = float(np.clip(cal.predict(raw_i) if cal_kind == "isotonic"
                                    else cal.predict_proba(raw_i.reshape(-1, 1))[:, 1], 0, 1)[0])
                ps.append(p_i)
            p = float(np.mean(ps))
            row = tail.iloc[-1]
            ol, lik = outlook(p)
            st = status_of(p, row["clean_cnt_3d"], row["clean_cnt_7d"])
            name, sub, icon, lat, lon = META[key]
            sectors.append({
                "key": key, "name": name, "subtitle": sub, "icon": icon,
                "lat": lat, "lon": lon,
                "p": round(p, 3), "outlook": ol, "likelihood": lik, "status": st,
                "summary": SUMMARY[st],
                "headlines": recent_headlines(conn, themes, TARGET_KEYWORDS[key], as_of),
            })
        points = map_points(conn, as_of)
        total_articles, clean_events, event_days = live_summary(conn)

    n_active = sum(1 for s in sectors if s["status"] == "active")
    n_watch = sum(1 for s in sectors if s["status"] == "watch")

    db_max = None
    with engine.connect() as conn:
        db_max = max_db_date(conn)

    feed = load_feed()

    return {
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
        },
    }


@app.get("/api/snapshot")
def get_snapshot(as_of: str | None = Query(None, description="YYYY-MM-DD date to rewind to")):
    engine = create_engine(get_read_db_url())
    if as_of:
        ts = pd.Timestamp(as_of)
    else:
        with engine.connect() as conn:
            db_max = max_db_date(conn)
        ts = pd.Timestamp(db_max) if db_max else pd.Timestamp(GRID_END)
    return _build_snapshot(ts)


@app.post("/api/ingest")
def trigger_ingest():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.ingest_live", "--no-geocode"],
        capture_output=True, text=True, timeout=300,
    )
    success = result.returncode == 0
    output_lines = result.stdout.strip().split("\n") if result.stdout else []
    summary_line = output_lines[-1] if output_lines else ""
    return {"ok": success, "summary": summary_line, "stderr": result.stderr[-500:] if result.stderr else ""}


@app.get("/api/health")
def health():
    engine = create_engine(get_read_db_url())
    with engine.connect() as conn:
        db_max = max_db_date(conn)
    return {"ok": True, "db_max": db_max}
