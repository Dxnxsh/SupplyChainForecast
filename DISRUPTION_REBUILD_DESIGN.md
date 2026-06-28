# Disruption Early-Warning — Rebuild Design (evidence-based, final)

> Architecture + ML design source of truth for the redesigned supply-chain disruption
> prediction system. Companion to `DESIGN.md` (frontend visual system).
> Status: **locked after a data-feasibility investigation.** Supersedes the legacy 14-day
> forecaster AND the earlier facility-level draft of this doc — both were disproven by the data.

---

## 1. The reframe (what the evidence forced)

The predecessor forecast a continuous risk scalar 14 days ahead per facility and produced a
smooth line that missed every spike. Investigation showed the failure was deeper than the model:
**the data has no usable per-facility disruption signal.** The final, evidence-based shape:

- **Predict near-term disruption probability at the THEME / COMMODITY level** (e.g. "Taiwan
  semiconductors", "European auto supply chain", "lithium"), NOT per named facility.
- **LLM as a one-time annotation oracle (distant supervision), not a runtime dependency.**
  The LLM labels the corpus once (offline). The *running system* uses the project's own NLP
  models: a trained **relevance classifier** + an **open-vocabulary topic model** for themes +
  the **temporal predictor**. No LLM in the live loop.
- **Open-vocabulary themes via clustering (no fixed list, no live LLM):** themes are *discovered*
  (BERTopic / LDA) from the relevance-filtered events and grow as new events appear — handling
  new-theme drift without a predefined taxonomy.
- Stay **news-based** (the FYP premise): news is the input/NLP core; structured DBs (USGS) are
  optional label validation only.

This makes it a genuine NLP project — three trained/derived models (relevance classification,
topic modeling, calibrated prediction) — with the LLM used only to bootstrap labels.

Success = calibration, precision@lead-time, beating a naive baseline — measured against
LLM-confirmed (and human-gold-validated) real events.

---

## 2. What the investigation established (evidence)

| Finding | Evidence |
|---|---|
| Data is ~18 months, ~180k articles | 2025=126k, 2026=55k; pre-2025 stray |
| Corpus is a **general/financial news firehose** | curated supply-chain feeds = **1.2%**; bulk from web-scrape + Perigon backfill |
| Old matcher is geography-only noise | 800km proximity + country fallback → sports ad tagged as `Industrial_Accident` at a port |
| Facility-level disruption rate ≈ 0 | ~100 sampled articles (every source/target), ~0 facility disruptions |
| Random sampling was the wrong instrument | disruptions are ~1% of corpus; 0/24 is expected at that base rate, not "absence" |
| Targeted retrieval + LLM **works** | keyword candidates → LLM surfaced real events: JLR cyberattack shutdown, VW chip-shortage production halts |
| Yield is modest but real | ~15–25% precision on candidates → ~a few hundred clean theme-level events extractable from 180k |
| LLM filter precision is excellent | rejected ~100% of geography noise with correct justifications |
| Structured DBs are signal-rich | USGS gave 1,128 dated/geocoded quakes near nodes (e.g. M7.4 Hualien near TSMC) |

Conclusion: **news is viable at theme level via the cascade**; facility-level is not.

---

## 3. Data flow — offline labeling vs live (LLM-free) pipeline

**Offline, one-time (LLM as annotator):**
```
events corpus (180k)
   │ keyword pre-filter → candidates (middle pool ~9.2k)
   ▼ TWO-STAGE LLM labeling — lenient (recall) → strict (precision)
   │   DONE: disruption_candidates; final clean set = 557 events; ~1,000+ hard negatives
   └─→ labeled dataset (positives + negatives) + human GOLD SET (80% precision / 95% recall)
```

**Live system (no LLM — the project's own models):**
```
incoming news (RSS / Perigon / dump)
   │
   ▼ RELEVANCE CLASSIFIER  (trained on LLM labels; TF-IDF or embeddings → LogReg/XGB)
   │   keeps disruptions, drops noise — replaces the live LLM
   ▼ TOPIC MODEL  (BERTopic / LDA) → open-vocab theme assignment + emergent-theme discovery
   ▼ EVENT layer (clean, theme-tagged)        RAW layer kept for negatives + features
   │                                                │
   └────────────────┬───────────────────────────────┘
                    ▼ daily (theme, day) features
        TEMPORAL PREDICTOR → P(disruption 1–3d)  →  alert + in-UI metrics
```

Why keep the whole stream: the predictor needs **negative** (no-disruption) days and
**volume/sentiment features**; positives-only training fails. The relevance classifier also
needs **easy negatives** (random non-disruption news), not only keyword-candidate hard negatives.

---

## 4. Prediction targets — MEASURED (middle pool, two-stage labeled + cleaned)

Built via the lenient→strict cascade over the middle candidate pool (~9.2k candidates).
Two-stage labeling: lenient `gemini-3.1-flash-lite` (high recall) → strict `gemini-3.5-flash`
(high precision). Final **clean** set (stored in `disruption_candidates` where
`is_risk_event AND strict_is_risk`): **557 events, 122 unique event-days**; lenient pass
yielded 1,639, strict kept 34%. Validated against a 150-row human gold set drawn from the
full clean set: **precision 80%, recall 95%** (F1 87%). So ~446 of the 557 are genuinely real.
High recall means the pipeline rarely misses a disruption; 80% precision is solid for
weak-supervision labels, and the human gold set serves as the trusted evaluation set.

The unit that matters for a daily model is **event-days**:

| Consolidated target | Clean events | Event-days | Modelable |
|---|---|---|---|
| Shipping chokepoints (Hormuz + Red Sea) | 459 | 79 | strong (flagship) |
| Semiconductor & electronics (semi+China+Japan+Korea+Taiwan) | 44 | 32 | usable |
| European auto supply chain | 34 | 22 | usable |
| Critical materials & export controls (lithium + rare earths) | 22 | 18 | marginal |
| US logistics (W. Coast ports + freight) | 10 | 9 | thin |
| **Pooled (any target)** | **557** | **122** | **solid (~22% base rate)** |

**Recommended target: a pooled "P(any disruption in next 1–3 days)" classifier (122 positive
days), with theme as a secondary/multi-label output; shipping also gets a dedicated model.**
Honest caveat: **82% of events are shipping** (the 2025–26 Gulf shipping crisis dominates the
corpus). A large 2026-03 spike must not leak across the train/test split.

---

## 5. Locked decisions

1. **LLM = one-time annotator only.** Used offline to label the corpus (done). NOT in the live
   system. This keeps it a genuine NLP project (own trained models) and removes runtime LLM
   cost/dependency.
2. **Relevance classifier (own model)** — trained on the LLM labels (positives + hard negatives
   + added easy negatives) to filter disruptions live. TF-IDF or sentence-transformer embeddings
   → LogReg/XGBoost. Validated against the human gold set. Keyword pre-filter = cheap baseline.
3. **Open-vocabulary themes via topic model** — BERTopic / LDA over relevance-filtered events.
   No fixed theme list; clusters emerge and grow (handles new-theme drift). Periodic re-cluster
   to surface emergent themes.
4. **Target** — `P(disruption in next 1–3 days)`, calibrated (isotonic/Platt). Classification,
   not magnitude regression. No severity head. Pooled primary model (122 event-days) with
   theme as a secondary output; theme used as prediction *scope*, optionally excluded as an
   input feature so the guess comes from news signals (see §11).
   **Target set = the 5 consolidated targets in §4 (measured, modelable). The topic model
   (decision 3) is the drift-discovery layer, NOT the initial target set** — it surfaces
   emergent themes for periodic review; the predictor trains on the 5 fixed targets first.
5. **Predictor model** — pooled gradient-boosted classifier (XGBoost/LightGBM); news
   volume/sentiment/recent-event features + SHAP.
6. **Stretch (one)** — scheduled-event lead-time extraction (reuses `temporal_info`).

---

## 6. Evaluation (honest, viva-proof)

- **Temporal split** + **walk-forward** backtest (train on past, test on later window).
- **Leakage controls:** features use only `data_date <= obs_date`; calibration on a disjoint
  slice; replay model train-cutoff < replay date.
- **LLM labeler eval:** precision AND recall vs a **human-verified gold set** (kills circularity).
- **Predictor metrics:** Brier vs naive persistence baseline, reliability/calibration curve,
  precision@lead-time. Per-theme positive-count report before training.

---

## 7. In-UI metrics surface

Computed only over a held-out window from a **locked walk-forward backtest** (read-only, never a
live recompute over training data): calibration curve, Brier-vs-baseline, precision@lead-time,
backtest-replay scrubber (leakage-free), SHAP why-panel, prospective tracker.

---

## 8. Honest constraints (state in the report)

- **Modest dataset** (~hundreds of clean events) → favors the boosted classifier over data-hungry
  models; set expectations accordingly.
- **Perigon reaches only ~3 months back** → the dump is the only >3mo history; collect forward
  from curated feeds to grow the set over the project.
- **Source skew** (financial/geopolitical) over-represents some disruption types.
- **Sudden exogenous events** (quakes, fires) have no textual precursor → the system targets
  near-term probability + detection, not foresight.
- **Labels are LLM-derived weak supervision** → defensible only because the human gold set
  quantifies labeler quality.

---

## 9. Phased plan + tasks

- **Phase 0 — Pilot (DONE):** feasibility established; cascade validated; theme grain confirmed.
- **Phase 1 — Two-stage labeling via LLM (DONE):**
  - T1 Keyword candidate retrieval (middle pool ~9.2k) — DONE (`CANDIDATE_RE`).
  - T2 Lenient pass `gemini-3.1-flash-lite` → 1,639 events — DONE (concurrent, resumable, circuit-breaker).
  - T2b Strict pass `gemini-3.5-flash` (precision filter) → 557 clean events — DONE
    (`scripts/reverify_positives.py`, `strict_is_risk` column).
  - T3 Human gold set — DONE. Full clean-set gold (`data/gold_set_full.csv`, n=150):
    **precision 80%, recall 95%, F1 87%**. This is the trusted evaluation set for the relevance
    classifier.
- **Phase 2 — Own NLP models (TODO):**
  - T4 Pull **easy negatives** (random non-disruption news from the 180k) to round out the
    relevance training set.
  - T5 **Relevance classifier** — train on LLM labels (pos + hard negs + easy negs); eval vs gold
    set; compare to keyword baseline. Replaces the live LLM.
  - T6 **Topic model** (BERTopic / LDA) over relevance-filtered events → open-vocab themes +
    emergent-theme discovery; map to the consolidated targets.
- **Phase 3 — Predictor + eval + UI (handoff target):**
  - T7 (target, day) feature build from RAW stream + pooled calibrated predictor (no severity head).
  - T8 Walk-forward eval + leakage tests + baseline (guard the 2026-03 spike in the split).
  - T9 In-UI metrics surface.
  - T10 Live ingestion (RSS + Perigon recent window) → relevance classifier → topic model (no LLM).
- **Phase 4 — Stretch:** T11 scheduled-event lead-time extraction.

### Build artifacts already in the repo (handoff state)
- `src/gemini_client.py` — Agent Platform / Gemini client (express api_key OR ADC; JSON mode).
- `scripts/build_disruption_dataset.py` — the resumable, concurrent cascade (pre-filter → LLM
  → `disruption_candidates`). `--limit`, `--workers`, `--report`. Resumable by title.
- `scripts/reverify_positives.py` — strict precision pass (`gemini-3.5-flash`, hard-exclude
  prompt) → `strict_is_risk` column. `--workers`, `--score-gold`. Resumable + circuit-breaker.
- `scripts/build_gold_set.py` — gold-set export/score (LLM-labeler precision/recall).
- `disruption_candidates` table — the dataset. **Final clean set = `is_risk_event AND
  strict_is_risk`** (557 events). Columns: `is_risk_event`, `strict_is_risk`, `themes` (JSONB),
  `risk_type`, `confidence`, `reason`, `article_date`, `model`, `strict_model`. Strict-dropped
  and lenient-rejected rows are hard negatives.
- `src/gemini_client.py` — Agent Platform client (express api_key OR ADC; JSON mode; patient
  429 backoff). Models: lenient `gemini-3.1-flash-lite`, strict `gemini-3.5-flash`.
- `src/openmodel_client.py` — earlier OpenModel client (superseded by Gemini; kept for reference).
- Env: `GEMINI_API_KEY` (Agent Platform express) in `.env`. Run at ~8 workers (per-minute RPM limit).

---

## 10. Reused vs retired

**Reuse:** Postgres, FastAPI, React/shadcn UI, `rss_feeds.json`, `perigon_ingest.py`,
`openrouter_client.py` (LLM calls), event-type taxonomy, FinBERT, `temporal_info` extraction,
Stage-1 classifier code.

**Retire:** `predictive_forecasting.py` (EDSF/Prophet), freeze-window snapshots, Stage-2 severity
regression, the 800km/country matcher, facility-level prediction, and the raw web-scrape dump as
*direct* training input (it becomes the RAW layer feeding the cascade, not labels).

---

## 11. Themes: scope vs feature (design note)

A theme is the prediction **target/scope** — it defines *what* the model predicts about
("disruption risk for shipping chokepoints"), not a hint the model leans on. The model still
makes its own guess (the probability) from **news signals**.

- As **target/scope:** required. Without a defined unit there is no supervised question
  ("predict any disruption anywhere" is degenerate — almost always true).
- As an **input feature:** optional. To avoid over-reliance on theme identity, you may exclude
  theme as a feature so the prediction comes purely from news signals; theme then only labels
  *which* series the prediction belongs to.

Open-vocab (topic model) means the themes are **discovered**, not predefined — but they still
exist as the prediction unit. New themes are *captured* immediately (new cluster) but only
*predicted* once they accumulate history and the predictor is retrained. Retraining is
**periodic** (monthly/quarterly), not continuous; walk-forward eval already simulates it.

---

## 12. Build spec (concrete — for a cold agent executing Phase 2/3)

### 12.1 Targets and labels
- **Targets:** the 5 consolidated targets (§4). Map each via its sub-themes (the JSONB `themes`
  array) using `themes ?| ARRAY[...]` (see `reverify_positives.py` / report queries for the maps).
- **Positive label:** for (target, obs_date), positive if a clean event
  (`is_risk_event AND strict_is_risk`) whose `themes` belong to that target has
  `article_date ∈ [obs_date+1, obs_date+3]` (the 1–3 day horizon).
- **Negative label:** (target, obs_date) with no such event in the horizon.
- **Grid:** for each target, one row per day over **2025-01-01 … 2026-06-27** (~547 days).
- **"Disruption-day" definition** must match the gold-set bar the human used (oil-price/strait
  events counted as disruptions). Keep consistent.

### 12.2 Features (all computed with strict `data_date <= obs_date` — no leakage)
From the RAW news stream (all `events` matching the target's keywords) + the clean events:
- **Volume:** article count in last 1d / 3d / 7d / 14d.
- **Event recency:** days since last clean disruption (target); clean-event count last 3d / 7d / 14d.
- **Sentiment:** mean + min FinBERT `sentiment_score` last 3d / 7d; sentiment delta (last3 − prior).
- **Disruption-keyword density:** `CANDIDATE_RE` hits in target articles last 1d / 3d.
- **Calendar:** `day_of_week`, `is_weekend`.
- **Cross-target:** global clean-event count last 3d.
- **(Optional) embeddings:** mean sentence-transformer vector of target articles last 3d (ablation).
- **Theme identity:** optional input feature — see §11; default OFF for the pooled model.

### 12.3 Relevance classifier (T5)
- **Train set:** positives = clean events (`strict_is_risk=true`); hard negatives = strict-dropped
  + lenient-rejected rows; **easy negatives** = ~2–3k random `events` NOT matching `CANDIDATE_RE`.
- **Model:** TF-IDF (or sentence-transformer embeddings) → LogReg / XGBoost.
- **Eval:** against `data/gold_set_full.csv` (the trusted human set). Compare to the keyword
  pre-filter baseline. **Acceptance:** beat the keyword baseline on F1; report precision/recall.

### 12.4 Predictor (T7) + split + eval
- **Model:** gradient-boosted classifier (XGBoost/LightGBM), pooled over targets, calibrated
  (isotonic on a disjoint slice). Output `P(disruption in next 1–3 days)`.
- **Temporal split:** train `obs_date ≤ 2026-01-31`, test `obs_date ≥ 2026-02-01` — this puts
  the **2026-03 spike entirely in test** (no leakage). Also run **walk-forward** (rolling origin).
- **Baseline:** persistence ("disruption in last 3d → predict disruption"). Predictor must beat it.
- **Metrics:** Brier, reliability curve, precision@lead-time, per-target positive counts.
- **Leakage tests (must pass):** assert every feature's max source date ≤ obs_date; calibration
  slice disjoint from test; any backtest-replay model trained only on data before its origin.

### 12.5 Acceptance criteria (per task)
- T4 easy negatives: ~2–3k rows, verified non-candidate. T5: relevance F1 > keyword baseline,
  reported vs gold. T6 topic model: ≥3 coherent clusters mapping to the consolidated targets.
  T7: predictor Brier < persistence baseline on the held-out test. T8: leakage tests green.

---

## 13. Lessons / do-NOT-do (hard-won — don't re-suffer these)

- **Do NOT predict per-facility.** Facility-level disruption rate ≈ 0 in news (data-starved).
  Predict at the consolidated-theme level.
- **Do NOT use the raw web-scrape dump as labels directly**, and do NOT trust the old
  geography matcher (800km + country fallback = noise). Use the cascade output.
- **Do NOT filter labels by LLM `confidence`** — it does not separate real from false
  (real mean 0.93 vs false 0.88). Use the strict second pass instead.
- **Do NOT broaden retrieval to the full ~31k pool.** It's ~75% noise terms (tariff, sanction,
  generic "strike", recall) that yield few real events. The **middle pool (~9.2k)** is the sweet spot.
- **Two-stage labeling is the pattern:** lenient `flash-lite` (recall) → strict `flash` (precision).
  Single-pass over-calls (40% precision); strict pass lifts it to ~80%.
- **Do NOT measure precision on a non-representative subset** — the early "88%" was a tiny
  tight-pool slice; the representative full-set number is **80%**.
- **Do NOT let the 2026-03 spike straddle the train/test split** (see §12.4).
- **Gemini Agent Platform gotchas:** express mode = `genai.Client(enterprise=True, api_key=...)`
  (NOT plain `api_key=`); `/v1/responses` 404s for deepseek (use `/v1/messages`); there is a
  **per-minute RPM limit → run ~8 workers, not 24** (24 trips 429 RESOURCE_EXHAUSTED).
- **Excel/Numbers saves the gold CSV as mac-roman**, not UTF-8 — `build_gold_set.py` now reads
  multiple encodings; keep that when editing the reader.
- **News is contemporaneous, not leading, for sudden events** (quakes/fires) — target near-term
  probability + detection, not multi-week foresight. This is why the predecessor's 14-day
  forecast failed structurally.

---

## 14. Phase-2 build results (measured — branch `disruption-rebuild-v2`)

Scripts: `scripts/build_easy_negatives.py` (T4), `train_relevance_classifier.py` (T5),
`train_predictor.py` (T7, parametric: `--targets`, `--drop`, `--tag`). Metrics persisted to
`data/relevance_metrics.json` and `data/predictor_metrics.json` (for the in-UI surface, T9).

- **T4 easy negatives:** 2,500 random non-`CANDIDATE_RE` articles → `easy_negatives` table. 0 match the filter (acceptance pass).
- **T5 relevance classifier** (TF-IDF + XGBoost, distills the cascade; gold held out):
  P=77% R=59% **F1=67%** vs keyword baseline F1=59% (**PASS**) and LLM-strict oracle F1=87%.
  Precision is near-oracle; **recall is the lever** (lower threshold / sentence-transformer embeddings).
- **T7 predictor** (pooled, calibrated XGBoost; split keeps 2026-03 spike in test):
  - **Chosen config = pooled, `dow`/`is_weekend` dropped.** Test (n=720, 21% base rate):
    AUC 0.61, **onset recall 71% (52/73)** at 23% precision; F1 38% vs persistence 54%.
  - **Headline = onset detection:** persistence (clustering rule) has **0% recall on new-onset
    disruptions by construction**; the news model catches 71% of them. That is the real "prediction."
  - Driving features (post-`dow`): `vol_3d/7d/14d` (article-volume momentum), `sent_min_3d/7d`
    (negative-sentiment spikes), `kw_hits_1d/3d`, `cross_clean_3d`. Clean "predict-from-news" story.

### Phase-2 lessons (hard-won — fold into §13)
- **`dow` (day-of-week) is a confound — drop it.** As a feature it dominated importance (0.27)
  by exploiting "disruptions get reported on weekdays." Dropping it lifts onset recall 55%→71%
  and removes an examiner-bait criticism. News-content features then drive the model.
- **Do NOT build a shipping-only model under the honest split.** The Gulf/Red Sea crisis
  escalated *after* 2026-02, so shipping has only **28 train vs 88 test positives** (7%→61%
  base-rate shift); calibration collapses (Brier 0.42). **Pool the targets** — the others supply
  training positives across the split, making the pooled model far more robust. (Reverses the
  §4 "shipping flagship" assumption.)
- **Brier is NOT a selling point here.** A constant base-rate predictor (~0.166) beats both the
  model (0.176) and persistence's hard-0/1 (0.190). Lead with **onset recall + AUC**, not Brier.
- **Persistence is a strong baseline on raw F1** (clustering) — the model cannot win raw F1 and
  should not claim to. Its value is onset anticipation, calibrated probabilities, and SHAP-able
  news features.
