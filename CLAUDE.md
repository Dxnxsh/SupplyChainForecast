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
- `POST /api/ingest` — trigger one RSS ingest cycle immediately, on top of the schedule below
- `GET /api/health` — `{"ok": true, "db_max": "...", "ingest": {...}}`
- **Owns live ingestion**: as long as the API process is running, a background asyncio task
  calls `scripts.ingest_live.run_cycle()` every `INGEST_INTERVAL_SECONDS` (default 1800s), off
  the event loop (`asyncio.to_thread`) so it never blocks snapshot requests, bounded by
  `INGEST_CYCLE_TIMEOUT_S` (default 600s) so a hung cycle can't wedge the scheduler. This
  replaces running `scripts.ingest_live --interval` as a separate process — starting the API
  server is now sufficient to keep data fresh. Set `DISABLE_BACKGROUND_INGEST=true` to turn it
  off (e.g. for tests); `/api/health`'s `ingest` block reports `running`/`last_result`/
  `last_error` for visibility.

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

Live-ingest scheduler (`src/api.py`, all optional): `INGEST_INTERVAL_SECONDS` (default 1800),
`INGEST_CYCLE_TIMEOUT_S` (default 600), `INGEST_NO_GEOCODE` (default false — geocoding is
implemented and enabled by default, see below), `DISABLE_BACKGROUND_INGEST` (default false).

## Notes for future work

- `legacy/` is gitignored — do not treat anything under it as live code or configuration.
- The predictor's calibrator is sparse (~584 events), so raw single-day P is nearly 3-valued;
  always use/preserve the 3-day smoothing when touching prediction code.
- `data/live_feed.json` is the rolling live-feed list rendered on the Feed page; it's
  regenerated/appended by `scripts/ingest_live.py` each cycle.
- **Geocoding** (`add_geocode` in `scripts/ingest_live.py`, rebuilt 2026-07): location
  extraction is `src/preprocessing.py` (spaCy `en_core_web_sm`, GPE/LOC entities, offline, no
  LLM) and resolution is `src/geocoding.py` (offline gazetteer — `geonamescache` country/city
  data plus a small hand-curated table of maritime chokepoints like Hormuz/Suez/Bab-el-Mandeb
  that aren't cities or countries). Each match carries a `geocode_confidence` (0-1) score based
  on match specificity (chokepoint/country match ≈0.9-0.95, unique city match ≈0.85, ambiguous
  same-named city ≈0.6); `scripts/build_ui_snapshot.py::map_points()` drops anything below
  `MIN_GEOCODE_CONFIDENCE` (0.65) going forward, while keeping pre-rebuild rows (`NULL`
  confidence) since there's no way to score them retroactively. A `GENERIC_BLOCKLIST` in
  `src/geocoding.py` excludes continent/region words ("Asia", "the Middle East", etc.) that
  would otherwise spuriously match an obscure same-named town. `INGEST_NO_GEOCODE` now defaults
  to `false`; set it to `true` to disable geocoding (e.g. for a faster dry run) — it adds well
  under a second per article and doesn't meaningfully affect the ~30-60s a live cycle takes.
- **Predictor retrain cadence**: the calibrator is sparse (~584 labelled events as of 2026-07),
  so it's worth retraining periodically as the live-ingested dataset grows rather than on a fixed
  calendar schedule. Retrigger `venv311/bin/python -m scripts.train_predictor` when either (a) the
  labelled dataset (`disruption_candidates` where `is_risk_event AND strict_is_risk`) has grown by
  roughly 100+ new clean events since the last retrain, or (b) it's been over a month of live
  ingestion, whichever comes first. After retraining, compare `data/predictor_metrics.json`
  against the previous version before deploying the new `model_training/predictor.pkl`: walk-forward
  `mean_auc` shouldn't regress, and check `per_target[*].train_pos` — a sector crossing the
  `LOW_DATA_TRAIN_POS` threshold (30, in `scripts/build_ui_snapshot.py`) should see its "limited
  history" badge disappear from the UI, which is a good sanity signal that the retrain used the
  updated data. Keep the isotonic-vs-Platt calibration choice under review as `data/predictor_metrics.json`'s
  positive count grows — isotonic needs more data to avoid overfitting the calibration curve.
