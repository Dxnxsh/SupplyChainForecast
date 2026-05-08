# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Supply chain disruption monitoring and forecasting: articles become structured events (NLP, geocoding, node matching, temporal hints), scored for risk, rolled up per supplier node, and combined with Prophet-style hybrid forecasts. **PostgreSQL** is the system of record. **FastAPI** (`src/main.py`) serves the API. **Live news** enters through **RSS ingestion** (`src/rss_ingest.py`). The **Vite + React** app in `chain-calm-main/` is the operator dashboard.

Two ways data gets into the database:

1. **Batch pipeline** — `run_predictive_pipeline.py`: raw JSON articles under `data/raw/web_scrape/` → JSONL stages in `data/processed/` → forecasts in `data/forecasts/` → `src/load_to_db.py` loads suppliers and events.
2. **RSS path** — On a schedule (background thread when the API starts) or **on demand** (`POST /admin/rss-ingest/trigger`): feeds from `config/rss_feeds.json` → relevance classifier → same enrichment stack as the batch path (event types, geocode, match node, temporal enrichment) → optional **disruption** and **impact** models → upsert via `load_to_db.upsert_events`.

## Commands

### Backend

```bash
# Full batch pipeline (preprocessing → DB load)
python run_predictive_pipeline.py

# API (project root)
venv311/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000

# RSS ingest once (CLI)
venv311/bin/python -m src.rss_ingest
venv311/bin/python -m src.rss_ingest --interval 600   # poll loop

# Single batch steps (optional)
venv311/bin/python -m src.preprocessing
venv311/bin/python -m src.filter_events
venv311/bin/python -m src.risk_scoring
venv311/bin/python -m src.geocoding
venv311/bin/python -m src.match_events_to_nodes
venv311/bin/python -m src.temporal_extraction
venv311/bin/python -m src.predictive_forecasting
venv311/bin/python -m src.load_to_db

# spaCy (first run)
venv311/bin/python -m spacy download en_core_web_sm
```

### Frontend (`chain-calm-main/`)

```bash
cd chain-calm-main
npm install
npm run dev
npm run build
npm test
```

### Model training (`model_training/`)

Scripts build labels/datasets and train pickles consumed at RSS time (and optional batch scoring). Examples: `train_classifier.py`, `train_two_stage_impact_models.py`, `label_with_openrouter.py`, `build_impact_dataset.py`. Default artifact paths are under **Environment** below.

### Hybrid weight tuning (optional)

`scripts/tune_hybrid_weights.py` uses `src/forecast_validation.py` to adjust news vs historical blend weights for forecasts.

## Environment variables

| Variable | Default / notes | Purpose |
|----------|-----------------|---------|
| `DB_CONNECTION_STRING` | `postgresql://postgres:your_password@localhost:5432/supply_chain_db` | Postgres for API and loaders |
| `RSS_FEEDS_PATH` | `config/rss_feeds.json` | JSON array of `{ "url", "source" }`; copy from `config/rss_feeds.example.json` |
| `ML_CLASSIFIER_PATH` | `model_training/classifier.pkl` | Sklearn vectorizer + model: article → `ml_risk_label` + coarse `risk_score` (`ML_TO_RISK` in `rss_ingest.py`) |
| `DISRUPTION_CLASSIFIER_PATH` | `model_training/disruption_classifier.pkl` | Optional; `predicted_disruption_probability` |
| `IMPACT_REGRESSOR_PATH` | `model_training/impact_regressor_v2.pkl` | Optional; `predicted_impact_score` (training scale ~0–300; see rollup) |
| `OPENROUTER_API_KEY` | _(required for AI summary)_ | `POST .../ai-summary` |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Default chat model |
| `OPENROUTER_HTTP_REFERER` | `http://127.0.0.1:8080` | OpenRouter header |
| `VITE_API_BASE_URL` | same browser host, port **8000** | Dashboard API base (`chain-calm-main/src/lib/config.ts`) |

## Architecture

### Batch data flow (`run_predictive_pipeline.py`)

Each step reads/writes JSONL under `data/processed/` (except forecasts):

```
data/raw/web_scrape/*.json
  → src/preprocessing.py          processed_events.jsonl
  → src/filter_events.py          filtered_events.jsonl
  → src/risk_scoring.py           scored_events.jsonl
  → src/geocoding.py              geocoded_events.jsonl
  → src/match_events_to_nodes.py  matched_events.jsonl
  → src/temporal_extraction.py    temporal_enriched_events.jsonl
  → src/predictive_forecasting.py data/forecasts/{node}_forecast.json
  → src/load_to_db.py             PostgreSQL (suppliers + events)
```

### RSS data flow (`src/rss_ingest.py`)

- Parse feeds → **classifier** assigns `ml_risk_label`, `ml_risk_probabilities`, and initial `risk_score`.
- **preprocessing**: `detect_potential_events`, `extract_locations_batch` (and related helpers).
- **geocoding**: `geocode_location_with_retry` (shared cache file under `data/` as configured in geocoding module).
- **matching**: `match_event_to_node` from `match_events_to_nodes`.
- **temporal**: `enrich_events_with_temporal_data` (single-event path used for batches).
- **disruption classifier** → `predicted_disruption_probability`.
- **impact regressor** → `predicted_impact_score`.
- **load_to_db.upsert_events** merges into `events`, then recomputes supplier rollups.

Background worker: started from FastAPI **lifespan** in `main.py` (~10 minute interval). Same env paths as manual trigger.

### Supplier catalog and rollups

- **Canonical node list** (lat/lon, country, **criticality** 1–5) lives in **`src/load_to_db.py`** (`SUPPLIER_NODES`) and is mirrored in **`src/match_events_to_nodes.py`** (`SUPPLIER_NODES`) — keep them aligned.
- Nodes: TSMC_Hsinchu, Foxconn_Zhengzhou, Port_of_Long_Beach, CATL_Ningde, Albemarle_Chile, Tesla_Berlin (criticalities 5,5,4,4,3,3 respectively).
- **API `impact_score`** on each event is still **risk_score × criticality** for list responses (`process_events_with_impact` in `main.py`).
- **`suppliers.current_risk_score`** (exposure index, 0–100) is recomputed in **`load_to_db._recompute_supplier_risk_scores`**:
  - Per-event **strength** = `min(100, predicted_impact_score/3)` if impact is present, else `risk_score`.
  - Only events with `risk_score > 0` or non-null `predicted_impact_score` count.
  - Prefer **last 30 days**; if none qualify, fall back to **all time** (same SQL pattern as in `main.py` for AI summary context).
  - **Exposure** = `min(100, 0.62 * avg(strength) + 0.38 * max(strength))`.

### Backend API (`src/main.py`)

FastAPI app version **1.2.0** (see `app = FastAPI(..., version=...)`).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Health / welcome JSON |
| GET | `/suppliers` | All supplier rows including `criticality`, `current_risk_score` |
| GET | `/events/latest` | Recent geocoded events; `impact_score` = risk × criticality |
| GET | `/events/by_node/{node_name}` | Same, filtered by `matched_node` |
| GET | `/events/forecasted` | Events with predictive temporal info |
| GET | `/events/forecasted/by_node/{node_name}` | Node-filtered predictive events |
| GET | `/summary` | Aggregate stats for dashboard |
| GET | `/suppliers/{node_name}/forecast` | Prophet points (`ForecastPoint`) |
| GET | `/suppliers/{node_name}/hybrid_forecast` | Hybrid series with news vs historical contributions |
| POST | `/suppliers/{node_name}/ai-summary` | OpenRouter narrative using rollup + recent events (also mounted at `/api/...` for proxies, hidden from schema) |
| POST | `/admin/rss-ingest/trigger` | Queue one RSS cycle |
| GET | `/admin/rss-ingest/status` | Progress object from `rss_ingest.ingestion_status` |

CORS is open (`*`) for development; tighten for production.

### Dashboard (`chain-calm-main/src/`)

- **`App.tsx`**: React Router — `/` map, `/suppliers`, `/forecast` & `/history` (resilience), `/news`, `/admin`.
- **`lib/api.ts`**: Typed `fetch` wrappers for the endpoints above (including RSS trigger/status and AI summary).
- **`lib/dataMappers.ts`**: Backend DTOs → UI models (exposure levels, disruption cards).
- UI: **shadcn/ui**, **TanStack Query**, **Recharts** / map components as used in pages.

### Domain constants (batch NLP / scoring)

- **Event types** (`src/preprocessing.py`): e.g. `Natural_Disaster`, `Labor_Issue`, `Logistics_Issue`, `Industrial_Accident`, `Political_Regulatory`, `Demand_Supply_Shift`, `Cyber_Attack`.
- **Risk weights** (`src/risk_scoring.py`): type weights plus VADER, urgency/intensifier keywords (used heavily in the batch path; RSS path leans on the trained classifier for headline-level risk).
- **Forecasting** (`src/predictive_forecasting.py`): hybrid Prophet + news; `CONFIDENCE_WEIGHTS` for temporal confidence tiers, `TIME_DECAY_FACTOR` for news decay.

### Data shapes

- **Raw article JSON**: `url`, `title`, `content`, `source`, `timestamp` (see pipeline inputs).
- **Event row** (DB / API): URLs, titles, timestamps, text segment, `potential_event_types`, `extracted_locations`, `matched_node`, `risk_score`, split scores `risk_relevance_score` / `risk_severity_score`, lat/lon, `temporal_info` JSONB, ML fields (`ml_risk_label`, `ml_risk_confidence`, `ml_risk_probabilities`), `predicted_disruption_probability`, `predicted_impact_score`.
- **Hybrid forecast JSON**: `ds`, `yhat`, `yhat_lower`, `yhat_upper`, `news_contribution`, `historical_contribution`, `method`.

## Repository layout (concise)

| Path | Role |
|------|------|
| `src/` | Pipeline modules, FastAPI app, RSS ingest, OpenRouter client |
| `config/` | `rss_feeds.json` (local), `rss_feeds.example.json` |
| `data/raw/`, `data/processed/`, `data/forecasts/` | Inputs and pipeline outputs (many gitignored) |
| `model_training/` | Training scripts and `.pkl` artifacts (some gitignored) |
| `chain-calm-main/` | Operator UI |
| `scripts/` | Optional tooling (e.g. hybrid weight tuning) |
| `run_predictive_pipeline.py` | Batch orchestration |
