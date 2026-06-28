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
- **Phase 2 — Own NLP models (T4/T5/T6 DONE):**
  - T4 **(DONE)** Easy negatives — 2,500 random non-`CANDIDATE_RE` articles → `easy_negatives`
    table. `scripts/build_easy_negatives.py`.
  - T5 **(DONE)** Relevance classifier (TF-IDF + XGBoost) — F1 **67%** vs keyword baseline 59%
    (PASS), oracle 87%. Recall (59%) was the weak link. `scripts/train_relevance_classifier.py`.
  - T5+ **(DONE, improvement B)** Sentence-transformer (all-MiniLM-L6-v2) variant fixes recall:
    emb+LogReg **R 59%→89%**, F1 67%→69% (73% tuned); emb+XGBoost 69/75/72 (balanced).
    `scripts/train_relevance_embeddings.py`. New dep: `sentence-transformers`. Recall-first choice
    for a live early-warning filter. **Chosen live relevance model = embeddings.**
  - T6 **(DONE)** Topic model — BERTopic (MiniLM→UMAP→HDBSCAN→c-TF-IDF) over the 557 clean
    events. 12 coherent topics, 0 outliers; **11/12 map cleanly to a fixed target** (validates the
    supervised targets), 1 emergent (manufacturing/production); `recent_90d_share` = drift signal.
    Acceptance PASS. Shipping-dominated corpus → topics mostly sub-divide shipping (faithful to
    82% reality). Discovery/scope layer, NOT a predictor feature. `scripts/build_topic_model.py`,
    summary `data/topic_model_summary.json`, assignments `data/topic_assignments.csv`.
- **Phase 3 — Predictor + eval + UI:**
  - T7 **(DONE)** (target, day) feature grid from RAW stream + pooled calibrated predictor (no
    severity head). Chosen config: pooled, `dow` dropped. `scripts/train_predictor.py`. See §14.
  - T8 **(DONE)** Leakage + walk-forward tests — truncation-invariance max diff 0.0 (no leak),
    calib disjoint, **walk-forward mean AUC 0.733** (90% folds >0.55). `scripts/test_predictor.py`.
  - T9 **(DONE)** Fresh `web/` app — 4 views (Map landing, Sectors, Products, Accuracy), paper-terminal
    skin, `build_ui_snapshot.py` bridge. In-UI metrics surfaced on the Accuracy page.
  - T10 **(SPEC'd — see §16)** Live ingestion (RSS + Perigon recent window) → embeddings relevance
    classifier + embedding theme-router → `events`/`disruption_candidates` (no LLM in the loop).
- **Phase 4 — Stretch:** T11 scheduled-event lead-time extraction.

**Model-improvement menu (results):**
- (B) **DONE, big win** — sentence-transformer relevance classifier, recall 59%→89% (see T5+).
- (C) **DONE, null result** — semantic embedding feature for the predictor does NOT help
  (walk-forward AUC 0.733→0.716; single split 0.645→0.597). `scripts/train_predictor_embed.py`,
  report `data/predictor_embed_report.json`. **Why:** relevance is text-classification (semantics =
  signal) but the predictor is time-series (signal = volume/recency/sentiment dynamics, not
  recent-article semantics). Canonical predictor unchanged.
- (D) **not done** — extend the cascade for more labeled positives. Only 122 event-days; C proved
  the bottleneck is **data quantity, not features**, so D is the predictor's only real lever — but
  it costs Gemini calls. Decide vs shipping the (already walk-forward-defensible) model to T9.

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
  - **Chosen config = pooled, `dow`/`is_weekend` dropped.** Single-split test (n=720, 21% base rate):
    AUC 0.61, **onset recall 71% (52/73)** at 23% precision; F1 38% vs persistence 54%.
  - **Headline = onset detection:** persistence (clustering rule) has **0% recall on new-onset
    disruptions by construction**; the news model catches 71% of them. That is the real "prediction."
  - Driving features (post-`dow`): `vol_3d/7d/14d` (article-volume momentum), `sent_min_3d/7d`
    (negative-sentiment spikes), `kw_hits_1d/3d`, `cross_clean_3d`. Clean "predict-from-news" story.
- **T8 leakage + walk-forward tests** (`scripts/test_predictor.py`, report
  `data/predictor_test_report.json`):
  - **No leakage (proven):** feature truncation-invariance — rebuilding every feature with future
    data hidden gives byte-identical values (max |full−truncated| = 0.0 over 15 cells). Calib slice
    disjoint from test. Both hard assertions PASS.
  - **Walk-forward (10 monthly rolling origins, each trained only on its past): mean AUC 0.733,
    90% of folds >0.55.** The single 2026-02 split (AUC 0.61) was pessimistic; the signal generalizes.
  - **Complementarity demonstrated:** in sparse/early folds (2025-08→2026-02) persistence F1 ≈ 0
    while the model holds AUC 0.56–0.88 — news carries the signal exactly when clustering can't.
    The lone weak fold is 2026-03 (AUC 0.51), the pervasive-disruption spike where ranking is hard
    and persistence finally works (F1 0.53). Honest and explainable.

### Current standing (as of T8) — viva-defensible
Leakage-proven pipeline; relevance F1 0.67 (>baseline); predictor walk-forward AUC 0.733 with
onset recall 71% on new disruptions persistence cannot predict. The honest framing is **onset
anticipation + calibrated ranking from news content**, NOT beating persistence on raw F1 (it can't;
disruptions cluster) and NOT Brier (a constant base-rate ~0.166 beats everyone). Remaining: T9 UI.

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

---

## 15. UI & presentation layer (T9)

Fresh frontend — **new Vite + React + TypeScript app in `web/`** (NOT a revival of
`chain-calm-main`, which was supplier-node-centric). v2 is **target/theme-centric**. Reads model
outputs; no per-facility prediction in the UI (composition only).

### Views (public-first)
1. **Global situation map** — world map; 5 targets as geographic markers coloured by status;
   live disruption events plotted from `events.latitude/longitude` (already geocoded); shipping
   lane Hormuz→Red Sea→Suez highlights when disrupted. Click marker → sector card.
2. **Sector status board** — the 5 consolidated targets in plain language: status
   (calm / watch / active disruption), one-line "what's happening", 3-day outlook
   (unlikely / possible / likely + low/med/high), and "why now" headlines.
3. **Product supply chain** — iPhone / AirPods / EV / Laptop as a **weighted composition** of the
   5 targets (approximate BOM). Exposure = aggregate of target predictions by reliance weight;
   shows the driver. **Composition, NOT a new model** — must not reach down to per-facility scoring.
4. **Model accuracy** — technical validation page (secondary, for examiner): relevance P/R/F1 vs
   baselines, predictor walk-forward AUC, leakage-test badges, discovered topics.

### Plain-language mapping (model → words)
- `P(disruption next 1-3d)`: `<0.15` unlikely · `0.15–0.35` possible · `>0.35` likely.
- status pill from current activity (recent clean events + onset flag): calm / watch / active.
- "why now" = top recent matched headlines per target (from `events`).
- accuracy phrased plainly ("right ~7 in 10 times on new disruptions"), not "AUC 0.73".

### Design language — "paper terminal" (skin only; layouts stay friendly)
- **Palette (light, primary):** paper `#EFEDE4`, panel `#F7F5EE`, ink `#20201C`, border `#D7D3C7`;
  status calm `#2F7D4F`, watch `#B07D29`, alert `#B23A2E`. Colour only encodes status.
- **Palette (dark CRT variant, toggle):** base `#0E0F0C`, panel `#14160F`, phosphor `#E4E2D8`,
  border `#2A2E22`; calm `#4FB36A`, watch `#D6A23C`, alert `#E0584B`.
- **Type:** display/headers + big numbers = dot-matrix **Doto**; body/labels = clean mono
  **IBM Plex Mono** (or JetBrains Mono); labels UPPERCASE, letter-spacing ~0.14em.
- **Treatment:** hairline-bordered panels, tick-mark + dotted-leader panel headers, LED status
  dots, prominent numeric readouts. Instrument-grade but legible.
- **Toggles:** light↔dark (CRT), and optional lite↔pro density. Implement palette as CSS tokens.

### Data + rewind
- All views computed **for a given date** (default = latest). Backend `as_of` pattern → the
  **rewind-to-past-date** feature (later) drops in without a rebuild.
- Bridge: `scripts/build_ui_snapshot.py` writes `data/ui_snapshot.json` (per-target current status,
  P(next 3d), recent headlines, map points) by running `model_training/predictor.pkl` on the latest
  features. UI reads the snapshot + the metric JSONs; a small FastAPI read layer can serve them later.
- **Live "current" status depends on live ingestion (T10).** Until then the board reflects the
  latest available data date — state this in the UI.

## 16. Live ingestion (T10) — LLM-free build spec

**Goal:** keep `events` and `disruption_candidates` fresh from live news so the snapshot (and UI)
advances day-to-day, **with no generative LLM in the loop**. The one-time Gemini cascade that
labeled the 180k corpus is replaced live by the **embeddings relevance classifier** (T5/Improvement B)
+ an **embedding theme-router**. The predictor (`predictor.pkl`) is **fixed** — no retraining in T10;
features are recomputed live by the existing `build_target_frame`.

### 16.1 Data contract (what the live loop MUST produce)
The predictor + snapshot read exactly two tables. Live writes must satisfy both:

- **`events`** (raw corpus, 180,939 rows, PK `id`, dedup key `article_url`). Live insert must populate:
  `article_url`, `article_source`, `article_title`, `article_timestamp` (timestamp), `event_text_segment`
  (body/summary), `sentiment_score` (DOUBLE), `sentiment_label`, and best-effort `latitude`/`longitude`.
  Consumed by `daily_news()` (per-day count + `AVG/MIN(sentiment_score)` over a keyword-regex slice) and
  `map_points()` (lat/lon dots). **Sentiment scale is RESOLVED:** the corpus convention is signed
  **[−1, 1], neutral = 0.0** (verified: min −0.977, max 0.963, 0 nulls), produced by
  `src.sentiment_finbert.analyze_finbert` / `batch_analyze_finbert` (FinBERT, returns
  `{label, sentiment_score∈[−1,1], confidence}` — positive → +conf, negative → −conf, neutral → 0).
  **Call that function directly** — do not invent a new sentiment path or the `sent_mean/min` features
  shift under the fixed model. (All deps — `feedparser`, `sentence_transformers`, `transformers`,
  `vaderSentiment` — already in `venv311`; nothing to install.)
- **`disruption_candidates`** (clean-event layer, PK `article_title`). A clean event =
  `is_risk_event AND strict_is_risk`. Live insert for a **relevant** article sets **both true in one
  shot** (the embeddings classifier was trained positive = `is_risk_event AND strict_is_risk` (557),
  negative = `is_risk_event AND NOT strict_is_risk` (1082) — it already collapses the two LLM stages):
  `article_title` (PK), `article_id`, `article_url`, `article_date` (= `article_timestamp::date`),
  `is_risk_event=true`, `strict_is_risk=true`, `themes` (JSONB, ≥1 name from the 12-name `THEMES`),
  `risk_type` (router label), `confidence` (classifier P), `reason` ("emb-relevance ≥ thr"),
  `model`/`strict_model` = `"emb-minilm-logreg"`. Consumed by `clean_event_days()` (filters by
  `themes` ∈ target's theme list). **Non-relevant articles are NOT written here** — they only land in
  `events`, and url-dedup stops re-fetch, so no "seen" marker is needed.

### 16.2 Pipeline (LLM-free)
```
RSS feeds (primary, live) + Perigon recent window (supplement, last 24–72h)
  → dedup by article_url against events          (skip rows already present)
  → parse: title, body, source, timestamp, url
  → sentiment: FinBERT (match corpus scale) → sentiment_score, sentiment_label
  → geocode (best-effort, non-blocking): GLiNER2 NER → geocode cache → lat/lon
  → INSERT events (ON CONFLICT (article_url) DO NOTHING)
  → relevance: MiniLM encode title+body ONCE; emb_logreg classifier P(disruption); thr = 0.59
       P ≥ 0.59 ? ── yes ─→ theme-router (reuse same MiniLM vector):
       │                      cosine to per-theme prototypes; take themes ≥ τ (top-k, k≤2);
       │                      fallback to per-theme keyword regex if none clear τ
       │                    → INSERT disruption_candidates (is_risk_event=t, strict_is_risk=t, themes=…)
       └────────── no ──→  (already in events; nothing more)
  → build_ui_snapshot --as-of <today>   (predictor.pkl is fixed; features recomputed live)
```
No call to `src.gemini_client` / OpenRouter / OpenModel anywhere on this path — assert it in a test.

### 16.3 Components to build
1. **`scripts/build_theme_prototypes.py`** (one-time, re-runnable). Encode the 557 clean events
   (`is_risk_event AND strict_is_risk`) with `all-MiniLM-L6-v2` (normalized), average per theme →
   `model_training/theme_prototypes.pkl` = `{encoder_name, themes:[…], protos: np.ndarray[12×384]}`.
   This is the LLM-free theme assigner; prototypes come from the already-labeled positives.
2. **`scripts/live_label.py`** (shared labeler, importable). Loads `relevance_classifier_emb.pkl`
   (`{encoder_name, classifier=LogReg, best_model}` — `classifier.predict_proba(X)[:,1]`) +
   `theme_prototypes.pkl`; one MiniLM encoder instance, `normalize_embeddings=True`.
   `label_batch(texts) -> [{relevant, P, themes, top_theme, sim}]`. **Threshold = 0.59** (the
   documented `best_thr` in `relevance_metrics_embeddings.json`: R=0.889, P=0.615, F1=0.727 vs 0.5's
   F1=0.691). τ for theme cosine ≈0.30 (tune on the 557; pick so ≥95% of known positives route to
   their gold theme).
3. **`scripts/ingest_live.py`** (slim runner — fresh, NOT legacy `rss_ingest.py`). Reuses only:
   `feedparser` parse helpers (`_strip_html`, `_entry_timestamp`), `src.sentiment_finbert`,
   optionally `src.preprocessing`(GLiNER2)+`src.geocoding`, `src.db_config`. Drops all legacy
   heavyweight heads (tri-class `classifier.pkl`, disruption/impact XGB, node-match, temporal,
   forecast_snapshots). Flags: `--interval N` (poll loop), `--skip-db` (dry-run print),
   `--source rss|perigon|both`, `--limit`, `--no-geocode`. Ends each cycle by invoking
   `scripts.build_ui_snapshot` with `--as-of` = max(`article_timestamp`)::date.
4. **`config/rss_feeds.json`** — copy from `legacy/config/rss_feeds.json` (JSON array of
   `{url, source}`). Curated supply-chain + general-news feeds.
5. **Perigon (OPTIONAL — RSS alone makes a working T10).** The 15 RSS feeds in
   `legacy/config/rss_feeds.json` (SupplyChainDive, FreightWaves, Reuters, JOC, Labor Notes, …) are
   live and sufficient to demo. Perigon is a recent-window supplement only (≤3 months back, 150
   req/month). **Open micro-decision if pursued:** legacy `perigon_ingest.fetch_articles_for_node`
   is supplier-node-centric; v2 is theme-centric, so send one broad supply-chain query (or per-theme
   queries) instead of per-node. Defer unless RSS volume proves too thin.
6. **`web/src/pages/Feed.tsx`** — new 5th view **"Live feed / Evidence"** (route `/feed`, add to
   `TopBar`). The transparency page that proves the model isn't a black box: a reverse-chronological
   table of recently ingested articles, each row = `time · source · headline · relevance P
   (≥thr ✓/✗) · routed theme · sentiment · which sector it feeds`. Click a row → the feature deltas
   it contributed to that sector's current score (e.g. "bumped `kw_hits_3d` +1, `clean_cnt_3d` +1 →
   sector P 0.21 → 0.27"). Reads a new `feed[]` block in the snapshot (no new endpoint). Relevant
   articles get a calm/positive accent; scored-but-rejected articles (P<thr) are shown muted, so the
   examiner sees the classifier's discriminating decisions, not just the hits.

### Influence of live ingestion on each page (confirmation)
- **Map / Sectors / Products → live.** Map & Sectors read per-target status/P/headlines/event-dots
  straight from the snapshot; Products is a client-side composition of the sector P values, so it
  moves whenever sectors move. A freshly-ingested clean event flows through `clean_event_days` →
  features → predictor → snapshot → all three.
- **Feed → live (most directly).** It *is* the live article stream with per-article evidence.
- **Accuracy → static by design.** Validation metrics (walk-forward AUC, relevance F1/recall,
  leakage badges, topics) are frozen held-out evaluation; the predictor is **fixed** in T10 (no
  retrain in the loop), so live news changes *today's prediction*, not *measured model quality*. The
  only live-moving figure there is the dataset-size counter (clean-events / event-days / articles)
  if wired to live `COUNT`s — a tally, not a quality metric. Reported AUC/F1 only change under a
  future retrain task (§16.7). State this on the page so the freeze reads as intentional rigor.

### 16.4 `build_ui_snapshot` change
`GRID_END` (2026-06-27) is the predictor's training cutoff; the snapshot's `--as-of` is independent
(features run `LOOKBACK_START..as_of`). Change the snapshot default from the hardcoded `GRID_END` to
`max(article_timestamp)::date` from the DB (fall back to `GRID_END`), so live data drives "current"
without a flag. Keep `--as-of` for rewind. Update the snapshot's `data_note` + the hardcoded
`summary` counts (557/122/180939) to live `SELECT COUNT`s.

**Emit a `feed[]` block for the Evidence page.** Add, per recent article (last ~14d, cap ~120, both
relevant and a sample of scored-but-rejected): `{ts, source, title, url, relevance_p, relevant
(bool), theme, sentiment_score, sector_key}`. For relevant rows also attach `contributes`: the
feature(s) it incremented for its sector (`kw_hits_3d`, `clean_cnt_3d`, `vol_3d`, sentiment) plus the
sector's current `p` — enough to render the before/after deltas. `relevance_p`/`theme` come from the
live labeler at ingest time; **persist them** so the snapshot can read them back rather than
re-encoding (store `relevance_p` in `disruption_candidates.confidence` (already there) and the routed
theme in `themes`; for rejected rows, either a lightweight `article_scores(article_url, p, ts)` table
or recompute on the fly in the snapshot for the recent window). Keep the encode-once discipline:
the labeler already has the vector at ingest — write it through, don't recompute in the UI bridge.

### 16.5 Scheduling
Dev: `venv311/bin/python -m scripts.ingest_live --interval 1800`. Prod: launchd (macOS) /cron every
20–30 min calling one cycle. One cycle = fetch → label → insert → rebuild snapshot. Idempotent, so
overlap is harmless.

### 16.6 Acceptance criteria (T10)
- **Dry-run:** `--skip-db` fetches RSS, scores, prints N relevant/total with themes; writes nothing.
- **Insert correctness:** new `events` rows appear; relevant → `disruption_candidates` with
  `is_risk_event=strict_is_risk=true`, `themes ⊆ THEMES` (12 names), `article_date` set.
- **Dedup:** re-running the same cycle inserts **0** new rows (url + title conflicts no-op).
- **Theme routing sanity:** a Red-Sea/Hormuz headline routes to a shipping theme; a TSMC headline to
  a semiconductor theme (assert on a small fixture set).
- **Snapshot advances:** after a cycle, `ui_snapshot.json` `as_of` = new max date; sectors recompute;
  a freshly-inserted clean event moves its sector toward watch/active.
- **No-LLM guarantee:** `ingest_live` + `live_label` import-graph contains no `gemini_client`,
  `openrouter_client`, `openmodel_client` (grep-assert in a test).
- **Sentiment scale:** live `sentiment_score` distribution matches the historical corpus
  (same sign/range) — spot-check 10 rows.
- **Evidence page round-trip:** an article in `feed[]` shows its `relevance_p`, routed `theme`, and
  sentiment; clicking a relevant row shows the feature delta(s) it added and the sector's current `p`.
  The same article's contribution is traceable from feed → sector card → map marker (one event, three
  consistent views).

### 16.7 Out of scope for T10 (later)
Predictor retraining on live-grown positives (T-future "D: more labels"); scheduled-event lead-time
extraction (T11); a FastAPI read layer replacing the static snapshot JSON; backfilling geocode for
historical rows. T10 is ingestion + live labeling only.

### 16.8 Known risks & micro-decisions (named, not blockers)
- **RSS body is short.** Feeds give title + a short summary; the classifier trained on title+body
  from the corpus. Encode `title + " " + summary`; accept that thin summaries lower confidence. If
  recall drops, optionally fetch the article page body (adds latency + a dependency) — defer.
- **`disruption_candidates.article_id` linkage.** Insert `events` first; the predictor/snapshot
  never join on `article_id` (they key on `article_title` / `themes` / dates), so set `article_id`
  to the returned `events.id` (or leave null) — not load-bearing. `article_title` is the PK and the
  real dedup key; use `ON CONFLICT (article_title) DO NOTHING`.
- **Geocoding is optional.** GLiNER2 NER + geocode (`src.preprocessing` + `src.geocoding`) is heavy
  and only feeds map *dots* (sector markers use fixed coords). Ship `--no-geocode` as a clean path;
  enable best-effort when the models load.
- **Encode-once discipline.** One MiniLM `encode()` per article feeds BOTH relevance and theme
  routing; never re-encode in `build_ui_snapshot` — read `relevance_p`/`theme` back from the DB.
- **Dependencies & sentiment scale are already resolved** (§16.1) — no installs, call
  `analyze_finbert`. The only numbers Sonnet must *tune* are τ (theme cosine) on the 557.
