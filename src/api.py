"""FastAPI backend — serves live snapshots, supports date rewind, and owns live ingestion.

Endpoints:
  GET /api/snapshot          → current snapshot (latest DB date)
  GET /api/snapshot?as_of=2026-06-01  → rewind to that date
  POST /api/ingest           → trigger one RSS ingest cycle immediately (in addition to the
                                automatic background schedule below)
  GET /api/health            → {"ok": true, "db_max": "...", "ingest": {...}}

Background ingestion: as long as this process is running, an asyncio task spawns
`python -m scripts.ingest_live` as a fresh subprocess every INGEST_INTERVAL_SECONDS (default
1800s) — see `_run_one_cycle()` for why it's a subprocess rather than an in-process
asyncio.to_thread call (FinBERT's MPS backend has thread-safety issues across repeated calls
in one long-lived process). Set DISABLE_BACKGROUND_INGEST=true to turn this off (e.g. for
tests). The API server is still the single source of live data freshness — you don't need to
run `scripts.ingest_live --interval` separately.

Run:
  venv311/bin/python -m uvicorn src.api:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import pickle
import subprocess
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
    live_summary, load_feed, max_db_date, load_metric, data_confidence_of,
    smoothed_series, TREND_DAYS, top_drivers,
)

INGEST_INTERVAL_SECONDS = int(os.environ.get("INGEST_INTERVAL_SECONDS", "1800"))
INGEST_CYCLE_TIMEOUT_S = int(os.environ.get("INGEST_CYCLE_TIMEOUT_S", "600"))
INGEST_NO_GEOCODE = os.environ.get("INGEST_NO_GEOCODE", "false").lower() == "true"
DISABLE_BACKGROUND_INGEST = os.environ.get("DISABLE_BACKGROUND_INGEST", "").lower() == "true"

# Single shared engine + pool for the process lifetime — request handlers must reuse this
# rather than calling create_engine() per-request, which leaks a new connection pool each time.
engine = create_engine(get_read_db_url(), pool_pre_ping=True)

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
    """Run one ingest cycle as a fresh subprocess, not in-process via asyncio.to_thread.

    FinBERT's MPS (Apple GPU) backend is a module-level singleton (src/sentiment_finbert.py)
    that gets reused across every scheduled cycle for the life of this process; each cycle
    previously ran via asyncio.to_thread on a thread-pool worker that isn't guaranteed to be
    the same OS thread twice, and Metal command buffer submission isn't safe to interleave
    across threads — this caused cycles to intermittently hang until INGEST_CYCLE_TIMEOUT_S.
    Forcing FinBERT onto CPU instead avoided the MPS hang but crashed the whole process with
    a multiprocessing resource-tracker corruption that only reproduced inside uvicorn's
    async/threaded context (never in a plain CLI run with the identical CPU setting).

    A fresh subprocess sidesteps both failure modes entirely — every cycle gets an isolated
    process with its own single-threaded MPS context, identical to a plain CLI invocation
    (which has always been reliable and fast, ~40s for a few hundred articles), at the cost
    of a small process-startup overhead per cycle. This also matches the already-proven
    pattern `rebuild_snapshot()` uses elsewhere in this file for scripts.build_ui_snapshot.
    """
    _ingest_state["running"] = True
    _ingest_state["last_started"] = pd.Timestamp.utcnow().isoformat()
    cmd = [sys.executable, "-m", "scripts.ingest_live", "--verbose"]
    if INGEST_NO_GEOCODE:
        cmd.append("--no-geocode")
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True),
            timeout=INGEST_CYCLE_TIMEOUT_S,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ingest_live exited {result.returncode}: {result.stderr[-800:]}")
        summary = {"stdout_tail": result.stdout[-800:]}
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


# _build_snapshot() re-scans `events`/`disruption_candidates` (10 queries incl. regex/JSONB
# scans) plus model inference — routinely tens of seconds. A date is "closed" once db_max (the
# latest ingested article date) has moved past it: closed dates are immutable, so they're
# cached in memory (L1) *and* persisted to disk (L2) so a restart doesn't lose already-computed
# history. db_max itself is the only date still receiving live ingestion — it's memory-only,
# invalidated whenever a background ingest cycle finishes rather than on a timer, so it can
# never serve stale live data.
_snapshot_cache: dict[str, tuple[dict, str | None]] = {}

CACHE_DIR = "data/api_cache"
SNAPSHOT_CACHE_DIR = os.path.join(CACHE_DIR, "snapshots")
CACHE_META_PATH = os.path.join(CACHE_DIR, "meta.json")
CACHE_SCHEMA = 1


def _predictor_mtime() -> float | None:
    try:
        return os.path.getmtime(MODEL_PATH)
    except OSError:
        return None


def _init_disk_cache() -> None:
    """Wipe the persisted snapshot cache whenever its schema or the predictor model has changed
    since it was written. Closed-day entries are never re-validated once cached, so a stale disk
    cache would otherwise silently keep serving snapshots computed by a superseded model (or a
    since-fixed feature bug) forever."""
    os.makedirs(SNAPSHOT_CACHE_DIR, exist_ok=True)
    meta = {"schema": CACHE_SCHEMA, "predictor_mtime": _predictor_mtime()}
    stale = True
    if os.path.exists(CACHE_META_PATH):
        try:
            with open(CACHE_META_PATH) as f:
                stale = json.load(f) != meta
        except (OSError, json.JSONDecodeError):
            stale = True
    if stale:
        for name in os.listdir(SNAPSHOT_CACHE_DIR):
            if name.endswith(".json"):
                os.remove(os.path.join(SNAPSHOT_CACHE_DIR, name))
        with open(CACHE_META_PATH, "w") as f:
            json.dump(meta, f)


_init_disk_cache()


def _snapshot_disk_path(key: str) -> str:
    return os.path.join(SNAPSHOT_CACHE_DIR, f"{key}.json")


def _read_disk_snapshot(key: str) -> dict | None:
    try:
        with open(_snapshot_disk_path(key)) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_disk_snapshot(key: str, data: dict) -> None:
    path = _snapshot_disk_path(key)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)  # atomic — a killed write can't leave a half-written file behind


def _current_metrics() -> dict:
    return {
        "relevance": load_metric("data/relevance_metrics.json"),
        "relevance_embeddings": load_metric("data/relevance_metrics_embeddings.json"),
        "predictor": load_metric("data/predictor_metrics.json"),
        "predictor_test": load_metric("data/predictor_test_report.json"),
        "topics": load_metric("data/topic_model_summary.json"),
        "external_validation": load_metric("data/external_validation.json"),
    }


def _with_fresh_feed_and_metrics(data: dict) -> dict:
    """feed and metrics are cheap local-file reads that change independently of the snapshot's
    own date — always serve the latest even when the rest of the snapshot came from cache."""
    out = dict(data)
    out["feed"] = load_feed()
    out["metrics"] = _current_metrics()
    return out


def _is_closed(date_str: str, db_max: str | None) -> bool:
    """A snapshot date is closed (immutable, safe to persist) once db_max has moved past it.
    If db_max is unknown (empty DB), nothing is closed yet."""
    return bool(db_max) and date_str < db_max


def _cached_snapshot(ts: pd.Timestamp, db_max: str | None) -> dict:
    key = str(ts.date())
    closed = _is_closed(key, db_max)

    cached = _snapshot_cache.get(key)
    if cached is not None:
        data, built_after = cached
        if closed or built_after == _ingest_state["last_finished"]:
            return _with_fresh_feed_and_metrics(data)

    if closed:
        disk = _read_disk_snapshot(key)
        if disk is not None:
            _snapshot_cache[key] = (disk, _ingest_state["last_finished"])
            return _with_fresh_feed_and_metrics(disk)

    data = _build_snapshot(ts)
    _snapshot_cache[key] = (data, _ingest_state["last_finished"])
    if closed:
        _write_disk_snapshot(key, data)
    return _with_fresh_feed_and_metrics(data)


def _build_snapshot(as_of: pd.Timestamp) -> dict:
    bundle = _load_model()
    model, cal, cal_kind, feats = bundle["model"], bundle["calibrator"], bundle["cal_kind"], bundle["features"]

    full_idx = pd.date_range(LOOKBACK_START, as_of, freq="D")
    per_target = (load_metric("data/predictor_metrics.json") or {}).get("per_target", {})
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
        "metrics": _current_metrics(),
    }


@app.get("/api/snapshot")
def get_snapshot(as_of: str | None = Query(None, description="YYYY-MM-DD date to rewind to")):
    with engine.connect() as conn:
        db_max = max_db_date(conn)
    ts = pd.Timestamp(as_of) if as_of else (pd.Timestamp(db_max) if db_max else pd.Timestamp(GRID_END))
    return _cached_snapshot(ts, db_max)


@app.get("/api/alerts")
def get_alerts(limit: int = Query(50, ge=1, le=200)):
    alerts = load_metric("data/alerts.json") or []
    return alerts[:limit]


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
    with engine.connect() as conn:
        db_max = max_db_date(conn)
    return {"ok": True, "db_max": db_max, "ingest": _ingest_state}
