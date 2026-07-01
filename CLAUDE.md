# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project overview

**Supply-chain disruption early-warning monitor (v2 rebuild).** News articles are ingested live
via RSS, scored for relevance with a MiniLM embedding classifier, sentiment-scored with FinBERT,
and matched into 5 fixed sectors. A pooled **XGBoost + isotonic calibration** model predicts
P(disruption in next 1-3 days) per sector from rolling-window news/event features. A React
dashboard (`web/`) reads a FastAPI backend (`src/api.py`) and supports rewinding to any past date.

This is a from-scratch v2. The prior project (Two-Stage XGBoost forecast snapshots, node-level
impact regression, `chain-calm-main/` frontend) lives under `legacy/` (gitignored, not part of
the active app — its own `legacy/CLAUDE.md` documents that old architecture and should not be
used for v2 work). Full v2 design rationale/spec: `DISRUPTION_REBUILD_DESIGN.md`.

## Architecture

**5 sectors monitored** (`scripts/train_predictor.py::TARGETS`, `scripts/build_ui_snapshot.py::META`):
shipping_chokepoints, semiconductor_electronics, european_auto, critical_materials, us_logistics.

**Live ingestion pipeline** (`scripts/ingest_live.py`, no LLM anywhere in this path):
```
RSS feeds (config/rss_feeds.json)
  → parse + dedup (article_url)
  → FinBERT sentiment (src/sentiment_finbert.py), signed [-1, +1]
  → INSERT events
  → MiniLM relevance classifier, P(disruption) ≥ 0.59 (scripts/live_label.py::Labeler)
  → theme routing (cosine sim vs 12 MiniLM prototype vectors, model_training/theme_prototypes.pkl)
  → INSERT disruption_candidates (is_risk_event=T, strict_is_risk=T)
  → scripts/build_ui_snapshot.py --as-of <max_date>  (regenerates web/public/data/ui_snapshot.json)
```

**Prediction** (`scripts/train_predictor.py`, `scripts/build_ui_snapshot.py`, `src/api.py`):
16 rolling-window features per (sector, date) → `model_training/predictor.pkl`
(XGBClassifier + isotonic/Platt calibrator, features-only bundle, no vectorizer) → P(disruption
next 1-3d). The API and snapshot builder both average P over the **last 3 days** to smooth
single-day jitter (the calibrator only has ~584 training events, so raw P is nearly discrete).
Status thresholds (`status_of`): P≥0.25 → active, P≥0.10 or clean_3d≥5 → watch, else calm.

**BERTopic** (`scripts/build_topic_model.py`) is an **offline-only** discovery layer — MiniLM
embeddings → UMAP → HDBSCAN over historical clean events, used to validate the 5 fixed sectors
and surface emergent themes. It is not in the live pipeline and does not feed the predictor.

**Backend** (`src/api.py`, FastAPI):
- `GET /api/snapshot` — current snapshot (latest DB date)
- `GET /api/snapshot?as_of=YYYY-MM-DD` — rewind to that date (recomputes features + prediction)
- `POST /api/ingest` — trigger one RSS ingest cycle
- `GET /api/health` — `{"ok": true, "db_max": "..."}`

**Frontend** (`web/`, Vite + React + react-router-dom, TypeScript):
- `web/src/App.tsx` — routes: `/` Map, `/sectors` Dashboard, `/products` Products, `/feed` Feed,
  `/accuracy` Accuracy
- `web/src/components/DateWheel.tsx` + `web/src/lib/DateContext.tsx` — horizontal date-rewind
  scrollwheel; drives `as_of` for every page via `useDate()`
- `web/src/lib/useSnapshot.ts` — fetches `/api/snapshot`, caches past dates in localStorage
  (`snap_v{N}_` prefix — bump `CACHE_VERSION` when the snapshot shape changes); the `"live"` key
  always refetches and is never cached, so live data can't go stale
- Falls back to static `web/public/data/ui_snapshot.json` / `data/snapshots/<date>.json` if the
  API is unreachable

**Database**: PostgreSQL, `events` (raw ingested articles) and `disruption_candidates` (relevance-
and theme-labeled subset used for training/features) tables. `src/db_config.py` reads
`DB_CONNECTION_STRING`; `get_read_db_url()` allows overriding with `DB_READ_URL` for read paths.

## Commands

### Backend
```bash
# API server
venv311/bin/uvicorn src.api:app --reload --port 8000

# One live ingest cycle
venv311/bin/python -m scripts.ingest_live                  # full cycle (geocode + DB writes)
venv311/bin/python -m scripts.ingest_live --skip-db         # dry-run, print only
venv311/bin/python -m scripts.ingest_live --no-geocode      # skip GLiNER2 geocoding (faster)
venv311/bin/python -m scripts.ingest_live --interval 1800   # poll every 30 min

# Rebuild the static UI snapshot (bridge model -> JSON; also called by ingest_live each cycle)
venv311/bin/python -m scripts.build_ui_snapshot
venv311/bin/python -m scripts.build_ui_snapshot --as-of 2026-03-15

# Retrain the predictor
venv311/bin/python -m scripts.train_predictor

# Relevance classifier / theme prototypes / topic model (offline, occasional retrain)
venv311/bin/python -m scripts.train_relevance_embeddings
venv311/bin/python -m scripts.build_theme_prototypes
venv311/bin/python -m scripts.build_topic_model

# Tune / gate the live labeler
venv311/bin/python -m scripts.live_label --tune
venv311/bin/python -m scripts.live_label --fixture
```

### Frontend
```bash
cd web
npm run dev       # Vite dev server
npm run build      # tsc -b && vite build
npm run preview
```

## Models (gitignored binaries, tracked metrics)

| Model | File | Tracked metrics |
|---|---|---|
| Relevance (MiniLM embeddings + logreg, thr=0.59) | `model_training/relevance_classifier_emb.pkl` | `data/relevance_metrics_embeddings.json` |
| Relevance (TF-IDF baseline) | `model_training/relevance_classifier.pkl` | `data/relevance_metrics.json` |
| Theme prototypes (12 MiniLM vectors) | `model_training/theme_prototypes.pkl` | — |
| Predictor (XGBoost + isotonic) | `model_training/predictor.pkl` | `data/predictor_metrics.json`, `data/predictor_test_report.json` |
| Topic model (BERTopic, offline) | `model_training/bertopic_model/` | `data/topic_model_summary.json`, `data/topic_assignments.csv` |

`src/api.py` and `scripts/build_ui_snapshot.py` both load these metric JSON files into the
snapshot's `metrics` block, which feeds the Accuracy page.

## Environment (.env, never print keys in full — check by length/prefix only)

`DB_CONNECTION_STRING`, `PERIGON_API_KEY` (optional feed source), `GEMINI_API_KEY`,
`OPENROUTER_API_KEY`, `OPENMODEL_API_KEY` (LLM keys — **not used by the live ingestion path**,
`scripts/ingest_live.py` is explicitly LLM-free; these remain for offline/legacy tooling only),
`FINBERT_MODEL`, `USE_FINBERT_RISK`, `TORCH_DEVICE`, `RSS_FEEDS_PATH`.

## Notes for future work

- `legacy/` is gitignored — do not treat anything under it as live code or configuration.
- The predictor's calibrator is sparse (~584 events), so raw single-day P is nearly 3-valued;
  always use/preserve the 3-day smoothing when touching prediction code.
- `data/live_feed.json` is the rolling live-feed list rendered on the Feed page; it's
  regenerated/appended by `scripts/ingest_live.py` each cycle.
