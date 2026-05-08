import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import ElasticNet, LogisticRegression
from sklearn.metrics import (
    classification_report,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder


DEFAULT_INPUT_CSVS = [
    "model_training/impact_label_pack_balanced.csv",
    "model_training/impact_label_pack_positive_boost.csv",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train two-stage impact models from manually labeled CSV."
    )
    parser.add_argument(
        "--input-csv",
        action="append",
        dest="input_csvs",
        default=None,
        help="Labeled CSV (repeat for multiple files). Default: balanced + positive_boost packs.",
    )
    parser.add_argument(
        "--classifier-out",
        default="model_training/disruption_classifier.pkl",
        help="Output path for disruption classifier artifact",
    )
    parser.add_argument(
        "--regressor-out",
        default="model_training/impact_regressor_v2.pkl",
        help="Output path for impact regressor artifact",
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
    csv_paths = (
        [Path(p) for p in args.input_csvs]
        if args.input_csvs
        else [Path(p) for p in DEFAULT_INPUT_CSVS]
    )
    df = load_labeled_frames(csv_paths)
    df = prepare_df(df)
    if len(df) < 40:
        raise ValueError("Not enough labeled rows for reliable training.")

    pos_count = int((df["manual_is_disruption"] == 1).sum())
    neg_count = int((df["manual_is_disruption"] == 0).sum())
    print(f"Training rows: {len(df)} (disruption=1: {pos_count}, disruption=0: {neg_count})")

    stratify_labels = (
        df["manual_is_disruption"]
        if pos_count >= 2 and neg_count >= 2
        else None
    )
    train_df, test_df = train_test_split(
        df,
        test_size=args.test_size,
        random_state=args.random_state,
        stratify=stratify_labels,
    )

    X_train, shared_artifacts = fit_shared_features(train_df)
    X_test = transform_shared_features(test_df, shared_artifacts)

    y_train_cls = train_df["manual_is_disruption"].values
    y_test_cls = test_df["manual_is_disruption"].values

    cls = LogisticRegression(max_iter=2000, class_weight="balanced")
    cls.fit(X_train, y_train_cls)
    cls_pred = cls.predict(X_test)
    cls_prob = cls.predict_proba(X_test)[:, 1]

    print("=== Disruption Classifier ===")
    print(classification_report(y_test_cls, cls_pred, digits=4))
    try:
        auc = roc_auc_score(y_test_cls, cls_prob)
        print(f"ROC-AUC: {auc:.4f}")
    except ValueError:
        print("ROC-AUC: unavailable (single-class test split)")

    y_train_reg = train_df["manual_impact_score"].values
    y_test_reg = test_df["manual_impact_score"].values

    # Include classifier probability as a model feature for stage-2 regression.
    train_prob = cls.predict_proba(X_train)[:, 1]
    test_prob = cls_prob
    X_train_reg = sparse.hstack([X_train, sparse.csr_matrix(train_prob[:, None])], format="csr")
    X_test_reg = sparse.hstack([X_test, sparse.csr_matrix(test_prob[:, None])], format="csr")

    reg = ElasticNet(alpha=0.001, l1_ratio=0.2, max_iter=5000, random_state=args.random_state)
    reg.fit(X_train_reg, y_train_reg)
    reg_pred = np.maximum(0.0, reg.predict(X_test_reg))

    mae = mean_absolute_error(y_test_reg, reg_pred)
    rmse = np.sqrt(mean_squared_error(y_test_reg, reg_pred))
    print("\n=== Impact Regressor ===")
    print(f"MAE: {mae:.4f}")
    print(f"RMSE: {rmse:.4f}")

    cls_out = Path(args.classifier_out)
    reg_out = Path(args.regressor_out)
    cls_out.parent.mkdir(parents=True, exist_ok=True)
    reg_out.parent.mkdir(parents=True, exist_ok=True)

    with cls_out.open("wb") as f:
        pickle.dump(
            {
                "model": cls,
                "artifacts": shared_artifacts,
                "target": "manual_is_disruption",
            },
            f,
        )

    with reg_out.open("wb") as f:
        pickle.dump(
            {
                "model": reg,
                "artifacts": shared_artifacts,
                "uses_disruption_probability_feature": True,
                "target": "manual_impact_score",
            },
            f,
        )

    print(f"\nSaved disruption classifier: {cls_out}")
    print(f"Saved impact regressor v2: {reg_out}")


if __name__ == "__main__":
    main()
