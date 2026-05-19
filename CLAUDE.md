# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Supply chain disruption monitoring and forecasting: articles become structured events (NLP, geocoding, node matching, temporal hints), scored for risk, rolled up per supplier node, and combined with Prophet-style hybrid forecasts. **PostgreSQL** is the system of record. **FastAPI** (`src/main.py`) serves the API. **Live news** enters through **RSS ingestion** (`src/rss_ingest.py`). The **Vite + React** app in `chain-calm-main/` is the operator dashboard.

**ML stack (production paths):**

- **Headline tri-class risk** (LOW / MEDIUM / HIGH): TF-IDF + **XGBoost** (`model_training/classifier.pkl` as a **3-tuple**: vectorizer, model, `LabelEncoder`). Used in preprocessing (batch), RSS, and `json_ingest`.
- **Batch heuristic risk** (`risk_score`, relevance/severity): rule features + **FinBERT** sentiment by default (`src/sentiment_finbert.py`, `src/risk_scoring.py`); set `USE_FINBERT_RISK=0` for VADER.
- **Disruption + impact** (optional pickles): TF-IDF + categoricals + **XGBoost** classifier + **XGBoost** regressor (`disruption_classifier.pkl`, `impact_regressor_v2.pkl`). Same inference on **RSS** and **batch** via `apply_batch_disruption_and_impact`.

Two ways data gets into the database:

1. **Batch pipeline** — `run_predictive_pipeline.py`: raw JSON under `data/raw/web_scrape/` → filter → **FinBERT/VADER risk scoring** → geocode → match → optional temporal → **`apply_batch_disruption_and_impact`** (XGB disruption/impact) → optional Prophet → `load_to_db.populate_database`.
2. **RSS path** — Background worker or `POST /admin/rss-ingest/trigger`: `classifier.pkl` tri-class → enrichment (event types, NER, geocode, match, temporal) → **FinBERT** `sentiment_*` → disruption/impact → `upsert_events`.

**Web scrape JSON path** — `python -m src.json_ingest`: same scoring and enrichment pattern as RSS (uses `build_scored_event_dict` + `enrich_events_for_db`).

**Reference-style layers:** *collection* = RSS + `data/raw/web_scrape/`; *NLP / scoring* = `preprocessing`, `risk_scoring`, FinBERT, XGBoost heads; *persistence* = PostgreSQL (`src/load_to_db.py`, `src/db_config.py`); *visualization* = React + FastAPI. **Weak rule labels** (training only): `model_training/rule_based_disruption_labels.py` + `train_two_stage_impact_models.py --label-mode rules` (writes `*_rules.pkl` by default; manual CSV path remains default for production pickles).

## Commands

### Backend

```bash
# Full batch pipeline (interactive; checks xgboost, prophet, transformers, etc.)
python run_predictive_pipeline.py

# API (project root)
venv311/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000

# RSS ingest once (CLI)
venv311/bin/python -m src.rss_ingest
venv311/bin/python -m src.rss_ingest --interval 600   # poll loop

# Web scrape JSON → same enrichment as RSS
venv311/bin/python -m src.json_ingest
venv311/bin/python -m src.json_ingest --dry-run --limit 20

# Postgres sanity check (active DB; add --legacy for DB_CONNECTION_STRING_LEGACY)
venv311/bin/python check_db_status.py
venv311/bin/python check_db_status.py --legacy

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

| Script | Output | Notes |
|--------|--------|--------|
| `train_classifier.py` | `classifier.pkl` | TF-IDF + XGBoost + `LabelEncoder` (3-tuple) |
| `train_two_stage_impact_models.py` | `disruption_classifier.pkl`, `impact_regressor_v2.pkl` | XGB classifier + XGB regressor; `--label-mode rules` → `*_rules.pkl` |
| `train_impact_regressor.py` | `impact_regressor.pkl` | Legacy artifact shape (numeric + cat features); **XGBRegressor** |
| `retrain_with_feedback.py` | `classifier.pkl` | Same 3-tuple format as `train_classifier.py` |
| `evaluate_classifier.py` | — | Loads 2- or 3-tuple `classifier.pkl` |
| `build_impact_dataset.py`, `build_impact_hard_negative_pack.py` | CSVs | Read DB via `get_read_db_url()` (`DB_READ_URL` optional) |

On **macOS**, if `import xgboost` fails, install OpenMP: `brew install libomp`.

Also: `label_with_openrouter.py`, `label_data.py`. Default artifact paths are in **Environment** below.

### Hybrid weight tuning (optional)

`scripts/tune_hybrid_weights.py` uses `src/forecast_validation.py` to adjust news vs historical blend weights for forecasts.

## Environment variables

| Variable | Default / notes | Purpose |
|----------|-----------------|---------|
| `DB_CONNECTION_STRING` | `postgresql://postgres:your_password@localhost:5432/supply_chain_db` | Active Postgres: API, RSS, `load_to_db` (`src/db_config.py`) |
| `DB_CONNECTION_STRING_LEGACY` | _(unset)_ | Optional previous DB URL; `python check_db_status.py --legacy` |
| `DB_READ_URL` | _(unset)_ | Overrides active URL for read-only training scripts (`build_impact_dataset.py`, `build_impact_hard_negative_pack.py`) |
| `USE_FINBERT_RISK` | `1` (default) | FinBERT for batch sentiment + RSS `sentiment_*`; `0` / `false` / `off` → VADER (batch) and skip FinBERT in RSS enrichment |
| `FINBERT_MODEL` | `ProsusAI/finbert` | Transformers model id |
| `FINBERT_DEVICE` | auto | `cpu`, `cuda`, or `mps` to force device |
| `RSS_FEEDS_PATH` | `config/rss_feeds.json` | JSON array of `{ "url", "source" }`; copy from `config/rss_feeds.example.json` |
| `ML_CLASSIFIER_PATH` | `model_training/classifier.pkl` | 3-tuple `(vectorizer, XGBClassifier, LabelEncoder)`; legacy 2-tuple still loads |
| `DISRUPTION_CLASSIFIER_PATH` | `model_training/disruption_classifier.pkl` | XGBoost binary disruption; `predicted_disruption_probability` |
| `IMPACT_REGRESSOR_PATH` | `model_training/impact_regressor_v2.pkl` | XGBoost regressor; `predicted_impact_score` (~0–300 scale; see rollup) |
| `OPENROUTER_API_KEY` | _(required for AI summary)_ | `POST .../ai-summary` |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Default chat model |
| `OPENROUTER_HTTP_REFERER` | `http://127.0.0.1:8080` | OpenRouter header |
| `VITE_API_BASE_URL` | same browser host, port **8000** | Dashboard API base (`chain-calm-main/src/lib/config.ts`) |

## Architecture

### Batch data flow (`run_predictive_pipeline.py`)

Each step may write JSONL under `data/processed/` when you opt in to save intermediates:

```
data/raw/web_scrape/*.json
  → src/preprocessing.py          TF-IDF + XGBoost headline labels, NER, event types → processed_events.jsonl
  → src/filter_events.py          filtered_events.jsonl
  → src/risk_scoring.py           FinBERT (default) or VADER sentiment + heuristic risk → scored_events.jsonl; sets sentiment_label / sentiment_score
  → src/geocoding.py              geocoded_events.jsonl
  → src/match_events_to_nodes.py  matched_events.jsonl
  → src/temporal_extraction.py    temporal_enriched_events.jsonl (optional “full” run)
  → src/rss_ingest.apply_batch_disruption_and_impact  XGB disruption + impact (same pickles as RSS); skips if .pkl missing
  → src/predictive_forecasting.py data/forecasts/{node}_forecast.json (optional)
  → src/load_to_db.py             PostgreSQL (suppliers + events)
```

### RSS data flow (`src/rss_ingest.py`)

- Parse feeds → **`classifier.pkl`** (XGBoost tri-class) → `ml_risk_label`, `ml_risk_probabilities`, `risk_score` (`ML_TO_RISK` mapping).
- **Enrichment**: `detect_potential_events`, `extract_locations_batch`, geocode, `match_event_to_node`, optional `enrich_events_with_temporal_data`.
- **FinBERT** (default): `sentiment_label`, `sentiment_score` on each event.
- **Disruption / impact** pickles → `predicted_disruption_probability`, `predicted_impact_score`.
- **`load_to_db.upsert_events`** → supplier rollups (`_recompute_supplier_risk_scores`).

Background worker: FastAPI **lifespan** in `main.py` (~10 minute interval).

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

`Event` responses may include **`sentiment_label`** and **`sentiment_score`** when present in the database (optional fields; UI may ignore them).

### Dashboard (`chain-calm-main/src/`)

- **`App.tsx`**: React Router — `/` map, `/suppliers`, `/forecast` & `/history` (resilience), `/news`, `/admin`.
- **`lib/api.ts`**: Typed `fetch` wrappers for the endpoints above (including RSS trigger/status and AI summary).
- **`lib/dataMappers.ts`**: Backend DTOs → UI models (exposure levels, disruption cards).
- UI: **shadcn/ui**, **TanStack Query**, **Recharts** / map components as used in pages.

### Domain constants (batch NLP / scoring)

- **Event types** (`src/preprocessing.py`): e.g. `Natural_Disaster`, `Labor_Issue`, `Logistics_Issue`, `Industrial_Accident`, `Political_Regulatory`, `Demand_Supply_Shift`, `Cyber_Attack`.
- **Risk weights** (`src/risk_scoring.py`): type weights + **FinBERT** sentiment multiplier (default) or VADER if disabled; urgency/intensifier keywords. RSS **headline** risk comes from **XGBoost** `classifier.pkl`.
- **Forecasting** (`src/predictive_forecasting.py`): hybrid Prophet + news; `CONFIDENCE_WEIGHTS` for temporal confidence tiers, `TIME_DECAY_FACTOR` for news decay.

### Data shapes

- **Raw article JSON**: `url`, `title`, `content`, `source`, `timestamp` (see pipeline inputs).
- **Event row** (DB / API): URLs, titles, timestamps, text segment, `potential_event_types`, `extracted_locations`, `matched_node`, `risk_score`, `risk_relevance_score`, `risk_severity_score`, lat/lon, `temporal_info` JSONB, `ml_risk_label`, `ml_risk_confidence`, `ml_risk_probabilities`, `predicted_disruption_probability`, `predicted_impact_score`, **`sentiment_label`**, **`sentiment_score`** (when FinBERT ran or values were set).
- **Hybrid forecast JSON**: `ds`, `yhat`, `yhat_lower`, `yhat_upper`, `news_contribution`, `historical_contribution`, `method`.

## Repository layout (concise)

| Path | Role |
|------|------|
| `src/` | Pipeline modules, FastAPI, RSS, `db_config.py`, `sentiment_finbert.py`, `json_ingest.py`, OpenRouter client |
| `config/` | `rss_feeds.json` (local), `rss_feeds.example.json` |
| `data/raw/`, `data/processed/`, `data/forecasts/` | Inputs and pipeline outputs (many gitignored) |
| `model_training/` | Training scripts and `.pkl` artifacts (some gitignored) |
| `chain-calm-main/` | Operator UI |
| `scripts/` | Optional tooling (e.g. hybrid weight tuning, `backfill_forecast_snapshots.py` uses `db_config`) |
| `check_db_status.py` | Active or `--legacy` Postgres event counts |
| `run_predictive_pipeline.py` | Batch orchestration (interactive) |

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available skills: `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/connect-chrome`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/setup-gbrain`, `/retro`, `/investigate`, `/document-release`, `/document-generate`, `/codex`, `/cso`, `/autoplan`, `/plan-devex-review`, `/devex-review`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`, `/learn`.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
