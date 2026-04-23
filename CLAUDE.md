# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A full-stack supply chain disruption forecasting system. News articles are processed through an NLP pipeline to extract events, which are geocoded, risk-scored, matched to supplier nodes, and fed into a hybrid Prophet + news-based forecasting model. A FastAPI backend exposes the results; a React frontend visualizes them on a map with charts.

## Commands

### Backend

```bash
# Run the full 8-step data pipeline (preprocessing → DB load)
python run_predictive_pipeline.py

# Start the API server (from project root, not frontend/)
venv311/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000

# Run a single pipeline step directly
venv311/bin/python -m src.preprocessing
venv311/bin/python -m src.filter_events
venv311/bin/python -m src.risk_scoring
venv311/bin/python -m src.geocoding
venv311/bin/python -m src.match_events_to_nodes
venv311/bin/python -m src.temporal_extraction
venv311/bin/python -m src.predictive_forecasting
venv311/bin/python -m src.load_to_db

# One-time spaCy model download (required before first run)
venv311/bin/python -m spacy download en_core_web_sm
```

### Frontend

```bash
cd frontend
npm start          # Dev server at :3000
npm run build      # Production build
npm test           # Jest tests
```

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DB_CONNECTION_STRING` | `postgresql://postgres:your_password@localhost:5432/supply_chain_db` | PostgreSQL connection |
| `REACT_APP_API_BASE_URL` | auto-detected `{protocol}://{hostname}:8000` | Frontend → API URL |

## Architecture

### Data Pipeline (run by `run_predictive_pipeline.py`)

Each step reads from `data/processed/` and writes a new JSONL file:

```
data/raw/web_scrape/*.json
  → src/preprocessing.py        → processed_events.jsonl      (NLP event extraction: spaCy + BERT NER)
  → src/filter_events.py        → filtered_events.jsonl       (supply-chain relevance filter)
  → src/risk_scoring.py         → scored_events.jsonl         (VADER sentiment + weighted event type)
  → src/geocoding.py            → geocoded_events.jsonl       (Nominatim geocoder, retry/cache)
  → src/match_events_to_nodes.py→ matched_events.jsonl        (haversine + keyword → supplier node)
  → src/temporal_extraction.py  → temporal_enriched_events.jsonl (predicted dates + confidence)
  → src/predictive_forecasting.py → data/forecasts/{node}_forecast.json (Prophet + news hybrid)
  → src/load_to_db.py           → PostgreSQL (suppliers + events tables, JSONB fields)
```

### Supplier Nodes (hard-coded in `src/match_events_to_nodes.py`)

Six reference nodes with `criticality` (1–5): TSMC_Hsinchu (5), Foxconn_Zhengzhou (5), Port_of_Long_Beach (4), CATL_Ningde (4), Albemarle_Chile (3), Tesla_Berlin (3). Impact score = risk_score × criticality.

### Backend API (`src/main.py`) — FastAPI v1.2.0

Key endpoints:
- `GET /suppliers` — all nodes with criticality
- `GET /events/latest` — events with impact scores
- `GET /events/by_node/{node_name}` — node-filtered events
- `GET /summary` — dashboard stats
- `GET /suppliers/{node_name}/forecast` — 14-day Prophet forecast
- `GET /suppliers/{node_name}/hybrid_forecast` — news + historical forecast
- `GET /events/forecasted` / `GET /events/forecasted/by_node/{node_name}` — upcoming predicted events

### Frontend (`frontend/src/`)

- `App.js` — interactive Leaflet map + event list with filters (node, event type, current vs. forecasted)
- `ForecastChart.js` — Prophet forecast with confidence intervals
- `HybridForecastChart.js` — news contribution vs. historical contribution breakdown
- `config.js` — reads `REACT_APP_API_BASE_URL`

### Key Domain Constants

**Event types** (in `src/preprocessing.py`): `Natural_Disaster`, `Labor_Issue`, `Logistics_Issue`, `Industrial_Accident`, `Political_Regulatory`, `Demand_Supply_Shift`, `Cyber_Attack`

**Risk weights** (in `src/risk_scoring.py`): Natural_Disaster=10 down to Demand_Supply_Shift=5. Modified by VADER sentiment, urgency keywords, and intensifier keywords.

**Forecasting** (in `src/predictive_forecasting.py`): `CONFIDENCE_WEIGHTS = {high: 1.0, medium: 0.7, low: 0.4}`, `TIME_DECAY_FACTOR = 0.85`

### Data Formats

Raw input articles (JSON): `{url, title, content, source, timestamp}`

Processed event record (JSONL): `{article_url, article_source, article_title, article_timestamp, event_text_segment, potential_event_types[], extracted_locations[], matched_node, risk_score, latitude, longitude, temporal_info: {is_predictive, predicted_date, predicted_date_confidence, event_description}}`

Forecast output (JSON): `[{ds, yhat, yhat_lower, yhat_upper, news_contribution, historical_contribution, method}]`
