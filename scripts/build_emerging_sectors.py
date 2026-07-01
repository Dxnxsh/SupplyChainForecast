"""Emerging Sectors P1-P3 — novelty-pool clustering + burst detection
(EMERGING_SECTORS_PLAN.md §6).

Discovers candidate new sectors, LLM-free, by clustering the "unrouted" pool: clean
disruption_candidates whose top-prototype cosine similarity (top_sim, from
scripts.live_label's theme router) falls below TAU_NOVEL. Reuses the MiniLM -> UMAP ->
HDBSCAN -> c-TF-IDF pipeline from scripts.build_topic_model, but scoped to the novelty
pool and made as-of aware so historical dates can be replayed without ever seeing rows
from the future (EMERGING_SECTORS_PLAN.md §2 constraint 2, §8).

--grid replays the whole history on a weekly grid, carries stable cluster identity across
re-fits via nearest-centroid matching, and applies the nascent/bursting/candidate status
ladder from per-cluster weekly velocity vs its own trailing baseline (P3), writing
data/emerging_timeline.json (the §5.1 data contract the P4 UI reads).

This module owns the single-source-of-truth config block for the whole emerging-sectors
feature (EMERGING_SECTORS_PLAN.md §7); scripts.ingest_live imports TAU_NOVEL and
ensure_novelty_columns from here rather than defining its own copies.

Usage:
  venv311/bin/python -m scripts.build_emerging_sectors --backfill
  venv311/bin/python -m scripts.build_emerging_sectors --as-of 2026-05-11
  venv311/bin/python -m scripts.build_emerging_sectors --grid
  venv311/bin/python -m scripts.build_emerging_sectors               # as-of = latest date
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from src.db_config import DB_CONNECTION_STRING, get_read_db_url

# ── config (EMERGING_SECTORS_PLAN.md §7 — single source of truth for all phases) ───────
ENCODER = "sentence-transformers/all-MiniLM-L6-v2"
PROTO_PKL = "model_training/theme_prototypes.pkl"
SEED = 42

TAU_NOVEL = 0.45          # novelty ceiling on top_sim; below = candidate for the emerging pool
                          # Empirically tuned (not the routing τ=0.30 — that was tuned to
                          # maximize gold-theme recall, a different objective). top_sim over the
                          # 606 historical clean candidates is a smooth, ~unimodal distribution
                          # (median 0.66, p25 0.56); there is no clean bimodal valley. At 0.30
                          # only 2/606 rows qualify (unusable — can't cluster 2 points). 0.45 sits
                          # just below the p10-p12 breakpoint (~0.47-0.49), giving a workable
                          # ~55-60 row historical pool while still excluding the bulk of clearly
                          # on-theme content. Retune via `--tune-tau` if the corpus changes
                          # materially; see data/emerging_tuning.json for the evidence.
MIN_CLUSTER = 8           # HDBSCAN min_cluster_size over the novelty pool          (P2, this file)
MIN_FOR_CLUSTERING = max(6, MIN_CLUSTER)  # skip clustering below this pool size    (P2, this file)
Z_THRESH = 2.5            # burst z-score threshold                                 (P3)
SUSTAIN_WEEKS = 2         # consecutive bursting windows required                   (P3)
DURABILITY_K = 30         # cumulative articles required to reach "candidate"       (P3)
DURABILITY_WEEKS = 4      # weeks over which DURABILITY_K must accrue               (P3)
BASELINE_WEEKS = 8        # trailing baseline window for the burst z-score          (P3)
Z_STD_FLOOR = 0.5         # guards div-by-~0 when the baseline window is near-empty (P3)
CENTROID_MATCH_THR = 0.85  # cosine sim to carry a stable cluster_id across grid dates (P3)

TIMELINE_OUT = "web/public/data/emerging_timeline.json"   # served as a static asset (P4 UI),
                                                            # mirrors build_ui_snapshot.py's OUT
GRID_FREQ = "W"                                 # weekly grid (§8: strict-weekly default)


def ensure_novelty_columns(conn) -> None:
    """Additive, idempotent — see EMERGING_SECTORS_PLAN.md §4.1."""
    conn.execute(text("""
        ALTER TABLE disruption_candidates
          ADD COLUMN IF NOT EXISTS top_sim double precision,
          ADD COLUMN IF NOT EXISTS is_unrouted boolean DEFAULT false
    """))


def load_clean_candidates() -> pd.DataFrame:
    """The same 'clean' corpus as build_topic_model.py: is_risk_event AND strict_is_risk."""
    engine = create_engine(get_read_db_url())
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT d.article_title, d.article_id, d.article_url, d.article_date,
                   d.themes::text, d.top_sim, d.is_unrouted,
                   COALESCE((SELECT LEFT(article_title||'. '||event_text_segment, 800) FROM events
                             WHERE article_title = d.article_title LIMIT 1), d.article_title) AS doc,
                   (SELECT article_source FROM events
                    WHERE article_title = d.article_title LIMIT 1) AS source
            FROM disruption_candidates d
            WHERE d.is_risk_event AND d.strict_is_risk
        """)).fetchall()
    df = pd.DataFrame(rows, columns=["title", "article_id", "url", "date", "themes_json",
                                      "top_sim", "is_unrouted", "doc", "source"])
    df["date"] = pd.to_datetime(df["date"])
    df["themes"] = df["themes_json"].apply(lambda s: json.loads(s) if s else [])
    return df


def backfill_top_sim(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute top_sim/is_unrouted for rows with NULL top_sim (pre-P1 rows), write to DB."""
    import pickle

    from sentence_transformers import SentenceTransformer

    todo = df[df["top_sim"].isna()]
    if todo.empty:
        print("  backfill: nothing to do, all rows already have top_sim")
        return df

    print(f"  backfill: encoding {len(todo)} rows without top_sim …")
    with open(PROTO_PKL, "rb") as f:
        proto_bundle = pickle.load(f)
    protos = proto_bundle["protos"]  # [12, 384], L2-normalised

    enc = SentenceTransformer(ENCODER)
    embs = enc.encode(
        todo["doc"].tolist(), batch_size=64, normalize_embeddings=True,
        show_progress_bar=True, convert_to_numpy=True,
    )
    sims = embs @ protos.T          # [N, 12]
    top_sim = sims.max(axis=1)
    is_unrouted = top_sim < TAU_NOVEL

    df.loc[todo.index, "top_sim"] = top_sim
    df.loc[todo.index, "is_unrouted"] = is_unrouted

    engine = create_engine(DB_CONNECTION_STRING)
    with engine.begin() as conn:
        ensure_novelty_columns(conn)
        for i, idx in enumerate(todo.index):
            conn.execute(text("""
                UPDATE disruption_candidates
                SET top_sim = :top_sim, is_unrouted = :is_unrouted
                WHERE article_title = :title
            """), {
                "top_sim": float(top_sim[i]),
                "is_unrouted": bool(is_unrouted[i]),
                "title": todo.iloc[i]["title"],
            })
    print(f"  backfill: wrote top_sim/is_unrouted for {len(todo)} rows "
          f"({int(is_unrouted.sum())} unrouted, {int((~is_unrouted).sum())} routed)")
    return df


def retag_is_unrouted(tau: float = TAU_NOVEL) -> int:
    """Recompute is_unrouted for every row with a stored top_sim, against `tau`.

    Cheap (no re-encoding) — use this whenever TAU_NOVEL changes, instead of --backfill
    (which only fills rows that have never been encoded).
    """
    engine = create_engine(DB_CONNECTION_STRING)
    with engine.begin() as conn:
        ensure_novelty_columns(conn)
        result = conn.execute(text("""
            UPDATE disruption_candidates
            SET is_unrouted = (top_sim < :tau)
            WHERE top_sim IS NOT NULL
        """), {"tau": tau})
        n = result.rowcount
    print(f"  retag: is_unrouted recomputed for {n} rows at tau={tau}")
    return n


def tune_tau(df: pd.DataFrame) -> dict:
    """Empirical evidence for TAU_NOVEL: percentiles + histogram of top_sim (§7 tuning method).

    Writes data/emerging_tuning.json (for the thesis Accuracy page) and returns the summary.
    """
    s = df["top_sim"].dropna().to_numpy()
    percentiles = {p: round(float(np.percentile(s, p)), 4) for p in (1, 2, 5, 8, 10, 12, 15, 20, 25, 30, 40, 50)}
    counts, edges = np.histogram(s, bins=20)
    histogram = [
        {"lo": round(float(lo), 4), "hi": round(float(hi), 4), "count": int(c)}
        for c, lo, hi in zip(counts, edges[:-1], edges[1:])
    ]
    summary = {
        "task": "emerging_sectors_tau_tuning",
        "n": int(len(s)),
        "mean": round(float(s.mean()), 4),
        "std": round(float(s.std()), 4),
        "min": round(float(s.min()), 4),
        "max": round(float(s.max()), 4),
        "percentiles": percentiles,
        "histogram": histogram,
        "chosen_tau_novel": TAU_NOVEL,
        "n_below_chosen_tau": int((s < TAU_NOVEL).sum()),
        "note": ("No clean bimodal valley in top_sim; the historical 'clean' candidate corpus "
                 "was itself curated (LLM-classified or fallback-routed) against the 12 fixed "
                 "themes, so it is a poor ground truth for 'no theme fits'. TAU_NOVEL is set "
                 "near the p10-p12 breakpoint as a pragmatic historical-replay threshold, not a "
                 "principled separation boundary; see EMERGING_SECTORS_PLAN.md §7."),
    }
    os.makedirs("data", exist_ok=True)
    with open("data/emerging_tuning.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  tune-tau: wrote data/emerging_tuning.json "
          f"({summary['n_below_chosen_tau']}/{summary['n']} below chosen tau={TAU_NOVEL})")
    return summary


def novelty_pool(df: pd.DataFrame, as_of: pd.Timestamp | None, tau: float = TAU_NOVEL) -> pd.DataFrame:
    """Rows eligible for emerging-sector clustering as of a given date (§6 P2 definition).

    Filters on top_sim < tau directly (rather than the stored is_unrouted flag) so --tau can
    be overridden for exploration/tuning without needing to re-backfill the DB column.
    """
    pool = df[df["top_sim"] < tau]
    if as_of is not None:
        pool = pool[pool["date"] <= as_of]
    return pool


def topic_centroids(emb: np.ndarray, topics: np.ndarray) -> dict[int, np.ndarray]:
    """Mean L2-normalised embedding per real topic — used by P3's centroid matching."""
    centroids: dict[int, np.ndarray] = {}
    for tid in sorted(set(topics)):
        if tid == -1:
            continue
        member = emb[topics == tid]
        c = member.mean(axis=0)
        c = c / (np.linalg.norm(c) + 1e-12)
        centroids[int(tid)] = c
    return centroids


def encode_docs(docs: list[str]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    enc = SentenceTransformer(ENCODER)
    return enc.encode(docs, batch_size=64, normalize_embeddings=True,
                       show_progress_bar=len(docs) > 200, convert_to_numpy=True)


def cluster_pool(pool: pd.DataFrame, emb: np.ndarray | None = None):
    """MiniLM -> UMAP -> HDBSCAN -> c-TF-IDF over the novelty pool.

    Mirrors scripts.build_topic_model's approach so cluster labels/keywords are produced
    the same LLM-free way, but the min_cluster_size and UMAP neighborhood shrink for small
    pools (early as-of dates may have very few unrouted articles). Pass a precomputed `emb`
    (e.g. from encode_docs) to avoid re-encoding on every grid step (EMERGING_SECTORS_PLAN.md
    §8: "cache embeddings in-process across grid dates").
    """
    from bertopic import BERTopic
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    docs = pool["doc"].tolist()
    n_docs = len(docs)

    if emb is None:
        emb = encode_docs(docs)

    min_cluster = max(2, min(MIN_CLUSTER, n_docs // 3)) if n_docs < MIN_CLUSTER * 3 else MIN_CLUSTER
    n_neighbors = max(2, min(15, n_docs - 1))
    umap_model = UMAP(n_neighbors=n_neighbors, n_components=min(5, max(2, n_docs - 2)),
                       min_dist=0.0, metric="cosine", random_state=SEED)
    hdbscan_model = HDBSCAN(min_cluster_size=min_cluster, metric="euclidean",
                            cluster_selection_method="eom", prediction_data=True)
    vectorizer = CountVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    topic_model = BERTopic(umap_model=umap_model, hdbscan_model=hdbscan_model,
                           vectorizer_model=vectorizer, calculate_probabilities=False, verbose=False)
    topics, _ = topic_model.fit_transform(docs, embeddings=emb)

    if -1 in topics:
        try:
            topics = topic_model.reduce_outliers(docs, topics, strategy="embeddings", embeddings=emb)
            topic_model.update_topics(docs, topics=topics, vectorizer_model=vectorizer)
        except Exception as e:
            print(f"  (outlier reduction skipped: {e})")

    return topic_model, np.array(topics), emb


def summarize_pool(pool: pd.DataFrame, topic_model, topics: np.ndarray, as_of: pd.Timestamp) -> list[dict]:
    df = pool.copy()
    df["topic"] = topics
    real_topics = [t for t in sorted(set(topics)) if t != -1]
    n_outliers = int((topics == -1).sum())

    print(f"\nNovelty pool as of {as_of.date()}: {len(pool)} unrouted articles "
          f"-> {len(real_topics)} clusters (+{n_outliers} outliers)")
    print(f"{'id':>4} | {'size':>4} | first_seen  | keywords")

    rows = []
    for tid in real_topics:
        sub = df[df["topic"] == tid]
        kws = [w for w, _ in topic_model.get_topic(tid)[:6]]
        first_seen = sub["date"].min()
        rows.append({
            "cluster_tmp_id": int(tid),
            "size": int(len(sub)),
            "first_seen": str(first_seen.date()),
            "keywords": kws,
            "example": sub.iloc[0]["title"][:90],
            "sources": sorted(s for s in sub["source"].dropna().unique()),
        })
        print(f"{tid:>4} | {len(sub):>4} | {str(first_seen.date())} | {', '.join(kws[:6])}")
    return rows


def compute_velocity(
    member_dates: pd.Series, as_of: pd.Timestamp, n_windows: int = BASELINE_WEEKS + 1,
) -> tuple[list[int], int, float, float]:
    """Weekly counts of `member_dates` in the n_windows trailing 7-day buckets ending at as_of.

    Returns (velocity, n_recent, baseline_mean, baseline_std) where velocity[-1] == n_recent
    and velocity[:-1] is the baseline window (EMERGING_SECTORS_PLAN.md §6 P3 step 1-2).
    """
    counts: list[int] = []
    for i in range(n_windows, 0, -1):
        hi = as_of - pd.Timedelta(days=7 * (i - 1))
        lo = as_of - pd.Timedelta(days=7 * i)
        counts.append(int(((member_dates > lo) & (member_dates <= hi)).sum()))
    n_recent = counts[-1]
    baseline = counts[:-1]
    baseline_mean = float(np.mean(baseline)) if baseline else 0.0
    baseline_std = float(np.std(baseline)) if baseline else 0.0
    return counts, n_recent, baseline_mean, baseline_std


def match_or_create(registry: dict, centroid: np.ndarray, next_id: list[int]) -> str:
    """Carry a stable cluster_id across grid dates via nearest-centroid cosine match.

    EMERGING_SECTORS_PLAN.md §9 risk mitigation: cluster IDs from a fresh HDBSCAN fit are not
    stable across re-fits, so identity must be recovered by comparing centroids, not by index.
    """
    best_id, best_sim = None, -1.0
    for sid, reg in registry.items():
        sim = float(centroid @ reg["centroid"])
        if sim > best_sim:
            best_sim, best_id = sim, sid
    if best_id is not None and best_sim >= CENTROID_MATCH_THR:
        return best_id
    new_id = f"c_{next_id[0]:03d}"
    next_id[0] += 1
    registry[new_id] = {"centroid": centroid, "z_history": []}
    return new_id


def weekly_grid(df: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.date_range(df["date"].min(), df["date"].max(), freq=GRID_FREQ)


def run_grid(df: pd.DataFrame, tau: float = TAU_NOVEL) -> dict:
    """P3: replay the whole history on a weekly grid, tracking burst status per stable cluster.

    As-of correctness (§2 constraint 2): the pool for date D never includes rows dated after D.
    Performance (§8, strict-weekly default): embeddings for the full (latest-date) novelty pool
    are computed once, then sliced by date per grid step so only clustering re-runs.
    """
    full_pool = novelty_pool(df, as_of=None, tau=tau).reset_index(drop=True)
    if full_pool.empty:
        print("  grid: novelty pool is empty at this tau, nothing to do")
        return {"dates": {}}

    print(f"  grid: encoding {len(full_pool)} total unrouted articles once …")
    full_emb = encode_docs(full_pool["doc"].tolist())

    dates = weekly_grid(df)
    registry: dict[str, dict] = {}
    next_id = [0]
    timeline_dates: dict[str, dict] = {}

    for D in dates:
        mask = (full_pool["date"] <= D).to_numpy()
        n_avail = int(mask.sum())
        if n_avail < MIN_FOR_CLUSTERING:
            continue

        sub_pool = full_pool[mask].reset_index(drop=True)
        sub_emb = full_emb[mask]

        # as-of correctness gate — must hold on every single grid step, not just spot-checks.
        assert sub_pool.empty or sub_pool["date"].max() <= D, f"as-of leak at {D.date()}"

        topic_model, topics, emb = cluster_pool(sub_pool, emb=sub_emb)
        centroids = topic_centroids(emb, topics)
        sub_pool = sub_pool.copy()
        sub_pool["topic"] = topics

        clusters_out = []
        for tid, centroid in centroids.items():
            members = sub_pool[sub_pool["topic"] == tid]
            stable_id = match_or_create(registry, centroid, next_id)
            reg = registry[stable_id]
            reg["centroid"] = centroid
            if "first_seen" not in reg:
                reg["first_seen"] = str(members["date"].min().date())

            velocity, n_recent, baseline_mean, baseline_std = compute_velocity(members["date"], D)
            z = (n_recent - baseline_mean) / max(baseline_std, Z_STD_FLOOR)
            reg["z_history"].append((str(D.date()), z))

            recent_zs = [zz for _, zz in reg["z_history"][-SUSTAIN_WEEKS:]]
            is_bursting = len(recent_zs) >= SUSTAIN_WEEKS and all(zz >= Z_THRESH for zz in recent_zs)
            weeks_span = (D - pd.Timestamp(reg["first_seen"])).days / 7.0
            is_candidate = is_bursting and len(members) >= DURABILITY_K and weeks_span >= DURABILITY_WEEKS
            status = "candidate" if is_candidate else ("bursting" if is_bursting else "nascent")

            kws = [w for w, _ in topic_model.get_topic(tid)[:6]]
            clusters_out.append({
                "cluster_id": stable_id,
                "label": " ".join(kws[:4]),
                "keywords": kws,
                "status": status,
                "n_total": int(len(members)),
                "n_recent": int(n_recent),
                "z": round(float(z), 3),
                "velocity": velocity,
                "first_seen": reg["first_seen"],
                "example_titles": members["title"].head(3).tolist(),
            })

        timeline_dates[str(D.date())] = {"clusters": clusters_out}

    return {"dates": timeline_dates, "registry": registry}


def write_timeline(df: pd.DataFrame, tau: float = TAU_NOVEL) -> dict:
    import datetime as _dt

    result = run_grid(df, tau=tau)
    timeline = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "grid_freq": GRID_FREQ,
        "encoder": ENCODER,
        "params": {
            "tau_novel": tau, "z_thresh": Z_THRESH, "sustain_weeks": SUSTAIN_WEEKS,
            "min_cluster_size": MIN_CLUSTER, "durability_k": DURABILITY_K,
            "durability_weeks": DURABILITY_WEEKS,
        },
        "dates": result["dates"],
    }
    os.makedirs(os.path.dirname(TIMELINE_OUT), exist_ok=True)
    with open(TIMELINE_OUT, "w") as f:
        json.dump(timeline, f, indent=2)
    print(f"\n  grid: wrote {TIMELINE_OUT} ({len(result['dates'])} dates with clusterable pools, "
          f"{len(result['registry'])} distinct stable clusters discovered)")

    # Emergence ranking for the P6 replay demo (EMERGING_SECTORS_PLAN.md §6 P3):
    # rank stable clusters by peak historical z.
    ranked = sorted(
        result["registry"].items(),
        key=lambda kv: max((z for _, z in kv[1]["z_history"]), default=-1),
        reverse=True,
    )
    print("\n  Candidates for the P6 replay demo (ranked by peak z):")
    for sid, reg in ranked[:5]:
        peak_z = max((z for _, z in reg["z_history"]), default=0.0)
        print(f"    {sid}: peak_z={peak_z:.2f}  first_seen={reg.get('first_seen', '?')}  "
              f"weeks_tracked={len(reg['z_history'])}")
    return timeline


def main():
    ap = argparse.ArgumentParser(description="Emerging-sectors novelty-pool clustering (P2)")
    ap.add_argument("--backfill", action="store_true",
                     help="Backfill top_sim/is_unrouted for candidate rows that predate P1")
    ap.add_argument("--tune-tau", action="store_true",
                     help="Write data/emerging_tuning.json (percentiles/histogram of top_sim)")
    ap.add_argument("--retag", action="store_true",
                     help="Recompute is_unrouted for all rows against the current TAU_NOVEL "
                          "(cheap, no re-encoding) — run after changing TAU_NOVEL")
    ap.add_argument("--as-of", default=None,
                     help="Cluster the novelty pool as of this date (YYYY-MM-DD); default = latest")
    ap.add_argument("--tau", type=float, default=TAU_NOVEL,
                     help=f"Override TAU_NOVEL for this run only (default {TAU_NOVEL}); "
                          "exploration/tuning, does not change the stored is_unrouted flag")
    ap.add_argument("--grid", action="store_true",
                     help="Replay the full weekly grid with burst detection, write "
                          f"{TIMELINE_OUT} (P3)")
    args = ap.parse_args()

    df = load_clean_candidates()
    print(f"Loaded {len(df)} clean candidates "
          f"({int(df['top_sim'].notna().sum())} with top_sim, "
          f"{int(df['top_sim'].isna().sum())} pending backfill)")

    if args.backfill:
        df = backfill_top_sim(df)

    if args.tune_tau:
        tune_tau(df)

    if args.retag:
        retag_is_unrouted(TAU_NOVEL)
        df = load_clean_candidates()

    if args.grid:
        write_timeline(df, tau=args.tau)
        return

    as_of = pd.Timestamp(args.as_of) if args.as_of else df["date"].max()
    pool = novelty_pool(df, as_of, tau=args.tau)

    # as-of correctness gate (EMERGING_SECTORS_PLAN.md §2 constraint 2): the pool must never
    # contain rows dated after as_of.
    assert pool.empty or pool["date"].max() <= as_of, "as-of leak: pool contains rows after as_of"

    denom = int((df["date"] <= as_of).sum())
    print(f"\nAs-of {as_of.date()}: {len(pool)}/{denom} clean candidates up to that date are "
          f"unrouted (top_sim < {args.tau})")

    if len(pool) < MIN_FOR_CLUSTERING:
        print(f"  Too few unrouted articles to cluster yet "
              f"({len(pool)} < {MIN_FOR_CLUSTERING} minimum).")
        return

    topic_model, topics, emb = cluster_pool(pool)
    summarize_pool(pool, topic_model, topics, as_of)


if __name__ == "__main__":
    main()
