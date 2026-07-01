# Emerging Sectors — Implementation Plan (LLM-free adaptive taxonomy)

> **Purpose of this file:** a complete, self-contained build spec for the "emerging sectors"
> feature, written to be handed to a coding model (Sonnet) that has *not* seen the design
> discussion. Read this top to bottom before writing code. Every file path, schema, and
> threshold below is grounded in the real repo state as of this writing.
>
> **This is a plan, not the thesis.** It does not need to follow the thesis style rules.
> Do not edit `DISRUPTION_REBUILD_DESIGN.md`; this feature lives in its own docs + scripts.

---

## 0. One-paragraph summary

Today the system monitors **5 fixed sectors** hard-coded in `scripts/train_predictor.py::TARGETS`.
This feature makes the taxonomy **adaptive**: it discovers *new* risk categories directly from the
live RSS stream, with **no LLM anywhere**, by (1) capturing a per-article "novelty" signal that
already exists in the pipeline, (2) clustering the novel articles offline, (3) detecting when a
cluster's article rate **bursts** above its own baseline, (4) surfacing bursting clusters in the UI
as descriptive "Emerging Risks" (not yet forecast), and (5) graduating durable clusters into a real
6th+ forecast sector once they have enough history to backfill features. Because everything is
recomputed **as-of** any date, the whole thing can be **replayed** on historical data — the
centerpiece demo.

---

## 1. Grounding: current state (verified against the repo)

### 1.1 The novelty signal already exists but is thrown away
`scripts/live_label.py::Labeler.label_batch()` returns a `LabelResult` dataclass with:
```python
relevant: bool     # P >= 0.59 relevance gate
P: float
themes: list[str]  # top-k<=2 themes >= TAU (0.30); falls back to nearest if none clear TAU
top_theme: str | None
top_sim: float     # cosine of the article embedding to the NEAREST of 12 theme prototypes
```
`top_sim` is the key. A **relevant** article (`P >= 0.59`) with a **low `top_sim`** is, by
definition, "a real supply-chain disruption that fits none of our existing sectors well." That is
the novelty signal. Right now `top_sim` is only embedded as free text inside the `reason` column
(`"...top_theme_sim=0.42"`) and is otherwise discarded.

### 1.2 `disruption_candidates` schema (live Postgres, verified)
```
article_title  text        article_id     text        article_url    text
article_date   date        is_risk_event  boolean      themes         jsonb
risk_type      text        confidence     double precision           reason  text
model          text        processed_at   timestamptz  strict_is_risk boolean
strict_model   text
```
There is **no** `top_sim` column, **no** stored embedding, and **no** body text (body lives on
`events.event_text_segment`). Counts: `events` = 181,391 rows, `disruption_candidates` = 9,281 rows,
candidate `article_date` range = 2021-12-14 → 2026-06-28.

### 1.3 Live insert point
`scripts/ingest_live.py` (~line 210) inserts each relevant article into `disruption_candidates`,
setting `themes`, `risk_type` (= `top_theme`), `confidence`, `reason`. This is the **only** place
the live path needs to change (add two columns to the insert).

### 1.4 Offline clustering already exists
`scripts/build_topic_model.py` runs **MiniLM embeddings → UMAP → HDBSCAN → c-TF-IDF keywords** over
the ~557 clean events and already emits `recent_90d_share` (a drift signal) and an `emergent` flag
per topic into `data/topic_model_summary.json` (`n_emergent: 1` currently). The c-TF-IDF keywords
give human-readable cluster labels **with no LLM**. This is the code to generalize.

### 1.5 Encoder + prototypes
- Encoder: `sentence-transformers/all-MiniLM-L6-v2`, 384-dim (used everywhere).
- `model_training/theme_prototypes.pkl` = `{encoder_name, themes:[12 names], protos: ndarray[12,384] L2-normalised, counts}`.
- Relevance gate thr = **0.59**; theme-routing TAU = **0.30**.

### 1.6 Snapshot / rewind machinery (what "as-of" means here)
`scripts/build_ui_snapshot.py` writes `web/public/data/ui_snapshot.json`, is `--as-of YYYY-MM-DD`
parameterized, builds rolling features per `(sector, date)`, smooths P over the last 3 days, and
maps P → status via `status_of`. The frontend rewinds via `web/src/lib/DateContext.tsx` →
`web/src/lib/useSnapshot.ts`, which caches past dates and always refetches `"live"`.

### 1.7 The pooled-predictor property (important for Tier 2)
Per `CLAUDE.md`, the predictor is a **pooled** XGBoost + isotonic model: one model trained over the
feature rows of *all* sectors, keyed by `(sector, date)`. Consequence: **a new sector does not
require retraining** to be scored — once its 16 rolling-window features are backfilled, the existing
model can predict it. Retraining is optional and only folds the new sector's events into calibration.

---

## 2. Design constraints (do not violate these)

1. **LLM-free.** No `gemini_client`, `openrouter_client`, `openmodel_client`, or any LLM call in any
   new code on the ingest or emerging-detection path. `ingest_live.py` has an assertion guard for
   this (~line 412); keep the new offline script equally clean. Cluster labels come from c-TF-IDF
   keywords only.
2. **As-of correctness is mandatory (this is what makes the replay demo real).** Any emerging-sector
   state shown for date `D` must be computable using **only** rows with `article_date <= D`. If
   detection ever peeks at the full corpus while claiming to show date `D`, the replay is fraudulent.
   Bake this into the data model from Phase 1, not as an afterthought.
3. **Descriptive vs predictive separation.** Tier 1 output is **descriptive** (a cluster is
   trending) and must be visually/labelled as "not a forecast." Only Tier 2 (graduated) sectors get
   a calibrated probability from the predictor.
4. **Sparsity honesty.** Total clean events ≈ 605; emerging clusters start with a handful of
   articles. The whole burst-detection design must resist single-day / single-source noise (hence
   the sustain + durability requirements below). Do not over-claim statistical significance.
5. **Additive, reversible.** New columns are nullable with defaults; new outputs are new files; the
   dynamic sector registry is a config file merged at read time, **not** an edit to the `TARGETS`
   dict in source. The 5 fixed sectors must keep working unchanged if the feature is disabled.

---

## 3. Tiers & phases overview

| Phase | Title | Tier | Deliverable |
|---|---|---|---|
| P1 | Persist novelty at ingest | 1 | 2 new columns + populated on every ingest |
| P2 | Novelty-pool clustering (as-of, offline) | 1 | `scripts/build_emerging_sectors.py` clustering step |
| P3 | Burst detection + status ladder | 1 | per-cluster velocity + `nascent/bursting/candidate` status |
| P4 | Emerging Risks UI strip | 1 | `web/` component driven by as-of timeline |
| P5 | Graduation → prototype + backfill | 2 | dynamic sector registry + backfilled features |
| P6 | Historical replay demo | 2 | scripted rewind showing discovery → graduation |

---

## 4. Data model changes

### 4.1 New columns on `disruption_candidates` (Phase 1)
```sql
ALTER TABLE disruption_candidates
  ADD COLUMN IF NOT EXISTS top_sim      double precision,   -- nearest-prototype cosine (novelty)
  ADD COLUMN IF NOT EXISTS is_unrouted  boolean DEFAULT false;  -- top_sim < TAU_NOVEL at ingest time
```
- Populate both in the `ingest_live.py` insert from the `LabelResult` (`top_sim` is already
  computed; `is_unrouted = top_sim < TAU_NOVEL`).
- Backfill historical rows once: re-encode existing candidates' titles (+body from `events`),
  recompute `top_sim` against `theme_prototypes.pkl`, and set the columns. Provide a one-shot
  `--backfill` mode in the offline script (Section 6, P2) so this is reproducible.

> **Embeddings are NOT stored.** With only ~9k candidate rows, the offline job re-encodes on demand
> (MiniLM does thousands/sec). This keeps Phase 1 to two scalar columns and avoids a vector-storage
> dependency. If performance ever demands it, add a `pgvector` column later; out of scope now.

### 4.2 Dynamic sector registry (Phase 5)
New file `config/dynamic_sectors.json` (tracked). Consumers that today read `TARGETS` must read the
**merge** of `TARGETS` + this file. Shape:
```json
{
  "version": 1,
  "sectors": [
    {
      "key": "panama_canal_drought",
      "name": "Panama Canal / drought transit limits",
      "themes": ["<generated theme name>"],
      "prototype_ref": "model_training/dynamic_protos/panama_canal_drought.npy",
      "graduated_on": "2026-05-11",
      "provenance": {"peak_z": 4.7, "n_articles_at_grad": 41, "weeks_sustained": 6}
    }
  ]
}
```
Provide a single accessor, e.g. `src/sectors.py::all_sectors()`, and refactor `build_ui_snapshot.py`
+ `train_predictor.py` to call it instead of importing `TARGETS` directly. (Keep `TARGETS` as the
static base.)

---

## 5. Data contracts (the JSON the UI and demo consume)

### 5.1 `data/emerging_timeline.json` (Phase 3 output, read by UI in Phase 4)
As-of aware time series. One entry per grid date; each lists cluster states as-of that date.
```json
{
  "generated_at": "2026-07-01T00:00:00Z",
  "grid_freq": "W",                      // weekly grid (see 6.3)
  "encoder": "sentence-transformers/all-MiniLM-L6-v2",
  "params": { "tau_novel": 0.30, "z_thresh": 2.5, "sustain_weeks": 2,
              "min_cluster_size": 8, "durability_k": 30, "durability_weeks": 4 },
  "dates": {
    "2026-05-11": {
      "clusters": [
        {
          "cluster_id": "c_017",              // STABLE across dates via centroid matching
          "label": "panama canal drought transit",   // top c-TF-IDF keywords, joined
          "keywords": ["panama","canal","drought","transit","gatun","draft"],
          "status": "bursting",               // nascent | bursting | candidate | graduated
          "n_total": 22,                      // cumulative articles <= this date
          "n_recent": 9,                      // articles in the trailing window
          "z": 3.1,                           // burst z-score as-of this date
          "velocity": [0,0,1,2,4,9],          // recent per-window counts (for sparkline)
          "first_seen": "2026-04-06",
          "example_titles": ["...", "..."]
        }
      ]
    }
  }
}
```
- `cluster_id` MUST be stable across dates (centroid matching, Section 6.4). The UI relies on this to
  draw a single cluster's velocity over the rewind.
- `"live"` state = the entry for the latest grid date; UI keys into `dates[as_of]` with graceful
  fallback to the nearest earlier grid date.

### 5.2 `data/emerging_sectors.json` (current snapshot convenience, optional)
Flat "as of latest" view = `emerging_timeline.dates[<max date>]`, written separately so the live UI
can fetch a small file. Optional; UI can also just read the timeline.

---

## 6. Phase-by-phase build

### P1 — Persist novelty at ingest
**Files:** `scripts/ingest_live.py`, new migration (inline `ALTER ... IF NOT EXISTS` run at startup
is acceptable, matching the repo's existing `CREATE TABLE IF NOT EXISTS` style).
**Steps:**
1. Add the two columns (Section 4.1).
2. In the insert (~line 210), add `top_sim` and `is_unrouted = result.top_sim < TAU_NOVEL`.
3. Define `TAU_NOVEL` as a module constant (start = `0.30`; tuned in Section 7).
**Gate:** after one `python -m scripts.ingest_live` cycle, `SELECT top_sim, is_unrouted FROM
disruption_candidates ORDER BY processed_at DESC LIMIT 20` shows populated values; no LLM import
introduced (the existing assertion still passes).

### P2 — Novelty-pool clustering (offline, as-of aware)
**New file:** `scripts/build_emerging_sectors.py`. Reuse the embedding→UMAP→HDBSCAN→c-TF-IDF
machinery from `build_topic_model.py` (refactor shared helpers into a small module if clean, e.g.
`src/topic_utils.py`).
**Modes:**
- `--backfill` : recompute `top_sim`/`is_unrouted` for all existing candidates (satisfies P1 backfill).
- `--as-of YYYY-MM-DD` : build state for a single date.
- `--grid` : iterate the whole historical grid and write `data/emerging_timeline.json`.
**Novelty pool definition (per as-of date D):**
```
relevant AND is_risk_event AND article_date <= D AND top_sim < TAU_NOVEL
```
**Clustering:** HDBSCAN with `min_cluster_size = MIN_CLUSTER` (start 8) over the pool's embeddings.
Outliers (label -1) are ignored. Each cluster → c-TF-IDF keywords for its label + centroid (mean
L2-normalised embedding).
**Gate:** on the full corpus, produces a sane set of clusters with readable keyword labels; cluster
count and sizes printed; runs with only `article_date <= D` rows when `--as-of` is given (assert no
future rows sneak in).

### P3 — Burst detection + status ladder
**Same file.** For each cluster `c` and as-of date `D`:
1. Build per-window counts `n_c(t)` over the trailing horizon (weekly buckets recommended).
2. Baseline = mean + std of counts over a trailing baseline window (e.g. last 8 weeks **excluding**
   the current window). Guard zero-variance with a small floor.
3. `z = (n_recent - baseline_mean) / max(baseline_std, floor)`.
4. **Status ladder:**
   - `nascent`   : cluster exists, `size >= MIN_CLUSTER`, not bursting.
   - `bursting`  : `z >= Z_THRESH` sustained for `>= SUSTAIN_WEEKS` consecutive windows.
   - `candidate` : bursting **and** `n_total >= DURABILITY_K` over `>= DURABILITY_WEEKS` (eligible
     for Tier 2 graduation).
5. Emit `data/emerging_timeline.json` (Section 5.1).
**Emergence selection for the demo:** rank clusters by peak historical `z`; pick one with a clear
pre/post transition and a recognizable label for P6. (Plausible real emergents outside the 5 fixed
sectors, judging from existing keywords: trade-war/tariffs, port-labor strikes, Panama Canal
drought, undersea-cable cuts. Confirm empirically; do not hard-code.)
**Gate:** replaying the grid shows the chosen cluster climbing `nascent → bursting → candidate`
across consecutive dates, and staying `nascent`/absent on quiet dates.

### P4 — Emerging Risks UI strip
**Files:** new `web/src/components/EmergingRisks.tsx`; wire into the Map (`web/src/pages/MapView.tsx`)
and/or Dashboard. Data via a small loader in `web/src/lib/` reading `data/emerging_timeline.json`,
keyed by `useDate().asOf` with fallback to nearest earlier grid date.
**UI:** compact panel listing candidate clusters with: keyword label, status pill
(`nascent/bursting/candidate`), article count, and a velocity sparkline (the `velocity` array).
**Must** carry an explicit "Emerging signal — not yet forecast" caption to preserve the
descriptive/predictive separation.
**Gate:** rewinding the DateWheel across the demo window animates the strip (cluster appears, grows,
escalates); on live it shows current state; degrades gracefully if the file is missing.

### P5 — Graduation → prototype + backfill (Tier 2)
**Files:** `scripts/graduate_sector.py` (new); `config/dynamic_sectors.json`; `src/sectors.py`
accessor; touch `build_ui_snapshot.py` + `train_predictor.py` to read merged sectors.
**Steps:**
1. Input: a `candidate` cluster key + its members (as-of the graduation date).
2. Compute its prototype = mean L2-normalised member embedding (mirror
   `scripts/build_theme_prototypes.py`); save to `model_training/dynamic_protos/<key>.npy`.
3. Append a sector record to `config/dynamic_sectors.json` (Section 4.2).
4. Backfill 16 rolling-window features for `(new_sector, date)` over history, exactly as
   `train_predictor.py`/`build_ui_snapshot.py` build features for existing sectors.
5. **No mandatory retrain:** the pooled model scores the new sector from its backfilled features
   immediately. Optionally re-run `train_predictor` to fold the new events into isotonic calibration;
   note in `data/predictor_metrics.json` provenance if you do.
6. Live routing: once graduated, the new prototype should also participate in `ingest_live` theme
   routing so fresh articles route into it. Add dynamic prototypes to the routing set loaded from
   `theme_prototypes.pkl` + `dynamic_protos/`.
**Gate:** after graduating a cluster, `build_ui_snapshot --as-of <post-grad date>` returns 6 sectors,
the new one carries a calibrated P and a status, and the 5 originals are unchanged.

### P6 — Historical replay demo
**File:** `scripts/replay_emerging.py` (or a documented click-path). Rewind to just before the chosen
cluster's burst; step the DateWheel forward through: cluster first appears (`nascent`) → escalates
(`bursting` → `candidate`) → is graduated → appears as a forecast sector with its own P. This is the
strongest viva artifact. Script it so it is reproducible (fixed date list + expected statuses) and
add an assertion-style check that the observed status sequence matches the expected one.
**Gate:** the scripted sequence reproduces the same status ladder deterministically (fixed seeds:
UMAP/HDBSCAN `SEED=42` as in `build_topic_model.py`).

---

## 7. Tunable thresholds (single source of truth)

Put all of these in one config block at the top of `build_emerging_sectors.py` (and mirror the
relevant ones in `ingest_live.py`). Starting values + how to tune:

| Name | Start | Meaning | Tuning method |
|---|---|---|---|
| `TAU_NOVEL` | 0.30 | novelty ceiling on `top_sim`; below = novel | Plot `top_sim` distribution for gold-routed vs unrouted; set at the valley. Must be **>=** routing TAU so genuinely-routed items are excluded. |
| `MIN_CLUSTER` | 8 | HDBSCAN `min_cluster_size` | Lower = more (noisier) clusters. Pick smallest that yields stable, readable clusters on the novelty pool. |
| `Z_THRESH` | 2.5 | burst z-score | Higher = fewer false bursts. Validate against known past spikes. |
| `SUSTAIN_WEEKS` | 2 | consecutive bursting windows required | Raise to kill single-week noise; lower for earlier detection. |
| `DURABILITY_K` | 30 | cumulative articles to be `candidate` | Set so graduation needs enough rows to backfill meaningful features. |
| `DURABILITY_WEEKS` | 4 | weeks over which K must accrue | Prevents one big news day from graduating. |
| `BASELINE_WEEKS` | 8 | trailing baseline window for z | Long enough to be stable, short enough to adapt. |

Write the tuning evidence (distribution plots / chosen values) into `data/emerging_tuning.json` for
the thesis Accuracy page.

---

## 8. Grid & performance (the as-of cost trade-off)

Re-clustering at every daily date over history is expensive; two honest options:

- **Strict weekly (recommended default).** Grid = weekly (`freq="W"`), and at each grid date
  **re-cluster** using only `article_date <= D`. ~230 weekly points, each clustering a few-thousand-doc
  pool = minutes-to-tens-of-minutes offline. Fully as-of pure. Use this for the demo window.
- **Approximate (optional, cheaper).** Cluster once on full history for cluster *definitions*, then
  compute per-date *status* from `<= D` counts only. Cheaper but leaks cluster definition from the
  future; acceptable only for the broad background timeline, never for the demo slice. If used, label
  it clearly in output provenance.

Default to strict-weekly. Cache embeddings in-process across grid dates (encode the full pool once,
slice by date) so only clustering repeats.

---

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Cluster IDs reshuffle across refits, breaking the timeline | Centroid matching (Section 6.4): each grid step, match new centroids to previous by cosine, carry IDs forward; unmatched = new cluster. |
| Single loud news day fakes a burst | `SUSTAIN_WEEKS` + `DURABILITY_WEEKS` + source-diversity check (optionally require articles from >= 2 distinct `article_source`). |
| Emerging cluster is just a variant of an existing sector | It came from the `top_sim < TAU_NOVEL` pool, so it is already dissimilar to all 12 prototypes; also report nearest existing sector + distance in provenance for reviewer sanity. |
| New sector has no history → can't forecast on day one | Expected and honest: Tier 1 surfaces it descriptively; Tier 2 forecast only after backfill. The replay demo shows the *mechanism* on a past emergence where history exists. |
| Non-determinism (UMAP/HDBSCAN) | Fix `SEED=42` (as in `build_topic_model.py`); assert stable output in P6. |
| Frontend cache serves stale emerging state | Reuse `useSnapshot`'s existing pattern: never cache the `"live"` key; bump a cache version if the JSON shape changes. |

---

## 10. Out of scope (do not build now)

- pgvector / stored embeddings (re-encode offline instead).
- Online/streaming clustering (weekly offline re-cluster is sufficient).
- Auto-graduation without human confirmation — graduation (P5) should be an explicit operator step,
  not automatic, for the FYP.
- Any LLM-based labeling or summarization.
- Fixing geocoding/alerts (tracked separately).

---

## 11. Suggested commit sequence (one PR-sized change per step)

1. `feat(emerging): P1 persist top_sim + is_unrouted at ingest (+ backfill)`
2. `feat(emerging): P2 novelty-pool clustering, as-of aware (build_emerging_sectors.py)`
3. `feat(emerging): P3 burst detection + status ladder + emerging_timeline.json`
4. `feat(emerging): P4 Emerging Risks UI strip (as-of driven)`
5. `feat(emerging): P5 dynamic sector registry + graduation + backfill`
6. `feat(emerging): P6 scripted historical replay demo`

Each step has a Gate above; do not proceed to the next until its Gate passes.
