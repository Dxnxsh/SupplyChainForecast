# Chain Calm — Supply Chain Risk Intelligence Platform

A full-stack system for monitoring and forecasting supply chain disruptions. News articles are ingested via RSS and web scrape, processed through a multi-stage NLP + ML pipeline, scored for risk, matched to critical supplier nodes, and surfaced through a React operator dashboard with 14-day risk forecasts.

**Stack:** Python · FastAPI · PostgreSQL · XGBoost · Prophet · FinBERT · spaCy · Vite + React · shadcn/ui · Recharts

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Data Pipeline](#data-pipeline)
- [ML Stack](#ml-stack)
- [Forecasting Engine](#forecasting-engine)
- [Supplier Nodes](#supplier-nodes)
- [API Reference](#api-reference)
- [Dashboard](#dashboard)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [Repository Layout](#repository-layout)

---

## System Architecture

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {
  'primaryColor': '#f0f9ff',
  'primaryBorderColor': '#0ea5e9',
  'primaryTextColor': '#0c4a6e',
  'lineColor': '#94a3b8',
  'clusterBkg': '#f8fafc',
  'clusterBorder': '#cbd5e1',
  'titleColor': '#1e293b',
  'edgeLabelBackground': '#ffffff'
}}}%%
flowchart TD
    classDef source  fill:#fff7ed,stroke:#f97316,color:#7c2d12,font-weight:bold
    classDef ingest  fill:#f0f9ff,stroke:#0ea5e9,color:#0c4a6e,font-weight:bold
    classDef store   fill:#eef2ff,stroke:#6366f1,color:#312e81,font-weight:bold
    classDef api     fill:#ecfdf5,stroke:#10b981,color:#064e3b,font-weight:bold
    classDef ml      fill:#fff1f2,stroke:#f43f5e,color:#881337,font-weight:bold
    classDef ui      fill:#f5f3ff,stroke:#8b5cf6,color:#4c1d95,font-weight:bold

    RSS["RSS Feeds\nconfig/rss_feeds.json"]:::source
    WS["Web Scrape JSONs\ndata/raw/web_scrape/"]:::source

    RINGEST["RSS Ingest\nsrc/rss_ingest.py\nbackground worker · 10 min"]:::ingest
    BATCH["Batch Pipeline\nrun_predictive_pipeline.py\ninteractive · full history"]:::ingest

    DB[("PostgreSQL\nsuppliers · events\nforecast_snapshots")]:::store

    API["FastAPI  port 8000\nsrc/main.py  v1.2.0"]:::api
    SNAP["Two-Stage XGBoost\nSnapshot Engine\nforecast_snapshots.py"]:::ml

    UI["React Dashboard\nchain-calm-main/\nVite + shadcn/ui"]:::ui

    RSS  --> RINGEST
    WS   --> BATCH
    RINGEST -->|"upsert_events"| DB
    BATCH   -->|"populate_database"| DB
    DB      -->|"read"| API
    DB      <-->|"read / write snapshots"| SNAP
    API     -->|"TanStack Query"| UI
```

---

## Data Pipeline

### Batch Pipeline

Each stage writes optional JSONL intermediates to `data/processed/`:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {
  'primaryColor': '#f0f9ff',
  'primaryBorderColor': '#0ea5e9',
  'primaryTextColor': '#0c4a6e',
  'lineColor': '#94a3b8',
  'edgeLabelBackground': '#ffffff'
}}}%%
flowchart TD
    classDef nlp     fill:#f0f9ff,stroke:#0ea5e9,color:#0c4a6e
    classDef score   fill:#fff7ed,stroke:#f97316,color:#7c2d12
    classDef geo     fill:#ecfdf5,stroke:#10b981,color:#064e3b
    classDef ml      fill:#fff1f2,stroke:#f43f5e,color:#881337
    classDef store   fill:#eef2ff,stroke:#6366f1,color:#312e81,font-weight:bold

    A["Raw JSON Articles\ndata/raw/web_scrape/"]:::nlp
    B["preprocessing.py\nTF-IDF + XGBoost headline labels\nspaCy NER · event type detection"]:::nlp
    C["filter_events.py\nRemove low-signal articles"]:::nlp
    D["risk_scoring.py\nFinBERT sentiment\nrisk_score · relevance · severity"]:::score
    E["geocoding.py\nExtracted locations → lat / lon"]:::geo
    F["match_events_to_nodes.py\nStrategy 1: keyword anchors\nStrategy 2: Haversine proximity\nStrategy 3: country fallback"]:::geo
    G["temporal_extraction.py\nPredict future event dates\ntemporal_info JSONB"]:::ml
    H["Disruption + Impact XGB\ndisruption_classifier.pkl\nimpact_regressor_v2.pkl"]:::ml
    I[("PostgreSQL")]:::store
    J["_recompute_supplier_risk_scores\nExposure index 0 – 100"]:::score

    A --> B --> C --> D --> E --> F --> G --> H --> I --> J
```

### Event Matching Strategy (`src/match_events_to_nodes.py`)

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {
  'primaryColor': '#f0f9ff',
  'primaryBorderColor': '#0ea5e9',
  'primaryTextColor': '#0c4a6e',
  'lineColor': '#94a3b8',
  'edgeLabelBackground': '#ffffff'
}}}%%
flowchart TD
    classDef step    fill:#f0f9ff,stroke:#0ea5e9,color:#0c4a6e
    classDef decide  fill:#fff7ed,stroke:#f97316,color:#7c2d12
    classDef success fill:#ecfdf5,stroke:#10b981,color:#064e3b,font-weight:bold
    classDef fail    fill:#fff1f2,stroke:#f43f5e,color:#881337

    Start(["Article text + extracted_locations"]):::step

    S1{"Strategy 1\nKeyword anchors\nword-boundary regex"}:::decide
    S2{"Strategy 2\nHaversine proximity\n< 500 km to node"}:::decide
    S3{"Strategy 3\nCountry fallback\nextracted_locations first\nthen combined_text"}:::decide

    Done(["matched_node set"]):::success
    NoMatch(["unmatched"]):::fail

    Start --> S1
    S1 -- match found --> Done
    S1 -- no match --> S2
    S2 -- match found --> Done
    S2 -- no match --> S3
    S3 -- match found --> Done
    S3 -- no match --> NoMatch
```

### RSS Ingest Path

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {
  'primaryColor': '#f0f9ff',
  'primaryBorderColor': '#0ea5e9',
  'primaryTextColor': '#0c4a6e',
  'lineColor': '#94a3b8',
  'edgeLabelBackground': '#ffffff'
}}}%%
flowchart TD
    classDef input  fill:#fff7ed,stroke:#f97316,color:#7c2d12
    classDef nlp    fill:#f0f9ff,stroke:#0ea5e9,color:#0c4a6e
    classDef score  fill:#fff1f2,stroke:#f43f5e,color:#881337
    classDef store  fill:#eef2ff,stroke:#6366f1,color:#312e81,font-weight:bold

    F["RSS Feed URL"]:::input
    P["feedparser\nraw article list"]:::nlp
    CL["classifier.pkl  XGBoost tri-class\nLOW / MEDIUM / HIGH\n→ ml_risk_label"]:::nlp
    EN["NER + Event Types\nGeocode + Node Match\nTemporal extraction"]:::nlp
    FB["FinBERT sentiment\n→ sentiment_label\n→ sentiment_score"]:::score
    DI["Disruption + Impact XGB\n→ predicted_disruption_probability\n→ predicted_impact_score"]:::score
    DB[("PostgreSQL\nupsert_events")]:::store
    RS["_recompute_supplier_risk_scores\nExposure index 0 – 100"]:::store

    F --> P --> CL --> EN --> FB --> DI --> DB --> RS
```

---

## ML Stack

| Model | Artifact | Task | Used In |
|-------|----------|------|---------|
| TF-IDF + XGBoost + LabelEncoder | `model_training/classifier.pkl` | Headline tri-class risk | Preprocessing, RSS, JSON ingest |
| FinBERT (`ProsusAI/finbert`) | HuggingFace | Sentiment per article | Batch scoring, RSS enrichment |
| XGBoost Classifier | `model_training/disruption_classifier.pkl` | Binary disruption probability | RSS + batch |
| XGBoost Regressor | `model_training/impact_regressor_v2.pkl` | Impact score (0–300 scale) | RSS + batch |
| Two-Stage XGBoost | `models/forecast_*.json` | 14-day daily risk forecast | Snapshot endpoint |
| Prophet | in-memory | Seasonal baseline for live EDSF | `/forecast` endpoint |

### Supplier Risk Rollup

```
strength_i  = min(100, predicted_impact_score / 3)   # if impact present
            = risk_score                              # otherwise

exposure    = min(100, 0.62 × avg(strength) + 0.38 × max(strength))
```

Computed over the last 30 days; falls back to all-time if no qualifying events exist.

---

## Forecasting Engine

The system maintains two separate forecast paths:

**Path A — Live forecast** (`GET /suppliers/{node}/forecast`)

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {
  'primaryColor': '#f0f9ff',
  'primaryBorderColor': '#0ea5e9',
  'primaryTextColor': '#0c4a6e',
  'lineColor': '#94a3b8',
  'edgeLabelBackground': '#ffffff'
}}}%%
flowchart TD
    classDef data    fill:#fff7ed,stroke:#f97316,color:#7c2d12
    classDef model   fill:#f0f9ff,stroke:#0ea5e9,color:#0c4a6e
    classDef decide  fill:#fff7ed,stroke:#f97316,color:#7c2d12
    classDef boost   fill:#ecfdf5,stroke:#10b981,color:#064e3b
    classDef out     fill:#eef2ff,stroke:#6366f1,color:#312e81,font-weight:bold
    classDef fallbk  fill:#fff1f2,stroke:#f43f5e,color:#881337

    H["Historical risk\nAVG(risk_score) per day\n120-day training window"]:::data
    PB["Prophet Baseline\nweekly seasonality\nchangepoint_prior_scale = 0.25\nlevel-calibrated to 30-day mean"]:::model
    PD{"Prophet\nfit OK?"}:::decide
    NB["Gated News Boost\ndays_until_event ≥ 2\nconfidence = high\nσ = 0.5 · max +50 uplift"]:::boost
    FB["Recursive XGBoost\nFallback"]:::fallbk
    OUT["EDSF Forecast\nyhat · yhat_lower · yhat_upper\nnews_contribution · historical_contribution"]:::out

    H --> PB --> PD
    PD -- yes --> NB --> OUT
    PD -- no  --> FB --> OUT
```

**Path B — Persisted snapshots** (`GET /suppliers/{node}/forecast_snapshot`)

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {
  'primaryColor': '#f0f9ff',
  'primaryBorderColor': '#0ea5e9',
  'primaryTextColor': '#0c4a6e',
  'lineColor': '#94a3b8',
  'edgeLabelBackground': '#ffffff'
}}}%%
flowchart TD
    classDef freeze  fill:#fff7ed,stroke:#f97316,color:#7c2d12
    classDef feat    fill:#f0f9ff,stroke:#0ea5e9,color:#0c4a6e
    classDef s1      fill:#ecfdf5,stroke:#10b981,color:#064e3b,font-weight:bold
    classDef s2      fill:#fff1f2,stroke:#f43f5e,color:#881337,font-weight:bold
    classDef out     fill:#eef2ff,stroke:#6366f1,color:#312e81,font-weight:bold

    FW["Freeze at forecast_date\nAll features from real observed data\nday_offset 1–14 is the only time-varying input"]:::freeze

    FF["31 Freeze-Window Features\nevent_count_3d · event_count_7d · event_count_14d\nevent_freq_7d · avg/max risk last 7d\nsentiment mean / std / delta / lag / neg_ratio\ntype buckets: geopolitical · labor · logistics · weather\nnews_signal · global_event_count_3d\nrisk_trend_7d · event_freq_acceleration"]:::feat

    S1["Stage 1 — XGBClassifier\nforecast_event_prob.json\nP(event occurs on day T)"]:::s1

    S2["Stage 2 — XGBRegressor  q = 0.75\nforecast_severity_q75.json\nE[risk | event occurred]"]:::s2

    OUT["yhat = P(event) × severity\nuncertainty = ± per-node P80 error\nstored in forecast_snapshots table\nmethod: xgboost · xgboost_mean"]:::out

    FW --> FF --> S1 --> S2 --> OUT
```

### Training & Backfill

```bash
# Train all model variants → models/*.json
venv311/bin/python scripts/train_two_stage_forecast.py

# Regenerate all existing xgboost snapshots with new model
venv311/bin/python scripts/backfill_two_stage_snapshots.py

# Backfill q75 variant alongside mean for A/B comparison
venv311/bin/python scripts/backfill_q75_snapshots.py
```

---

## Supplier Nodes

| Node | Country | Criticality | Role |
|------|---------|:-----------:|------|
| TSMC_Hsinchu | Taiwan | 5 | Semiconductor wafer fabrication |
| Foxconn_Zhengzhou | China | 5 | Consumer electronics assembly |
| Port_of_Long_Beach | USA | 4 | Trans-Pacific freight gateway |
| CATL_Ningde | China | 4 | EV battery cells |
| Albemarle_Chile | Chile | 3 | Lithium raw material |
| Tesla_Berlin | Germany | 3 | EV manufacturing |

Criticality (1–5) drives the `impact_score = risk_score × criticality` multiplier on event responses and the exposure rollup weighting. Node coordinates and metadata live in `src/load_to_db.py` and are mirrored in `src/match_events_to_nodes.py` — keep them in sync.

---

## API Reference

Base URL: `http://127.0.0.1:8000`

Most read endpoints accept `?as_of=YYYY-MM-DD` to rewind results to a past UTC date.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/suppliers` | All nodes with criticality, current_risk_score, products |
| GET | `/events/latest` | Recent geocoded events; `impact_score = risk × criticality` |
| GET | `/events/by_node/{node_name}` | Events filtered to a single node |
| GET | `/events/forecasted` | Events with predictive temporal data |
| GET | `/events/forecasted/by_node/{node_name}` | Node-filtered predictive events |
| GET | `/summary` | Aggregate stats for the dashboard |
| GET | `/suppliers/{node_name}/forecast` | 14-day EDSF live forecast |
| GET | `/forecast-snapshots/dates` | Distinct snapshot origin dates |
| GET | `/suppliers/{node_name}/forecast_snapshot` | Persisted 14-day snapshot with MAE |
| POST | `/suppliers/{node_name}/ai-summary` | OpenRouter narrative summary |
| POST | `/admin/rss-ingest/trigger` | Queue one RSS cycle |
| GET | `/admin/rss-ingest/status` | RSS ingestion progress |
| POST | `/admin/forecast-snapshots/run` | Queue daily snapshot generation |

<details>
<summary>Example: forecast snapshot response</summary>

```json
{
  "node_name": "TSMC_Hsinchu",
  "forecast_date": "2026-05-20",
  "points": [
    { "ds": "2026-05-21", "yhat": 18.4, "yhat_lower": 9.2, "yhat_upper": 27.6, "y_actual": 21.0 }
  ],
  "mae": 4.2,
  "completed_days": 1,
  "horizon_days": 14,
  "generated_on_demand": false
}
```
</details>

---

## Dashboard

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {
  'primaryColor': '#f0f9ff',
  'primaryBorderColor': '#0ea5e9',
  'primaryTextColor': '#0c4a6e',
  'lineColor': '#94a3b8',
  'clusterBkg': '#f8fafc',
  'clusterBorder': '#cbd5e1',
  'edgeLabelBackground': '#ffffff'
}}}%%
flowchart LR
    classDef api   fill:#ecfdf5,stroke:#10b981,color:#064e3b,font-weight:bold
    classDef page  fill:#f0f9ff,stroke:#0ea5e9,color:#0c4a6e
    classDef admin fill:#fff1f2,stroke:#f43f5e,color:#881337

    API["FastAPI\nport 8000"]:::api

    subgraph UI["React Dashboard   chain-calm-main/"]
        MAP["World Map\nSonar-pulse risk nodes\narc connections by risk level"]:::page
        SUP["Suppliers Table\nexposure levels · criticality"]:::page
        HIST["Resilience History\nXGBoost snapshot vs actual\nrewindable as_of date"]:::page
        NEWS["News Events\nlive feed with type filters"]:::page
        ADMIN["Admin Panel\nRSS trigger · snapshot run\ningest status"]:::admin
    end

    API -- "TanStack Query" --> MAP
    API -- "TanStack Query" --> SUP
    API -- "TanStack Query" --> HIST
    API -- "TanStack Query" --> NEWS
    API -- "TanStack Query" --> ADMIN
```

```bash
cd chain-calm-main
npm install
npm run dev      # http://localhost:5173
npm run build
npm test
```

---

## Setup

### Prerequisites

- Python 3.11
- PostgreSQL with a `supply_chain_db` database
- Node.js 18+
- macOS: `brew install libomp` (XGBoost OpenMP dependency)

### Backend

```bash
# Virtual environment
python3.11 -m venv venv311
source venv311/bin/activate
pip install -r requirements.txt

# spaCy model (first run)
venv311/bin/python -m spacy download en_core_web_sm

# Configure environment
cp .env.example .env   # edit DB_CONNECTION_STRING etc.

# Verify DB
venv311/bin/python check_db_status.py

# Run batch pipeline (interactive)
python run_predictive_pipeline.py

# Start API
venv311/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000

# Start RSS ingest loop
venv311/bin/python -m src.rss_ingest --interval 600
```

### Ingest web scrape JSONs directly

```bash
venv311/bin/python -m src.json_ingest
venv311/bin/python -m src.json_ingest --dry-run --limit 20
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_CONNECTION_STRING` | `postgresql://postgres:your_password@localhost:5432/supply_chain_db` | Active PostgreSQL connection |
| `DB_CONNECTION_STRING_LEGACY` | _(unset)_ | Optional legacy DB for comparison |
| `USE_FINBERT_RISK` | `1` | `0` → use VADER instead of FinBERT |
| `FINBERT_MODEL` | `ProsusAI/finbert` | HuggingFace model id |
| `FINBERT_DEVICE` | auto | `cpu`, `cuda`, or `mps` |
| `SPACY_DEVICE` | auto | `gpu` (default preferred/activated) or `cpu` |
| `SPACY_BATCH_SIZE` | `256` | Batch size for `nlp.pipe()` |
| `RSS_FEEDS_PATH` | `config/rss_feeds.json` | JSON array of `{url, source}` entries |
| `ML_CLASSIFIER_PATH` | `model_training/classifier.pkl` | Tri-class headline risk model |
| `DISRUPTION_CLASSIFIER_PATH` | `model_training/disruption_classifier.pkl` | Binary disruption XGBoost |
| `IMPACT_REGRESSOR_PATH` | `model_training/impact_regressor_v2.pkl` | Impact score XGBoost |
| `OPENROUTER_API_KEY` | _(required for AI summary)_ | OpenRouter key |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Chat model for narratives |
| `VITE_API_BASE_URL` | same host, port 8000 | Frontend API base URL |

---

## Repository Layout

```
SupplyChainForecast/
├── src/                            # Backend modules
│   ├── main.py                     # FastAPI app (v1.2.0)
│   ├── rss_ingest.py               # RSS background worker
│   ├── preprocessing.py            # NLP labels + NER
│   ├── risk_scoring.py             # FinBERT / VADER scoring
│   ├── geocoding.py                # Location → lat/lon
│   ├── match_events_to_nodes.py    # 3-strategy node matching
│   ├── temporal_extraction.py      # Future event date prediction
│   ├── forecast_snapshots.py       # Two-stage XGBoost snapshots
│   ├── predictive_forecasting.py   # EDSF live forecast
│   ├── load_to_db.py               # PostgreSQL upserts + rollups
│   ├── db_config.py
│   ├── sentiment_finbert.py
│   ├── json_ingest.py
│   └── openrouter_client.py
│
├── model_training/                 # Training scripts + .pkl artifacts
│   ├── train_classifier.py
│   ├── train_two_stage_impact_models.py
│   ├── classifier.pkl
│   ├── disruption_classifier.pkl
│   └── impact_regressor_v2.pkl
│
├── models/                         # XGBoost forecast model artifacts
│   ├── forecast_event_prob.json    # Stage 1: P(event) classifier
│   ├── forecast_severity_q75.json  # Stage 2: q75 regressor (default)
│   ├── forecast_severity.json      # Stage 2: mean regressor
│   └── forecast_intervals*.json    # Per-node P80 error bounds
│
├── scripts/
│   ├── train_two_stage_forecast.py
│   ├── backfill_two_stage_snapshots.py
│   └── backfill_q75_snapshots.py
│
├── chain-calm-main/                # Vite + React dashboard
│   └── src/
│       ├── pages/                  # WorldMap · Suppliers · History · News · Admin
│       └── lib/                    # api.ts · dataMappers.ts · config.ts
│
├── config/
│   ├── rss_feeds.json              # Local RSS feed list (gitignored)
│   └── rss_feeds.example.json
│
├── data/
│   ├── raw/web_scrape/             # Input article JSONs
│   └── processed/                  # Pipeline JSONL intermediates
│
├── docs/                           # Architecture notes
├── run_predictive_pipeline.py      # Interactive batch orchestration
├── check_db_status.py              # DB health check
└── requirements.txt
```

### Model Training Reference

| Script | Output | Notes |
|--------|--------|-------|
| `model_training/train_classifier.py` | `classifier.pkl` | TF-IDF + XGBoost + LabelEncoder (3-tuple) |
| `model_training/train_two_stage_impact_models.py` | `disruption_classifier.pkl`, `impact_regressor_v2.pkl` | `--label-mode rules` → `*_rules.pkl` |
| `scripts/train_two_stage_forecast.py` | `models/forecast_*.json` | Two-stage freeze-window snapshot model |
| `scripts/train_forecast_model.py` | `models/forecast_xgboost.json` | Legacy recursive XGBoost (EDSF fallback) |
| `model_training/retrain_with_feedback.py` | `classifier.pkl` | Incorporate labelled feedback |
