<div align="center">

# Supply Chain Disruption Early-Warning Monitor

Continuously reads global news and predicts the probability of a supply-chain disruption
in the next 1–3 days across five sectors, with every prediction rewindable to any past date.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)

**[View the live demo →](https://fyp.meordnsh.dev)**

</div>

![Global situation map](.github/assets/screenshot-map.png)

---

## Overview

Supply-chain disruptions such as port closures, chip shortages and shipping-lane blockages
usually show up in the news days before they show up in operational data. This system reads
that news continuously and turns it into a calibrated probability of disruption per sector.

Everything in the live path runs on small, self-hosted models. **No LLM is called anywhere in
the ingestion or prediction pipeline**, which keeps a full cycle at roughly 30–60 seconds and
the running cost at the price of one small VM.

The dashboard's defining feature is the **date rewind**: scroll back to any past date and every
number is recomputed from only the data that existed then. Nothing is back-filled with hindsight,
so you can audit exactly what the model knew before each call it made.

## Features

- **Live ingestion** — 15 curated RSS sources, polled automatically every 30 minutes
- **Sentiment scoring** — FinBERT, finance-tuned, signed −1 to +1
- **Relevance filtering** — MiniLM embedding classifier separates genuine risk events from noise
- **Sector routing** — cosine similarity against 12 MiniLM theme prototypes
- **Calibrated forecasting** — XGBoost + isotonic calibration → P(disruption in 1–3 days)
- **Date rewind** — replay any past date with no hindsight leakage
- **Geocoding** — offline spaCy NER + gazetteer, with per-match confidence scoring
- **Status alerts** — in-app notifications when a sector changes state
- **Transparent accuracy** — every metric below is published live in the app, including a null result

![Sectors dashboard](.github/assets/screenshot-sectors.png)

## How It Works

```
RSS feeds (15 sources)
        │
        ▼
  parse + dedup by article URL
        │
        ▼
  FinBERT sentiment  ──────────────►  events table
        │
        ▼
  MiniLM relevance classifier (P ≥ 0.59)
        │
        ▼
  theme routing (cosine vs. 12 prototypes)
        │
        ▼
  disruption_candidates table
        │
        ▼
  16 rolling-window features per (sector, date)
        │
        ▼
  XGBoost + isotonic calibration
        │
        ▼
  P(disruption in next 1–3 days)  ──►  dashboard
```

**Sectors monitored:** shipping & chokepoints · semiconductors & electronics · European auto ·
critical materials · US logistics & freight

**Status thresholds:** `P ≥ 0.25` → active · `P ≥ 0.10` → watch · otherwise calm

Predictions are averaged over a 3-day trailing window before display. The calibrator is fit on
only a few hundred confirmed events, so raw single-day output is close to discrete. That
smoothing is load-bearing, not cosmetic.

## Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.11, FastAPI, Uvicorn, SQLAlchemy |
| **Database** | PostgreSQL 17 |
| **NLP** | FinBERT (sentiment), MiniLM / sentence-transformers (embeddings), spaCy (NER) |
| **ML** | PyTorch, XGBoost, scikit-learn (isotonic calibration), BERTopic (offline discovery) |
| **Frontend** | React 18, TypeScript, Vite, react-simple-maps |
| **Infrastructure** | Google Compute Engine, nginx, systemd, Let's Encrypt |

## Getting Started

### Prerequisites

- Python 3.11
- Node.js 20+
- PostgreSQL 15+

### Installation

```bash
git clone https://github.com/Dxnxsh/SupplyChainForecast.git
cd SupplyChainForecast

# Backend
python3.11 -m venv venv311
venv311/bin/pip install fastapi uvicorn python-dotenv SQLAlchemy psycopg2-binary \
  feedparser numpy pandas xgboost scikit-learn spacy sentence-transformers \
  transformers torch geonamescache google-genai
venv311/bin/python -m spacy download en_core_web_sm

# Frontend
cd web && npm install
```

> **Note:** `google-genai` is required even though no LLM runs in the live path. It sits in the
> import chain via `src/gemini_client.py`, and the API will not start without it.

### Configuration

Create a `.env` file in the project root:

```bash
DB_CONNECTION_STRING=postgresql://user:password@localhost:5432/supply_chain_db
FINBERT_MODEL=ProsusAI/finbert
USE_FINBERT_RISK=1
TORCH_DEVICE=cpu               # or mps / cuda
RSS_FEEDS_PATH=config/rss_feeds.json
TOKENIZERS_PARALLELISM=false   # avoids deadlocks inside the asyncio event loop
```

Optional scheduler tuning:

| Variable | Default | Description |
|---|---|---|
| `INGEST_INTERVAL_SECONDS` | `1800` | Seconds between automatic ingest cycles |
| `INGEST_CYCLE_TIMEOUT_S` | `600` | Kills a hung cycle so it can't wedge the scheduler |
| `INGEST_NO_GEOCODE` | `false` | Set `true` to skip geocoding for faster dry runs |
| `DISABLE_BACKGROUND_INGEST` | `false` | Set `true` to disable auto-ingestion (e.g. in tests) |

### Running

```bash
# API — also owns the background ingestion schedule
venv311/bin/uvicorn src.api:app --reload --port 8000

# Frontend (separate terminal)
cd web && npm run dev
```

Starting the API is enough to keep data fresh. No separate cron job or worker process is needed.

### Common Tasks

```bash
venv311/bin/python -m scripts.ingest_live              # one ingest cycle
venv311/bin/python -m scripts.ingest_live --skip-db    # dry run, no writes
venv311/bin/python -m scripts.build_ui_snapshot        # rebuild the static snapshot
venv311/bin/python -m scripts.train_predictor          # retrain the predictor
venv311/bin/python -m scripts.test_predictor           # leakage + walk-forward tests
venv311/bin/python -m scripts.build_topic_model        # offline topic discovery
```

## Project Structure

```
├── src/
│   ├── api.py               # FastAPI app + background ingestion scheduler
│   ├── db_config.py         # database URL resolution
│   ├── sentiment_finbert.py # FinBERT sentiment scoring
│   ├── preprocessing.py     # spaCy NER location extraction
│   └── geocoding.py         # offline gazetteer + confidence scoring
├── scripts/
│   ├── ingest_live.py       # the live RSS → DB pipeline
│   ├── live_label.py        # relevance classifier + theme routing
│   ├── train_predictor.py   # feature engineering + model training
│   ├── build_ui_snapshot.py # model output → dashboard JSON
│   ├── test_predictor.py    # leakage + walk-forward validation
│   └── build_topic_model.py # BERTopic discovery (offline only)
├── web/                     # React + TypeScript dashboard
├── config/rss_feeds.json    # the 15 monitored sources
├── data/                    # tracked metrics + runtime state
└── model_training/          # model binaries (gitignored)
```

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/snapshot` | Current snapshot for the latest available date |
| `GET` | `/api/snapshot?as_of=YYYY-MM-DD` | Rewind, recomputing features and predictions for that date |
| `GET` | `/api/alerts?limit=50` | Recent sector status-change alerts |
| `GET` | `/api/health` | Health check plus live ingestion scheduler state |
| `POST` | `/api/ingest` | Trigger an ingest cycle immediately |

## Model Performance

**Relevance classifier.** MiniLM embeddings + logistic regression at threshold 0.59, evaluated
against 150 hand-labelled articles:

| Model | Precision | Recall | F1 |
|---|---|---|---|
| **MiniLM + logistic regression** | 0.62 | **0.89** | **0.73** |
| TF-IDF + XGBoost baseline | 0.77 | 0.59 | 0.67 |

Recall is deliberately favoured over precision. For an early-warning system, a missed disruption
costs far more than a false alarm a human can dismiss in seconds.

**Disruption predictor.** 720 test rows, 153 positives (21.3% base rate), split at 2026-02-01:

| Metric | Predictor | Persistence baseline |
|---|---|---|
| Brier score (lower is better) | **0.1765** | 0.1903 |
| ROC-AUC (single split) | 0.615 | — |
| Walk-forward mean AUC (10 folds) | **0.733** | — |
| Recall on *new onset* events | **0.712** | 0.000 |

The onset row is the one that matters. A persistence baseline, meaning "assume tomorrow looks
like today", scores well on aggregate metrics by riding out ongoing disruptions, but by
definition catches **zero** new ones. The model catches 71% of genuine onsets, which is the
entire point of an early-warning system.

**External validation.** The model's shipping probability was correlated against Brent crude
oil volatility (FRED `DCOILBRENTEU`, 393 observations, lags from −14 to +14 days). The strongest
correlation found was −0.083, which is indistinguishable from noise. This is published in the
app as a **null result**: news-derived shipping risk and oil-price volatility are not measurably
related in this sample. Reporting it is more useful than quietly dropping it.

## Deployment

The live instance runs on a single Google Compute Engine VM (e2-standard-2, 2 vCPU / 8 GB):

- **nginx** serves the built frontend and reverse-proxies `/api/` to Uvicorn on `127.0.0.1:8000`
- **systemd** (`scf-api.service`) keeps the API running, restarts on failure, starts on boot
- **PostgreSQL** runs locally on the same instance
- **Let's Encrypt** provides TLS, auto-renewed via `certbot.timer`

The frontend bakes its API base URL in at build time, so set it explicitly when building:

```bash
cd web && VITE_API_URL=https://your-domain.com npm run build
```

## About

Built as a final-year project. The full architecture reference, including model retraining
cadence, geocoding confidence thresholds and known constraints, lives in
[`CLAUDE.md`](CLAUDE.md).
