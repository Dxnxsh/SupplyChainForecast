"""C (model improvement) — does a semantic embedding feature improve the predictor?

Adds a leakage-safe feature: cosine similarity between the rolling mean embedding of a target's
recent news (3d / 7d) and a "disruption prototype" (mean embedding of clean events BEFORE the
observation). Low-dimensional (2 features, not 384 raw dims) so it can't overfit 122 positives.

Compares base (16 no-dow features) vs base+semantic on BOTH the single split and walk-forward.
Honest ablation: a null result ("embeddings don't help the predictor") is a valid finding.

  prototype = mean emb of clean events with date < origin     (per-fold; no leakage)
  feature   = cos( rolling-3d/7d mean emb of target news ,  prototype )

Usage:
  venv311/bin/python -m scripts.train_predictor_embed
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics import roc_auc_score
from sqlalchemy import create_engine, text
from xgboost import XGBClassifier

from src.db_config import get_read_db_url
from scripts.train_predictor import (
    TARGETS, TARGET_KEYWORDS, FEATURES, BLOB, HORIZON,
    GRID_START, GRID_END, LOOKBACK_START, SPLIT_DATE, SEED, prf,
)

ENCODER = "sentence-transformers/all-MiniLM-L6-v2"
FEAT_BASE = [f for f in FEATURES if f not in ("dow", "is_weekend")]
REPORT_OUT = "data/predictor_embed_report.json"


def fit(train, feat):
    yf = train["label"].values
    spw = float((yf == 0).sum()) / float(max(1, (yf == 1).sum()))
    m = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                      colsample_bytree=0.8, scale_pos_weight=spw, min_child_weight=3,
                      random_state=SEED, n_jobs=-1, eval_metric="logloss", verbosity=0)
    m.fit(train[feat].values, yf)
    return m


def rolling_mean_emb(dates, vecs, full_idx, win):
    """Per-day weighted rolling mean embedding over `win` days, normalized. Returns (len(idx) x dim)."""
    dim = vecs.shape[1]
    day_sum = np.zeros((len(full_idx), dim))
    day_cnt = np.zeros(len(full_idx))
    pos = {d: i for i, d in enumerate(full_idx)}
    for d, v in zip(dates, vecs):
        i = pos.get(pd.Timestamp(d))
        if i is not None:
            day_sum[i] += v
            day_cnt[i] += 1
    cs = np.cumsum(day_sum, axis=0)
    cc = np.cumsum(day_cnt)
    roll_sum = cs - np.vstack([np.zeros((win, dim)), cs[:-win]])
    roll_cnt = cc - np.concatenate([np.zeros(win), cc[:-win]])
    mean = np.divide(roll_sum, roll_cnt[:, None], out=np.zeros_like(roll_sum), where=roll_cnt[:, None] > 0)
    n = np.linalg.norm(mean, axis=1, keepdims=True)
    return np.divide(mean, n, out=np.zeros_like(mean), where=n > 0)


def main():
    full_idx = pd.date_range(LOOKBACK_START, GRID_END, freq="D")
    df = pd.read_csv("data/predictor_dataset.csv", parse_dates=["obs_date"])
    print(f"loaded base dataset: {len(df)} rows, base features={len(FEAT_BASE)}")

    enc = SentenceTransformer(ENCODER)
    engine = create_engine(get_read_db_url())

    # clean-event embeddings + dates (for the prototype)
    with engine.connect() as conn:
        ce = conn.execute(text("""
            SELECT d.article_date,
                   COALESCE((SELECT LEFT(article_title||' '||event_text_segment,1200) FROM events
                             WHERE article_title=d.article_title LIMIT 1), d.article_title)
            FROM disruption_candidates d
            WHERE d.is_risk_event AND d.strict_is_risk AND d.article_date IS NOT NULL
        """)).fetchall()
    clean_dates = np.array([pd.Timestamp(r[0]) for r in ce])
    clean_emb = enc.encode([r[1] or "" for r in ce], normalize_embeddings=True, show_progress_bar=False)
    print(f"embedded {len(clean_emb)} clean-event texts")

    # per-target rolling mean embeddings aligned to df rows
    M3 = np.zeros((len(df), clean_emb.shape[1]))
    M7 = np.zeros((len(df), clean_emb.shape[1]))
    for name in TARGETS:
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT article_timestamp::date d, LEFT(article_title||' '||event_text_segment,1200) t
                FROM events
                WHERE article_timestamp::date BETWEEN :a AND :b AND {BLOB} ~ :kw
            """), {"a": LOOKBACK_START, "b": GRID_END, "kw": TARGET_KEYWORDS[name]}).fetchall()
        if not rows:
            continue
        vecs = enc.encode([r[1] or "" for r in rows], batch_size=128, normalize_embeddings=True, show_progress_bar=False)
        dates = [r[0] for r in rows]
        r3 = rolling_mean_emb(dates, vecs, full_idx, 3)
        r7 = rolling_mean_emb(dates, vecs, full_idx, 7)
        idxpos = {d: i for i, d in enumerate(full_idx)}
        sel = df.index[df["target"] == name]
        for i in sel:
            j = idxpos.get(df.at[i, "obs_date"])
            if j is not None:
                M3[i] = r3[j]
                M7[i] = r7[j]
        print(f"  embedded {len(rows):>5} articles for {name}")

    def sem_feats(proto):
        p = proto / (np.linalg.norm(proto) + 1e-9)
        return M3 @ p, M7 @ p

    # ---- single split ----
    proto = clean_emb[clean_dates < pd.Timestamp(SPLIT_DATE)].mean(axis=0)
    s3, s7 = sem_feats(proto)
    df2 = df.copy()
    df2["sem_sim_3d"], df2["sem_sim_7d"] = s3, s7
    FEAT_SEM = FEAT_BASE + ["sem_sim_3d", "sem_sim_7d"]

    tr, te = df2[df2.obs_date < SPLIT_DATE], df2[df2.obs_date >= SPLIT_DATE]
    auc_base = roc_auc_score(te["label"], fit(tr, FEAT_BASE).predict_proba(te[FEAT_BASE].values)[:, 1])
    m_sem = fit(tr, FEAT_SEM)
    auc_sem = roc_auc_score(te["label"], m_sem.predict_proba(te[FEAT_SEM].values)[:, 1])
    imp = dict(zip(FEAT_SEM, m_sem.feature_importances_.tolist()))
    print(f"\n[single split] AUC base={auc_base:.3f}  base+sem={auc_sem:.3f}  (delta {auc_sem-auc_base:+.3f})")
    print(f"  sem feature importance: sem_sim_3d={imp['sem_sim_3d']:.3f} sem_sim_7d={imp['sem_sim_7d']:.3f}")

    # ---- walk-forward (per-fold prototype: clean events before origin) ----
    cutoff = pd.Timestamp(GRID_END) - pd.Timedelta(days=HORIZON[1])
    dff = df[df.obs_date <= cutoff].reset_index(drop=True)
    M3f, M7f = M3[df.obs_date <= cutoff], M7[df.obs_date <= cutoff]
    origins = pd.date_range("2025-08-01", "2026-05-01", freq="MS")
    fb, fs = [], []
    print("[walk-forward] per-fold AUC base vs base+sem:")
    for O in origins:
        end = O + pd.offsets.MonthBegin(1)
        trm = (dff.obs_date < O).values
        tem = ((dff.obs_date >= O) & (dff.obs_date < end)).values
        if dff[trm]["label"].sum() < 20 or dff[tem]["label"].sum() < 3 or dff[tem]["label"].nunique() < 2:
            continue
        proto_O = clean_emb[clean_dates < O].mean(axis=0)
        pn = proto_O / (np.linalg.norm(proto_O) + 1e-9)
        s3f, s7f = M3f @ pn, M7f @ pn
        d = dff.copy()
        d["sem_sim_3d"], d["sem_sim_7d"] = s3f, s7f
        tr_, te_ = d[trm], d[tem]
        ab = roc_auc_score(te_["label"], fit(tr_, FEAT_BASE).predict_proba(te_[FEAT_BASE].values)[:, 1])
        asem = roc_auc_score(te_["label"], fit(tr_, FEAT_SEM).predict_proba(te_[FEAT_SEM].values)[:, 1])
        fb.append(ab); fs.append(asem)
        print(f"    {O.strftime('%Y-%m')}  base={ab:.2f}  base+sem={asem:.2f}  ({asem-ab:+.2f})")

    mb, ms = float(np.mean(fb)), float(np.mean(fs))
    print(f"\n  walk-forward mean AUC: base={mb:.3f}  base+sem={ms:.3f}  (delta {ms-mb:+.3f})")
    verdict = ("embeddings HELP the predictor" if ms - mb > 0.01
               else "embeddings do NOT meaningfully help the predictor")
    print(f"  VERDICT: {verdict}")

    out = {"task": "predictor_embedding_ablation", "encoder": ENCODER,
           "single_split": {"auc_base": round(auc_base, 4), "auc_base_plus_sem": round(auc_sem, 4),
                            "delta": round(auc_sem - auc_base, 4), "sem_importance": {k: round(imp[k], 4) for k in ("sem_sim_3d", "sem_sim_7d")}},
           "walk_forward": {"mean_auc_base": round(mb, 4), "mean_auc_base_plus_sem": round(ms, 4),
                            "delta": round(ms - mb, 4), "n_folds": len(fb)},
           "verdict": verdict}
    os.makedirs("data", exist_ok=True)
    with open(REPORT_OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved -> {REPORT_OUT}")


if __name__ == "__main__":
    main()
