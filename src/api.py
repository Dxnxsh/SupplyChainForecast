"""FastAPI backend — serves live snapshots, supports date rewind, and owns live ingestion.

Endpoints:
  GET /api/snapshot          → current snapshot (latest DB date)
  GET /api/snapshot?as_of=2026-06-01  → rewind to that date
  POST /api/ingest           → trigger one RSS ingest cycle immediately (in addition to the
                                automatic background schedule below)
  GET /api/health            → {"ok": true, "db_max": "...", "ingest": {...}}

Background ingestion: as long as this process is running, an asyncio task calls
scripts.ingest_live.run_cycle() every INGEST_INTERVAL_SECONDS (default 1800s), in a worker
thread (asyncio.to_thread) so it never blocks snapshot requests. Set
DISABLE_BACKGROUND_INGEST=true to turn this off (e.g. for tests). This replaces running
`scripts.ingest_live --interval` as a separate process — the API server is now the single
source of live data freshness.

Run:
  venv311/bin/python -m uvicorn src.api:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import pickle
import sys
import time

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

INGEST_INTERVAL_SECONDS = int(os.environ.get("INGEST_INTERVAL_SECONDS", "1800"))
INGEST_CYCLE_TIMEOUT_S = int(os.environ.get("INGEST_CYCLE_TIMEOUT_S", "600"))
INGEST_NO_GEOCODE = os.environ.get("INGEST_NO_GEOCODE", "true").lower() != "false"
DISABLE_BACKGROUND_INGEST = os.environ.get("DISABLE_BACKGROUND_INGEST", "").lower() == "true"

_ingest_lock = asyncio.Lock()
_ingest_state: dict = {
    "enabled": not DISABLE_BACKGROUND_INGEST,
    "interval_s": INGEST_INTERVAL_SECONDS,
    "running": False,
    "last_started": None,
    "last_finished": None,
    "last_result": None,
    "last_error": None,
}


async def _run_one_cycle() -> dict:
    """Run one ingest cycle off the event loop, with a hard timeout so a hung cycle
    (e.g. a stalled HuggingFace hub check) can't wedge the scheduler forever."""
    from scripts.ingest_live import run_cycle

    _ingest_state["running"] = True
    _ingest_state["last_started"] = pd.Timestamp.utcnow().isoformat()
    try:
        summary = await asyncio.wait_for(
            asyncio.to_thread(
                run_cycle, skip_db=False, geocode=not INGEST_NO_GEOCODE,
                limit=None, verbose=False,
            ),
            timeout=INGEST_CYCLE_TIMEOUT_S,
        )
        _ingest_state["last_result"] = summary
        _ingest_state["last_error"] = None
        return summary
    except Exception as e:
        _ingest_state["last_error"] = str(e)
        raise
    finally:
        _ingest_state["running"] = False
        _ingest_state["last_finished"] = pd.Timestamp.utcnow().isoformat()


async def _ingest_loop():
    """Runs a cycle immediately on startup, then every INGEST_INTERVAL_SECONDS thereafter
    (measured from cycle start, like scripts.ingest_live --interval does)."""
    while True:
        if _ingest_lock.locked():
            await asyncio.sleep(5)  # a manual /api/ingest trigger is in flight — wait it out
            continue
        t0 = time.monotonic()
        async with _ingest_lock:
            try:
                await _run_one_cycle()
            except Exception as e:
                print(f"[scheduled ingest] cycle failed (continuing): {e}")
        elapsed = time.monotonic() - t0
        await asyncio.sleep(max(0, INGEST_INTERVAL_SECONDS - elapsed))


app = FastAPI(title="Disruption Monitor API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_background_task: asyncio.Task | None = None


@app.on_event("startup")
async def _start_background_ingest():
    global _background_task
    if DISABLE_BACKGROUND_INGEST:
        print("[ingest] background scheduler disabled (DISABLE_BACKGROUND_INGEST=true)")
        return
    print(f"[ingest] background scheduler starting (every {INGEST_INTERVAL_SECONDS}s)")
    _background_task = asyncio.create_task(_ingest_loop())


@app.on_event("shutdown")
async def _stop_background_ingest():
    if _background_task:
        _background_task.cancel()

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
async def trigger_ingest():
    if _ingest_lock.locked():
        return {"ok": False, "error": "an ingest cycle is already running", "state": _ingest_state}
    try:
        summary = await _run_one_cycle()
        return {"ok": True, "summary": summary}
    except asyncio.TimeoutError:
        return {"ok": False, "error": f"ingest cycle timed out after {INGEST_CYCLE_TIMEOUT_S}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/health")
def health():
    engine = create_engine(get_read_db_url())
    with engine.connect() as conn:
        db_max = max_db_date(conn)
    return {"ok": True, "db_max": db_max, "ingest": _ingest_state}
