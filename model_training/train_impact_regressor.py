import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train impact regression model from training_impact_dataset.csv"
    )
    parser.add_argument(
        "--input-csv",
        default="model_training/training_impact_dataset.csv",
        help="Training dataset built by build_impact_dataset.py",
    )
    parser.add_argument(
        "--output-model",
        default="model_training/impact_regressor.pkl",
        help="Path to persist trained regressor artifacts",
    )
    parser.add_argument(
        "--max-text-features",
        type=int,
        default=30000,
        help="Max TF-IDF features for text",
    )
    parser.add_argument(
        "--clip-upper-quantile",
        type=float,
        default=0.99,
        help="Winsorize target to this upper quantile to reduce outlier dominance",
    )
    return parser.parse_args()


def require_columns(df, cols):
    missing = sorted(set(cols) - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def sanitize_df(df):
    for col in ["article_title", "event_text_segment", "article_source", "matched_node", "ml_risk_label"]:
        df[col] = df[col].fillna("").astype(str)
    for col in ["node_criticality", "ml_risk_confidence", "ml_prob_low", "ml_prob_medium", "ml_prob_high", "impact_score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["node_criticality"] = df["node_criticality"].fillna(1.0)
    df["ml_risk_confidence"] = df["ml_risk_confidence"].fillna(0.0)
    df["ml_prob_low"] = df["ml_prob_low"].fillna(0.0)
    df["ml_prob_medium"] = df["ml_prob_medium"].fillna(0.0)
    df["ml_prob_high"] = df["ml_prob_high"].fillna(0.0)
    df = df.dropna(subset=["impact_score"]).copy()
    return df


def build_text_input(df):
    return (df["article_title"] + " " + df["event_text_segment"].str.slice(0, 600)).values


def fit_features(train_df, max_text_features):
    text_vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=max_text_features)
    X_text = text_vectorizer.fit_transform(build_text_input(train_df))

    categorical_cols = ["article_source", "matched_node", "ml_risk_label"]
    cat_encoder = OneHotEncoder(handle_unknown="ignore")
    X_cat = cat_encoder.fit_transform(train_df[categorical_cols])

    numeric_cols = ["node_criticality", "ml_risk_confidence", "ml_prob_low", "ml_prob_medium", "ml_prob_high"]
    X_num = sparse.csr_matrix(train_df[numeric_cols].values.astype(float))

    X = sparse.hstack([X_text, X_cat, X_num], format="csr")
    artifacts = {
        "text_vectorizer": text_vectorizer,
        "cat_encoder": cat_encoder,
        "categorical_cols": categorical_cols,
        "numeric_cols": numeric_cols,
    }
    return X, artifacts


def transform_features(df, artifacts):
    X_text = artifacts["text_vectorizer"].transform(build_text_input(df))
    X_cat = artifacts["cat_encoder"].transform(df[artifacts["categorical_cols"]])
    X_num = sparse.csr_matrix(df[artifacts["numeric_cols"]].values.astype(float))
    return sparse.hstack([X_text, X_cat, X_num], format="csr")


def spearman_like(y_true, y_pred):
    # Spearman correlation via rank transform without extra dependencies.
    true_ranks = pd.Series(y_true).rank(method="average")
    pred_ranks = pd.Series(y_pred).rank(method="average")
    return float(true_ranks.corr(pred_ranks))


def evaluate_split(name, model, df, artifacts):
    if df.empty:
        print(f"{name}: skipped (0 rows)")
        return None
    X = transform_features(df, artifacts)
    y = df["impact_score"].values
    y_pred = np.maximum(0.0, np.asarray(model.predict(X)).ravel())
    mae = mean_absolute_error(y, y_pred)
    rmse = np.sqrt(mean_squared_error(y, y_pred))
    sp = spearman_like(y, y_pred)
    print(f"{name}: rows={len(df)} MAE={mae:.3f} RMSE={rmse:.3f} Spearman={sp:.3f}")
    return {"mae": mae, "rmse": rmse, "spearman": sp, "rows": len(df)}


def main():
    args = parse_args()
    input_path = Path(args.input_csv)
    output_path = Path(args.output_model)

    if not input_path.exists():
        raise FileNotFoundError(f"Input dataset not found: {input_path}")

    df = pd.read_csv(input_path)
    require_columns(
        df,
        [
            "article_title",
            "event_text_segment",
            "article_source",
            "matched_node",
            "ml_risk_label",
            "node_criticality",
            "ml_risk_confidence",
            "ml_prob_low",
            "ml_prob_medium",
            "ml_prob_high",
            "impact_score",
            "split",
        ],
    )
    df = sanitize_df(df)

    if df.empty:
        raise ValueError("No valid rows after cleaning.")

    upper = df["impact_score"].quantile(args.clip_upper_quantile)
    df["impact_score"] = df["impact_score"].clip(lower=0.0, upper=upper)

    train_df = df[df["split"] == "train"].copy()
    val_df = df[df["split"] == "val"].copy()
    test_df = df[df["split"] == "test"].copy()

    if train_df.empty:
        raise ValueError("No training rows found (split=='train').")

    X_train, artifacts = fit_features(train_df, args.max_text_features)
    y_train = train_df["impact_score"].values

    model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    print(f"Train rows: {len(train_df)} | Val rows: {len(val_df)} | Test rows: {len(test_df)}")
    print(f"Clipped target upper bound (q={args.clip_upper_quantile}): {upper:.3f}")

    metrics = {
        "val": evaluate_split("VAL", model, val_df, artifacts),
        "test": evaluate_split("TEST", model, test_df, artifacts),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        pickle.dump(
            {
                "model": model,
                "artifacts": artifacts,
                "target": "impact_score",
                "metrics": metrics,
                "clip_upper_quantile": args.clip_upper_quantile,
            },
            f,
        )
    print(f"Saved regressor: {output_path}")


if __name__ == "__main__":
    main()
