# Webhose Dataset Ingestion — Design Spec
**Date:** 2026-05-23

## Goal

Ingest the [Webhose political-news-dataset](https://github.com/Webhose/political-news-dataset) and [Webhose financial-news-dataset](https://github.com/Webhose/financial-news-dataset) to:
1. Populate the DB with more historical news events for risk calculation
2. Improve ML model training (disruption classifier, impact regressor, forecast models)

Scope: 2025-01-01 onwards, English articles only.

---

## Architecture

### Single script: `scripts/prepare_webhose_data.py`

Five phases run sequentially. Output lands in `data/raw/combined/`. Existing pipeline (`json_ingest.py`) is minimally changed (one `--directory` flag).

```
git clone webhose/political-news-dataset  → data/raw/webhose_political/
git clone webhose/financial-news-dataset  → data/raw/webhose_financial/

scripts/prepare_webhose_data.py
  Phase 1: Download & Extract   zip files → article dicts in memory
  Phase 2: Normalize            Webhose schema → {label, text} + metadata
  Phase 3: Merge & Dedup        Webhose wins on URL conflict vs web_scrape
  Phase 4: Group & Write        → data/raw/combined/all_news_{year}_q{N}.json
  Phase 5: Sidecar              → data/raw/combined/webhose_metadata.jsonl

src/json_ingest.py --directory data/raw/combined/
  (unchanged pipeline: scoring → geocoding → node match → DB → snapshots)
```

---

## Phase Details

### Phase 1 — Download & Extract

- User clones both repos locally before running the script
- Script accepts `--political-repo <path>` and `--financial-repo <path>` (default: `data/raw/webhose_political` and `data/raw/webhose_financial`)
- Walk each repo's `Datasets/` folder, iterate all `.zip` files
- Parse date from filename: `Politics_negative_20250112...` → `2025-01-12`
- **Skip** any zip dated before `2025-01-01`
- Extract article JSONs from each zip in-memory using `zipfile` (no temp files)

### Phase 2 — Normalize

Each Webhose article JSON → two outputs:

**Standard pipeline entry** (extended `{label, text, webhose_meta}` format):
```json
{
  "label": "{thread.site};{title};{url};{published}",
  "text": "<article text field>",
  "webhose_meta": {
    "locations": ["Taiwan", "Hsinchu"],
    "categories": ["Politics", "Economy, Business and Finance"]
  }
}
```
- `published` parsed and re-emitted as ISO 8601 UTC
- Skip if `language != "english"`
- Skip if `published < 2025-01-01`
- `webhose_meta` is an optional key — `json_ingest.py` uses it when present, ignores it otherwise (backward compatible with existing web_scrape files)

**Metadata dict** (held in memory, written in Phase 5):
```json
{
  "url": "...",
  "sentiment": "negative",
  "categories": ["Politics", "Economy, Business and Finance"],
  "topics": ["Politics->political parties", "Economy->financial and economic news"],
  "entities_locations": [{"name": "Taiwan", "sentiment": "none"}],
  "entities_organizations": [{"name": "TSMC", "sentiment": "negative"}],
  "domain_rank": 3187,
  "source_country": "US",
  "dataset_source": "webhose_political"
}
```

**Live pipeline enrichment from Webhose fields:**

| Webhose field | Pipeline field | Logic |
|---|---|---|
| `sentiment` | sidecar only | **Not** injected into the pipeline. FinBERT runs normally on all Webhose articles — consistent scoring across all sources. Webhose sentiment stored in sidecar for training use only. |
| `entities.locations[]` | Pre-seeded locations for geocoding | Passed as `extracted_locations` hint into the geocoding step |
| `categories[]` + `topics[]` | `potential_event_types` | Mapped via lookup table (see Mapping table below) |

**Category → Event type mapping:**

| Webhose category / topic | `potential_event_types` value |
|---|---|
| `Economy, Business and Finance` | `Demand_Supply_Shift` |
| `Politics` / `Politics->government` | `Political_Regulatory` |
| `Politics->political parties` | `Political_Regulatory` |
| `Disasters and Accidents` | `Natural_Disaster` |
| `Labor` / `Labor Issues` | `Labor_Issue` |
| `Technology` / `Cyber` | `Cyber_Attack` |
| `Transport` / `Logistics` | `Logistics_Issue` |
| `Industry` / `Manufacturing` | `Industrial_Accident` |

Multiple categories map to multiple event types. Unknown categories are ignored (pipeline's own `detect_potential_events` still runs over full text).

### Phase 3 — Merge & Deduplicate

1. Load all articles from `data/raw/web_scrape/*.json` into a `url → entry` dict
2. Load all normalized Webhose articles into a second `url → entry` dict
3. Merge: iterate web_scrape dict; if URL also in Webhose dict, **Webhose entry wins**
4. Add any Webhose URLs not present in web_scrape
5. Result: single flat list, deduplicated by URL, Webhose preferred

### Phase 4 — Group by Quarter & Write

Parse `published` from each entry's `label` field:
- Group into `(year, quarter)` buckets
- Quarter: Q1=Jan–Mar, Q2=Apr–Jun, Q3=Jul–Sep, Q4=Oct–Dec
- Output: `data/raw/combined/all_news_{year}_q{N}.json`
- Format: standard `[{label, text}, ...]` array — identical to existing web_scrape files
- Existing quarters (e.g. `all_news_q3_2025.json`) are **replaced** by the merged version

### Phase 5 — Metadata Sidecar

- Write `data/raw/combined/webhose_metadata.jsonl`
- One JSON line per Webhose article, keyed by URL
- Fields: `url`, `sentiment`, `categories`, `topics`, `entities_locations`, `entities_organizations`, `domain_rank`, `source_country`, `dataset_source`
- Does **not** go through the pipeline — used by training scripts to join on URL for extra features

---

## Changes to `json_ingest.py`

Add `--directory` flag:
```
python -m src.json_ingest --directory data/raw/combined/
```
Default stays `data/raw/web_scrape/` so existing usage is unchanged.

---

## Usage

```bash
# 1. Clone repos
git clone https://github.com/Webhose/political-news-dataset data/raw/webhose_political
git clone https://github.com/Webhose/financial-news-dataset data/raw/webhose_financial

# 2. Prepare combined dataset
venv311/bin/python scripts/prepare_webhose_data.py \
  --political-repo data/raw/webhose_political \
  --financial-repo data/raw/webhose_financial

# 3. Ingest into DB
venv311/bin/python -m src.json_ingest --directory data/raw/combined/
```

---

## Output Files

| File | Contents |
|---|---|
| `data/raw/combined/all_news_{year}_q{N}.json` | Merged quarterly articles, pipeline-ready `[{label, text}]` |
| `data/raw/combined/webhose_metadata.jsonl` | Per-article metadata sidecar for training enrichment |

---

## What's NOT in scope

- Automatically cloning the repos (user does this manually)
- Retraining models (separate step after ingestion)
- Changing DB schema (all extra fields go via sidecar only)
- Modifying RSS ingest or batch pipeline scripts
