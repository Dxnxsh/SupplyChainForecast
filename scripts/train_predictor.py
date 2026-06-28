"""T7 — disruption predictor: P(disruption in next 1-3 days) per target.

Pooled, calibrated gradient-boosted classifier over the 5 consolidated targets (§4).
Builds a (target, obs_date) feature grid from the RAW news stream + clean events, with
EVERY feature computed from data with date <= obs_date (no leakage), labels from the
1-3 day horizon. Temporal split keeps the 2026-03 spike entirely in test.

  features (<= obs_date)  -->  XGBoost  -->  isotonic/Platt calibration  -->  P(disruption next 1-3d)

Honest eval vs a persistence baseline ("disruption in last 3d -> predict disruption").

Outputs:
  model_training/predictor.pkl     (vectorizer-free: vec=None; (model, calibrator, FEATURES))  [gitignored]
  data/predictor_metrics.json      (Brier / AUC / P-R-F1, per-target counts)  [tracked]
  data/predictor_dataset.csv       (the feature grid, for audit / SHAP / UI)   [tracked]

Usage:
  venv311/bin/python -m scripts.train_predictor
"""

from __future__ import annotations

import json
import os
import pickle
import sys

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_recall_fscore_support, roc_auc_score
from sqlalchemy import create_engine, text
from xgboost import XGBClassifier

from src.db_config import get_read_db_url
from scripts.build_disruption_dataset import BLOB, CANDIDATE_RE

# --- the 5 consolidated targets (§4): name -> exact cascade theme names ---
TARGETS = {
    "shipping_chokepoints": ["Strait of Hormuz / Gulf shipping", "Red Sea / Suez shipping"],
    "semiconductor_electronics": ["Taiwan semiconductors", "China electronics manufacturing",
                                  "South Korea memory chips", "Japan electronic components",
                                  "Global semiconductor supply"],
    "european_auto": ["European auto supply chain"],
    "critical_materials": ["Lithium & battery materials", "Rare earths & export controls"],
    "us_logistics": ["US West Coast ports", "US freight & trucking"],
}

# Topical keyword regex per target — slices the RAW 180k corpus into each target's news stream.
TARGET_KEYWORDS = {
    "shipping_chokepoints": r"red sea|suez|hormuz|strait of|houthi|bab[- ]el[- ]mandeb|gulf of aden|"
                            r"tanker|container ship|shipping lane|maritime|cargo ship|freight rate",
    "semiconductor_electronics": r"semiconductor|\mchip|chips|wafer|foundry|tsmc|chipmaker|"
                                 r"memory chip|electronics manufactur|foxconn|\mfab\M",
    "european_auto": r"automaker|carmaker|car maker|automotive|vehicle production|car plant|"
                     r"auto parts|auto supplier|volkswagen|stellantis",
    "critical_materials": r"lithium|rare earth|cobalt|battery material|graphite|export control|"
                          r"export ban|critical mineral|neodymium",
    "us_logistics": r"port of los angeles|long beach|west coast port|trucking|freight rail|"
                    r"teamster|longshore|intermodal|cargo backlog",
}

GRID_START = "2025-01-01"
GRID_END = "2026-06-27"
LOOKBACK_START = "2024-12-01"   # 14d+ runway before grid for window features
HORIZON = (1, 3)                # positive if a clean event lands in [obs+1, obs+3]
SPLIT_DATE = "2026-02-01"       # test = obs_date >= this (keeps 2026-03 spike in test)
CALIB_START = "2026-01-01"      # disjoint calibration slice: [CALIB_START, SPLIT_DATE)

MODEL_OUT = "model_training/predictor.pkl"
METRICS_OUT = "data/predictor_metrics.json"
DATASET_OUT = "data/predictor_dataset.csv"
SEED = 42


def get_engine():
    return create_engine(get_read_db_url())


def daily_news(conn, kw_regex):
    """Per-day topical aggregates from the RAW corpus for one target's keyword stream."""
    q = text(f"""
        SELECT article_timestamp::date AS d,
               COUNT(*) AS cnt,
               AVG(sentiment_score)::float AS smean,
               MIN(sentiment_score)::float AS smin,
               SUM(CASE WHEN {BLOB} ~ :cand THEN 1 ELSE 0 END) AS hits
        FROM events
        WHERE article_timestamp::date BETWEEN :a AND :b
          AND {BLOB} ~ :kw
        GROUP BY 1 ORDER BY 1
    """)
    rows = conn.execute(q, {"cand": CANDIDATE_RE, "kw": kw_regex, "a": LOOKBACK_START, "b": GRID_END}).fetchall()
    df = pd.DataFrame(rows, columns=["d", "cnt", "smean", "smin", "hits"])
    df["d"] = pd.to_datetime(df["d"])
    return df.set_index("d")


def clean_event_days(conn, themes):
    """Per-day count of CLEAN disruption events whose themes belong to this target."""
    q = text("""
        SELECT article_date AS d, COUNT(*) AS c
        FROM disruption_candidates
        WHERE is_risk_event AND strict_is_risk AND article_date IS NOT NULL
          AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(themes) t WHERE t = ANY(:arr))
        GROUP BY 1 ORDER BY 1
    """)
    rows = conn.execute(q, {"arr": themes}).fetchall()
    s = pd.Series({pd.Timestamp(d): c for d, c in rows}, dtype="float64")
    return s


def build_target_frame(news, clean, global_clean, idx):
    """Reindex to daily grid and compute leakage-safe rolling features (window ends at obs_date)."""
    n = news.reindex(idx)
    cnt = n["cnt"].fillna(0.0)
    smean = n["smean"]
    smin = n["smin"]
    hits = n["hits"].fillna(0.0)
    sent_sum = (smean * cnt)  # weighted-mean numerator; NaN where no articles

    clean_d = clean.reindex(idx).fillna(0.0)
    gclean = global_clean.reindex(idx).fillna(0.0)

    def wmean(win):
        num = sent_sum.rolling(win, min_periods=1).sum()
        den = cnt.rolling(win, min_periods=1).sum()
        return (num / den).where(den > 0)

    f = pd.DataFrame(index=idx)
    f["vol_1d"] = cnt.rolling(1).sum()
    f["vol_3d"] = cnt.rolling(3, min_periods=1).sum()
    f["vol_7d"] = cnt.rolling(7, min_periods=1).sum()
    f["vol_14d"] = cnt.rolling(14, min_periods=1).sum()
    f["sent_mean_3d"] = wmean(3)
    f["sent_mean_7d"] = wmean(7)
    f["sent_min_3d"] = smin.rolling(3, min_periods=1).min()
    f["sent_min_7d"] = smin.rolling(7, min_periods=1).min()
    prior3 = (sent_sum.shift(3).rolling(3, min_periods=1).sum() /
              cnt.shift(3).rolling(3, min_periods=1).sum())
    f["sent_delta_3d"] = f["sent_mean_3d"] - prior3
    f["kw_hits_1d"] = hits.rolling(1).sum()
    f["kw_hits_3d"] = hits.rolling(3, min_periods=1).sum()
    f["clean_cnt_3d"] = clean_d.rolling(3, min_periods=1).sum()
    f["clean_cnt_7d"] = clean_d.rolling(7, min_periods=1).sum()
    f["clean_cnt_14d"] = clean_d.rolling(14, min_periods=1).sum()
    # days since last clean event (<= obs_date)
    last_event = pd.Series(np.where(clean_d.values > 0, np.arange(len(idx)), np.nan), index=idx).ffill()
    f["days_since_clean"] = (np.arange(len(idx)) - last_event).fillna(999).clip(upper=999)
    f["cross_clean_3d"] = gclean.rolling(3, min_periods=1).sum()
    f["dow"] = idx.dayofweek
    f["is_weekend"] = (idx.dayofweek >= 5).astype(int)

    # label: clean event in [obs+1, obs+3]
    fwd = sum(clean_d.shift(-k) for k in range(HORIZON[0], HORIZON[1] + 1))
    f["label"] = (fwd > 0).astype(int)
    return f


FEATURES = ["vol_1d", "vol_3d", "vol_7d", "vol_14d", "sent_mean_3d", "sent_mean_7d",
            "sent_min_3d", "sent_min_7d", "sent_delta_3d", "kw_hits_1d", "kw_hits_3d",
            "clean_cnt_3d", "clean_cnt_7d", "clean_cnt_14d", "days_since_clean",
            "cross_clean_3d", "dow", "is_weekend"]


def prf(y, p):
    pr, rc, f1, _ = precision_recall_fscore_support(y, p, average="binary", zero_division=0)
    return {"precision": round(pr, 4), "recall": round(rc, 4), "f1": round(f1, 4)}


def main():
    full_idx = pd.date_range(LOOKBACK_START, GRID_END, freq="D")
    engine = get_engine()
    with engine.connect() as conn:
        # global clean-event daily counts (all targets) for the cross-target feature
        g = conn.execute(text("""
            SELECT article_date d, COUNT(*) c FROM disruption_candidates
            WHERE is_risk_event AND strict_is_risk AND article_date IS NOT NULL GROUP BY 1
        """)).fetchall()
        global_clean = pd.Series({pd.Timestamp(d): c for d, c in g}, dtype="float64")

        frames = []
        for name, themes in TARGETS.items():
            news = daily_news(conn, TARGET_KEYWORDS[name])
            clean = clean_event_days(conn, themes)
            f = build_target_frame(news, clean, global_clean, full_idx)
            f = f.loc[GRID_START:GRID_END].copy()
            f["target"] = name
            f["obs_date"] = f.index
            frames.append(f)
            print(f"  {name:<26} topical-days={len(news):>4}  clean-event-days={int((clean>0).sum()):>3}  positives(grid)={int(f['label'].sum()):>3}")

    df = pd.concat(frames, ignore_index=True)
    # drop the last HORIZON days where the forward label is truncated
    cutoff = pd.Timestamp(GRID_END) - pd.Timedelta(days=HORIZON[1])
    df = df[df["obs_date"] <= cutoff].reset_index(drop=True)

    train = df[df["obs_date"] < SPLIT_DATE]
    test = df[df["obs_date"] >= SPLIT_DATE]
    fit = train[train["obs_date"] < CALIB_START]
    calib = train[train["obs_date"] >= CALIB_START]
    print(f"\nrows: total={len(df)} train={len(train)} (fit={len(fit)} calib={len(calib)}) test={len(test)}")
    print(f"positives: train={int(train['label'].sum())} test={int(test['label'].sum())}")

    Xf, yf = fit[FEATURES].values, fit["label"].values
    spw = float((yf == 0).sum()) / float(max(1, (yf == 1).sum()))
    model = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                          subsample=0.9, colsample_bytree=0.8, scale_pos_weight=spw,
                          min_child_weight=3, random_state=SEED, n_jobs=-1,
                          eval_metric="logloss", verbosity=0)
    model.fit(Xf, yf)

    # calibrate on the disjoint Jan-2026 slice (Platt if isotonic too sparse)
    raw_calib = model.predict_proba(calib[FEATURES].values)[:, 1]
    if int(calib["label"].sum()) >= 8:
        cal = IsotonicRegression(out_of_bounds="clip").fit(raw_calib, calib["label"].values)
        cal_kind = "isotonic"
        calibrate = lambda p: cal.predict(p)
    else:
        cal = LogisticRegression().fit(raw_calib.reshape(-1, 1), calib["label"].values)
        cal_kind = "platt"
        calibrate = lambda p: cal.predict_proba(p.reshape(-1, 1))[:, 1]

    # operating threshold chosen on the disjoint calib slice (NOT test) by best F1
    p_calib = np.clip(calibrate(raw_calib), 0, 1)
    grid = np.linspace(0.05, 0.9, 86)
    yc = calib["label"].values
    op_thr = float(max(grid, key=lambda t: prf(yc, (p_calib >= t).astype(int))["f1"]))

    # ---- evaluate on held-out test (>= 2026-02-01, includes the 2026-03 spike) ----
    raw_test = model.predict_proba(test[FEATURES].values)[:, 1]
    p_test = np.clip(calibrate(raw_test), 0, 1)
    y_test = test["label"].values
    pred_op = (p_test >= op_thr).astype(int)

    brier = brier_score_loss(y_test, p_test)
    auc = roc_auc_score(y_test, p_test) if len(set(y_test)) > 1 else float("nan")
    clf_prf = prf(y_test, pred_op)

    # persistence baseline: clean event in last 3d -> predict disruption
    base_pred = (test["clean_cnt_3d"].values > 0).astype(int)
    base_brier = brier_score_loss(y_test, base_pred)  # 0/1 "probabilities"
    base_prf = prf(y_test, base_pred)

    # ONSET value-add: positives with NO clean event in the prior 3d (persistence recall = 0 here)
    onset_mask = test["clean_cnt_3d"].values == 0
    onset_pos = onset_mask & (y_test == 1)
    n_onset_pos = int(onset_pos.sum())
    onset_caught = int(((p_test >= op_thr) & onset_pos).sum())
    onset_flagged = int(((p_test >= op_thr) & onset_mask).sum())
    onset = {
        "onset_positives": n_onset_pos,
        "persistence_recall": 0.0,  # blind by construction
        "predictor_recall": round(onset_caught / n_onset_pos, 4) if n_onset_pos else None,
        "predictor_precision": round(onset_caught / onset_flagged, 4) if onset_flagged else None,
        "caught": onset_caught, "flagged": onset_flagged,
    }
    print(f"\n  ONSET (new disruptions, no event in prior 3d; persistence recall=0):")
    print(f"    predictor catches {onset_caught}/{n_onset_pos} ({onset['predictor_recall']:.0%} recall, {onset['predictor_precision']:.0%} precision)")

    beats = brier < base_brier
    base_rate = float(y_test.mean())
    print(f"\n=== Predictor eval on held-out test (n={len(y_test)}, positives={int(y_test.sum())}, base rate={base_rate:.0%}) ===")
    print(f"  predictor   : Brier={brier:.3f}  AUC={auc:.3f}  P={clf_prf['precision']:.0%} R={clf_prf['recall']:.0%} F1={clf_prf['f1']:.0%}  (op_thr={op_thr:.2f}, calib={cal_kind})")
    print(f"  persistence : Brier={base_brier:.3f}            P={base_prf['precision']:.0%} R={base_prf['recall']:.0%} F1={base_prf['f1']:.0%}")
    print(f"\n  ACCEPTANCE (predictor Brier < persistence Brier): {'PASS' if beats else 'FAIL'}")
    print(f"  (predictor F1 vs persistence F1: {clf_prf['f1']:.0%} vs {base_prf['f1']:.0%})")

    # leakage guard: every feature window ends at obs_date (built via rolling, no shift(-) except label)
    assert "label" not in FEATURES, "label leaked into features"

    per_target = {t: {"train_pos": int(train[train.target == t]["label"].sum()),
                      "test_pos": int(test[test.target == t]["label"].sum())} for t in TARGETS}
    importances = dict(sorted(zip(FEATURES, model.feature_importances_.tolist()),
                              key=lambda kv: kv[1], reverse=True))

    os.makedirs("model_training", exist_ok=True)
    with open(MODEL_OUT, "wb") as f:
        pickle.dump({"model": model, "calibrator": cal, "cal_kind": cal_kind, "features": FEATURES}, f)
    df.to_csv(DATASET_OUT, index=False)
    metrics = {
        "task": "disruption_predictor",
        "horizon_days": list(HORIZON), "split_date": SPLIT_DATE,
        "n_total": len(df), "n_train": len(train), "n_test": len(test),
        "test_positives": int(y_test.sum()), "test_base_rate": round(base_rate, 4),
        "predictor": {"brier": round(brier, 4), "auc": round(auc, 4), **clf_prf,
                      "operating_threshold": round(op_thr, 3), "calibration": cal_kind},
        "persistence_baseline": {"brier": round(base_brier, 4), **base_prf},
        "beats_persistence_brier": bool(beats),
        "onset_value_add": onset,
        "per_target": per_target,
        "feature_importance": {k: round(v, 4) for k, v in importances.items()},
    }
    with open(METRICS_OUT, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nSaved model -> {MODEL_OUT}\nSaved metrics -> {METRICS_OUT}\nSaved dataset -> {DATASET_OUT}")


if __name__ == "__main__":
    main()
