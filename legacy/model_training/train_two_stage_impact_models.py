from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    classification_report,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from tqdm import tqdm
from xgboost import XGBClassifier, XGBRegressor
from xgboost.callback import TrainingCallback


class TqdmProgressCallback(TrainingCallback):
    """XGBoost callback that drives a tqdm bar — one tick per boosting round."""

    def __init__(self, total: int, label: str):
        self._bar = tqdm(total=total, desc=label, unit="tree", dynamic_ncols=True)

    def after_iteration(self, model, epoch, evals_log):
        self._bar.update(1)
        return False  # False = keep training

    def after_training(self, model):
        self._bar.close()
        return model

_TRAIN_DIR = Path(__file__).resolve().parent
if str(_TRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(_TRAIN_DIR))
from rule_based_disruption_labels import apply_rule_labels_df

DEFAULT_INPUT_CSVS = [
    "model_training/impact_label_pack_balanced.csv",
    "model_training/impact_label_pack_positive_boost.csv",
]

DEFAULT_RULES_INPUT_CSVS = [
    "model_training/training_impact_dataset.csv",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train two-stage impact models: manual labels (default) or rule-based weak labels."
    )
    parser.add_argument(
        "--label-mode",
        choices=["manual", "rules"],
        default="manual",
        help="manual: CSV manual_is_disruption / manual_impact_score. "
        "rules: keyword buckets (rule_based_disruption_labels.py). "
        "rules defaults to *_rules.pkl outputs.",
    )
    parser.add_argument(
        "--input-csv",
        action="append",
        dest="input_csvs",
        default=None,
        help="CSV path(s).",
    )
    parser.add_argument(
        "--classifier-out",
        default=None,
        help="Disruption classifier pickle path",
    )
    parser.add_argument(
        "--regressor-out",
        default=None,
        help="Impact regressor pickle path",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Holdout fraction",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed",
    )
    return parser.parse_args()


def load_labeled_frames(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Input CSV not found: {p}")
        df = pd.read_csv(p)
        require_columns(
            df,
            [
                "article_title",
                "event_text_segment",
                "article_source",
                "matched_node",
                "manual_is_disruption",
                "manual_impact_score",
            ],
        )
        frames.append(df)
    merged = pd.concat(frames, ignore_index=True)
    if "event_id" in merged.columns:
        merged = merged.drop_duplicates(subset=["event_id"], keep="last")
    else:
        merged = merged.drop_duplicates(
            subset=["article_url", "article_title", "article_timestamp"],
            keep="last",
        )
    return merged


def load_rules_training_frames(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Input CSV not found: {p}")
        df = pd.read_csv(p)
        for col in ("article_title", "event_text_segment"):
            if col not in df.columns:
                raise ValueError(f"rules mode requires column {col!r} in {p}")
        for col in ("article_source", "matched_node"):
            if col not in df.columns:
                df[col] = ""
        frames.append(df)
    merged = pd.concat(frames, ignore_index=True)
    if "event_id" in merged.columns:
        merged = merged.drop_duplicates(subset=["event_id"], keep="last")
    elif "article_url" in merged.columns:
        merged = merged.drop_duplicates(
            subset=["article_url", "article_title", "article_timestamp"],
            keep="last",
        )
    return apply_rule_labels_df(merged)


def require_columns(df, cols):
    missing = sorted(set(cols) - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def prepare_df(df):
    df = df.copy()
    df["article_title"] = df["article_title"].fillna("").astype(str)
    df["event_text_segment"] = df["event_text_segment"].fillna("").astype(str)
    df["article_source"] = df["article_source"].fillna("").astype(str)
    df["matched_node"] = df["matched_node"].fillna("").astype(str)
    df["manual_is_disruption"] = pd.to_numeric(df["manual_is_disruption"], errors="coerce")
    df["manual_impact_score"] = pd.to_numeric(df["manual_impact_score"], errors="coerce")
    df = df.dropna(subset=["manual_is_disruption", "manual_impact_score"]).copy()
    df["manual_is_disruption"] = df["manual_is_disruption"].astype(int).clip(0, 1)
    df["manual_impact_score"] = df["manual_impact_score"].clip(lower=0, upper=300)
    return df


def resolve_output_paths(
    label_mode: str, classifier_out: Optional[str], regressor_out: Optional[str]
) -> Tuple[Path, Path]:
    root = Path(__file__).resolve().parent.parent
    if label_mode == "rules":
        c_default = root / "model_training" / "disruption_classifier_rules.pkl"
        r_default = root / "model_training" / "impact_regressor_v2_rules.pkl"
    else:
        c_default = root / "model_training" / "disruption_classifier.pkl"
        r_default = root / "model_training" / "impact_regressor_v2.pkl"
    return (
        Path(classifier_out) if classifier_out else c_default,
        Path(regressor_out) if regressor_out else r_default,
    )


def text_input(df):
    return (df["article_title"] + " " + df["event_text_segment"].str.slice(0, 700)).values


def fit_shared_features(train_df):
    text_vec = TfidfVectorizer(ngram_range=(1, 2), max_features=30000)
    X_text = text_vec.fit_transform(text_input(train_df))

    cat_cols = ["article_source", "matched_node"]
    cat_enc = OneHotEncoder(handle_unknown="ignore")
    X_cat = cat_enc.fit_transform(train_df[cat_cols])

    X = sparse.hstack([X_text, X_cat], format="csr")
    artifacts = {
        "text_vectorizer": text_vec,
        "cat_encoder": cat_enc,
        "categorical_cols": cat_cols,
    }
    return X, artifacts


def transform_shared_features(df, artifacts):
    X_text = artifacts["text_vectorizer"].transform(text_input(df))
    X_cat = artifacts["cat_encoder"].transform(df[artifacts["categorical_cols"]])
    return sparse.hstack([X_text, X_cat], format="csr")


def main():
    args = parse_args()
    project_root = Path(__file__).resolve().parent.parent

    if args.input_csvs:
        csv_paths = [
            project_root / p if not Path(p).is_absolute() else Path(p) for p in args.input_csvs
        ]
    elif args.label_mode == "rules":
        csv_paths = [project_root / p for p in DEFAULT_RULES_INPUT_CSVS]
        if not csv_paths[0].exists():
            raise FileNotFoundError(
                "rules mode: pass --input-csv or add "
                f"{DEFAULT_RULES_INPUT_CSVS[0]}"
            )
    else:
        csv_paths = [project_root / p for p in DEFAULT_INPUT_CSVS]

    if args.label_mode == "rules":
        df = load_rules_training_frames(csv_paths)
        print("Rule-based disruption_category distribution:")
        print(df["rule_disruption_category"].value_counts().to_string())
    else:
        df = load_labeled_frames(csv_paths)

    import time
    def _step(msg: str) -> float:
        print(f"\n[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
        return time.time()

    df = prepare_df(df)
    if len(df) < 40:
        raise ValueError("Not enough labeled rows for reliable training.")

    pos_count = int((df["manual_is_disruption"] == 1).sum())
    neg_count = int((df["manual_is_disruption"] == 0).sum())
    print(f"Training rows: {len(df)} (disruption=1: {pos_count}, disruption=0: {neg_count})")

    stratify_labels = (
        df["manual_is_disruption"] if pos_count >= 2 and neg_count >= 2 else None
    )
    train_df, test_df = train_test_split(
        df,
        test_size=args.test_size,
        random_state=args.random_state,
        stratify=stratify_labels,
    )
    print(f"  train={len(train_df)}  test={len(test_df)}", flush=True)

    _step("Step 1/4  Building TF-IDF + OHE features...")
    X_train, shared_artifacts = fit_shared_features(train_df)
    print(f"  feature matrix: {X_train.shape}", flush=True)
    X_test = transform_shared_features(test_df, shared_artifacts)

    y_train_cls = train_df["manual_is_disruption"].values
    y_test_cls = test_df["manual_is_disruption"].values

    pos = max(1, int((y_train_cls == 1).sum()))
    neg = max(1, int((y_train_cls == 0).sum()))
    scale_pos_weight = float(neg) / float(pos)

    _step("Step 2/4  Training disruption classifier (XGBoost, 200 trees)...")
    cls = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        random_state=args.random_state,
        n_jobs=-1,
        eval_metric="logloss",
        verbosity=0,
        callbacks=[TqdmProgressCallback(200, "Classifier")],
    )
    cls.fit(X_train, y_train_cls)
    cls_pred = cls.predict(X_test)
    cls_prob = cls.predict_proba(X_test)[:, 1]

    print("=== Disruption Classifier (XGBoost) ===")
    print(classification_report(y_test_cls, cls_pred, digits=4))
    try:
        auc = roc_auc_score(y_test_cls, cls_prob)
        print(f"ROC-AUC: {auc:.4f}")
    except ValueError:
        print("ROC-AUC: unavailable (single-class test split)")

    y_train_reg = train_df["manual_impact_score"].values
    y_test_reg = test_df["manual_impact_score"].values

    _step("Step 3/4  Appending disruption probability feature for regressor...")
    train_prob = cls.predict_proba(X_train)[:, 1]
    test_prob = cls_prob
    X_train_reg = sparse.hstack([X_train, sparse.csr_matrix(train_prob[:, None])], format="csr")
    X_test_reg = sparse.hstack([X_test, sparse.csr_matrix(test_prob[:, None])], format="csr")

    _step("Step 4/4  Training impact regressor (XGBoost, 200 trees)...")
    reg = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=args.random_state,
        n_jobs=-1,
        verbosity=0,
        callbacks=[TqdmProgressCallback(200, "Regressor ")],
    )
    reg.fit(X_train_reg, y_train_reg)
    reg_pred = np.maximum(0.0, reg.predict(X_test_reg))

    mae = mean_absolute_error(y_test_reg, reg_pred)
    rmse = np.sqrt(mean_squared_error(y_test_reg, reg_pred))
    print("\n=== Impact Regressor (XGBoost) ===")
    print(f"MAE: {mae:.4f}")
    print(f"RMSE: {rmse:.4f}")

    cls_out, reg_out = resolve_output_paths(
        args.label_mode, args.classifier_out, args.regressor_out
    )
    cls_out.parent.mkdir(parents=True, exist_ok=True)
    reg_out.parent.mkdir(parents=True, exist_ok=True)

    # Remove tqdm callbacks before pickling — they hold unpicklable file handles.
    cls.set_params(callbacks=None)
    reg.set_params(callbacks=None)

    cls_payload = {
        "model": cls,
        "artifacts": shared_artifacts,
        "target": "manual_is_disruption",
        "label_mode": args.label_mode,
    }
    reg_payload = {
        "model": reg,
        "artifacts": shared_artifacts,
        "uses_disruption_probability_feature": True,
        "target": "manual_impact_score",
        "label_mode": args.label_mode,
    }

    with cls_out.open("wb") as f:
        pickle.dump(cls_payload, f)

    with reg_out.open("wb") as f:
        pickle.dump(reg_payload, f)

    print(f"\nSaved disruption classifier: {cls_out}")
    print(f"Saved impact regressor v2: {reg_out}")
    if args.label_mode == "rules":
        print(
            "Rollback: use manual mode outputs disruption_classifier.pkl / impact_regressor_v2.pkl "
            "via DISRUPTION_CLASSIFIER_PATH / IMPACT_REGRESSOR_PATH."
        )


if __name__ == "__main__":
    main()
