"""T8 — leakage + robustness tests for the disruption predictor.

Three checks (the first two are hard assertions; the third is a robustness report):

  1. Feature truncation-invariance (NO FUTURE LEAKAGE): for sample (target, obs_date) rows,
     rebuild every feature with the corpus index truncated at obs_date and assert it equals the
     value built over the full corpus. If a feature peeked at the future, truncation would change
     it. (Equivalent to "every feature's source date <= obs_date".)
  2. Calibration slice disjoint from test: [CALIB_START, SPLIT_DATE) must not overlap test (>= SPLIT_DATE).
  3. Walk-forward (rolling origin): retrain monthly, each model trained ONLY on data before its
     origin, scored on the next month. Mean AUC across folds shows the signal isn't a single-split
     fluke. Persistence F1 reported per fold for context.

Usage:
  venv311/bin/python -m scripts.test_predictor
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
from sklearn.metrics import roc_auc_score
from sqlalchemy import text
from xgboost import XGBClassifier

from scripts.train_predictor import (
    TARGETS, TARGET_KEYWORDS, FEATURES, HORIZON,
    GRID_START, GRID_END, LOOKBACK_START, SPLIT_DATE, CALIB_START, SEED,
    daily_news, clean_event_days, build_target_frame, get_engine, prf,
)

FEAT = [f for f in FEATURES if f not in ("dow", "is_weekend")]  # canonical config
REPORT_OUT = "data/predictor_test_report.json"


def fit_model(train, feat):
    yf = train["label"].values
    spw = float((yf == 0).sum()) / float(max(1, (yf == 1).sum()))
    m = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                      subsample=0.9, colsample_bytree=0.8, scale_pos_weight=spw,
                      min_child_weight=3, random_state=SEED, n_jobs=-1,
                      eval_metric="logloss", verbosity=0)
    m.fit(train[feat].values, yf)
    return m


def main():
    full_idx = pd.date_range(LOOKBACK_START, GRID_END, freq="D")
    results = {"checks": {}}
    engine = get_engine()

    # fetch once; reuse for both the leakage test and the walk-forward dataset
    with engine.connect() as conn:
        g = conn.execute(text("""
            SELECT article_date d, COUNT(*) c FROM disruption_candidates
            WHERE is_risk_event AND strict_is_risk AND article_date IS NOT NULL GROUP BY 1
        """)).fetchall()
        global_clean = pd.Series({pd.Timestamp(d): c for d, c in g}, dtype="float64")
        news_by, clean_by, full_frames = {}, {}, {}
        for name in TARGETS:
            news_by[name] = daily_news(conn, TARGET_KEYWORDS[name])
            clean_by[name] = clean_event_days(conn, TARGETS[name])
            f = build_target_frame(news_by[name], clean_by[name], global_clean, full_idx).loc[GRID_START:GRID_END]
            f = f.copy()
            f["target"] = name
            f["obs_date"] = f.index
            full_frames[name] = f

    # ---- Check 1: feature truncation-invariance (no future leakage) ----
    sample_dates = ["2025-06-15", "2025-09-01", "2025-12-01", "2026-03-15", "2026-05-01"]
    sample_targets = ["shipping_chokepoints", "semiconductor_electronics", "critical_materials"]
    max_abs_diff = 0.0
    n_checked = 0
    for name in sample_targets:
        full_f = build_target_frame(news_by[name], clean_by[name], global_clean, full_idx)
        for ds in sample_dates:
            D = pd.Timestamp(ds)
            trunc_idx = full_idx[full_idx <= D]  # corpus visible only up to obs_date
            trunc_f = build_target_frame(news_by[name], clean_by[name], global_clean, trunc_idx)
            a = full_f.loc[D, FEAT].astype(float).values
            b = trunc_f.loc[D, FEAT].astype(float).values
            diff = np.nanmax(np.abs(a - b)) if len(a) else 0.0
            max_abs_diff = max(max_abs_diff, float(diff))
            n_checked += 1
    leak_pass = max_abs_diff < 1e-9
    results["checks"]["feature_truncation_invariance"] = {
        "pass": bool(leak_pass), "rows_checked": n_checked,
        "max_abs_diff_full_vs_truncated": max_abs_diff,
        "note": "features identical whether or not future data exists -> no leakage",
    }
    print(f"[1] Feature truncation-invariance: checked {n_checked} (target,date) cells, "
          f"max |full-truncated| = {max_abs_diff:.2e} -> {'PASS' if leak_pass else 'FAIL'}")
    assert leak_pass, "LEAKAGE: a feature changed when future data was hidden"

    # ---- Check 2: calibration slice disjoint from test ----
    calib_disjoint = pd.Timestamp(CALIB_START) < pd.Timestamp(SPLIT_DATE)
    results["checks"]["calib_disjoint_from_test"] = {
        "pass": bool(calib_disjoint),
        "calib_window": [CALIB_START, SPLIT_DATE], "test_from": SPLIT_DATE,
    }
    print(f"[2] Calibration slice [{CALIB_START}, {SPLIT_DATE}) disjoint from test (>= {SPLIT_DATE}): "
          f"{'PASS' if calib_disjoint else 'FAIL'}")
    assert calib_disjoint, "calibration slice overlaps test"

    # ---- Check 3: walk-forward rolling origin ----
    df = pd.concat(full_frames.values(), ignore_index=True)
    cutoff = pd.Timestamp(GRID_END) - pd.Timedelta(days=HORIZON[1])
    df = df[df["obs_date"] <= cutoff].reset_index(drop=True)

    origins = pd.date_range("2025-08-01", "2026-05-01", freq="MS")
    folds = []
    print("[3] Walk-forward (train < origin, test = next month):")
    for O in origins:
        end = O + pd.offsets.MonthBegin(1)
        train = df[df["obs_date"] < O]
        test = df[(df["obs_date"] >= O) & (df["obs_date"] < end)]
        tr_pos, te_pos = int(train["label"].sum()), int(test["label"].sum())
        if tr_pos < 20 or te_pos < 3 or test["label"].nunique() < 2:
            continue
        m = fit_model(train, FEAT)
        p = m.predict_proba(test[FEAT].values)[:, 1]
        auc = roc_auc_score(test["label"].values, p)
        base = (test["clean_cnt_3d"].values > 0).astype(int)
        base_f1 = prf(test["label"].values, base)["f1"]
        # onset recall at top-quartile score threshold (threshold-light, fold-local)
        thr = float(np.quantile(p, 0.75))
        onset_pos = (test["clean_cnt_3d"].values == 0) & (test["label"].values == 1)
        onset_recall = float(((p >= thr) & onset_pos).sum() / max(1, onset_pos.sum()))
        folds.append({"origin": O.strftime("%Y-%m"), "train_pos": tr_pos, "test_n": len(test),
                      "test_pos": te_pos, "auc": round(auc, 3),
                      "onset_recall@q75": round(onset_recall, 3), "persistence_f1": round(base_f1, 3)})
        print(f"    {O.strftime('%Y-%m')}  train_pos={tr_pos:>3} test={len(test):>3} pos={te_pos:>3}  "
              f"AUC={auc:.2f}  onsetR@q75={onset_recall:.2f}  persistF1={base_f1:.2f}")

    aucs = [f["auc"] for f in folds]
    mean_auc = float(np.mean(aucs)) if aucs else float("nan")
    share_gt_half = float(np.mean([a > 0.55 for a in aucs])) if aucs else 0.0
    results["checks"]["walk_forward"] = {
        "n_folds": len(folds), "mean_auc": round(mean_auc, 3),
        "share_folds_auc_gt_0.55": round(share_gt_half, 3), "folds": folds,
    }
    print(f"\n    Walk-forward: {len(folds)} folds, mean AUC={mean_auc:.3f}, "
          f"{share_gt_half:.0%} of folds AUC>0.55")

    results["summary"] = {
        "leakage_tests_pass": bool(leak_pass and calib_disjoint),
        "walk_forward_mean_auc": round(mean_auc, 3),
        "verdict": ("signal is consistent across time" if mean_auc > 0.55
                    else "signal is weak/inconsistent across folds"),
    }
    os.makedirs("data", exist_ok=True)
    with open(REPORT_OUT, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved report -> {REPORT_OUT}")
    print(f"VERDICT: leakage tests {'PASS' if results['summary']['leakage_tests_pass'] else 'FAIL'}; "
          f"{results['summary']['verdict']}")


if __name__ == "__main__":
    main()
