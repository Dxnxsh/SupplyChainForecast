import argparse
import pickle
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split


VALID_LABELS = {"LOW", "MEDIUM", "HIGH"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Retrain classifier using original labeled_data + manually corrected feedback labels."
    )
    parser.add_argument("--base-data", default="model_training/labeled_data.csv", help="Base auto-labeled CSV")
    parser.add_argument("--feedback-data", default="model_training/eval_set.csv", help="CSV with manual_label column")
    parser.add_argument("--output-model", default="model_training/classifier.pkl", help="Where to save retrained model")
    parser.add_argument("--test-size", type=float, default=0.2, help="Train/test split fraction")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed")
    return parser.parse_args()


def normalize_labels(series):
    return series.astype(str).str.strip().str.upper()


def load_base_dataset(path):
    df = pd.read_csv(path)
    needed = {"headline", "text", "risk"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"Base data missing required columns: {sorted(missing)}")
    df = df.dropna(subset=["headline", "text", "risk"]).copy()
    df["label"] = normalize_labels(df["risk"])
    df = df[df["label"].isin(VALID_LABELS)].copy()
    return df[["headline", "text", "label"]]


def load_feedback_dataset(path):
    df = pd.read_csv(path)
    needed = {"headline", "text", "manual_label"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"Feedback data missing required columns: {sorted(missing)}")
    df = df.dropna(subset=["headline", "text", "manual_label"]).copy()
    df["label"] = normalize_labels(df["manual_label"])
    df = df[df["label"].isin(VALID_LABELS)].copy()
    if df.empty:
        print("⚠️ No valid manual labels found in feedback file; retraining with base data only.")
    return df[["headline", "text", "label"]]


def main():
    args = parse_args()
    base_path = Path(args.base_data)
    feedback_path = Path(args.feedback_data)
    output_path = Path(args.output_model)

    if not base_path.exists():
        raise FileNotFoundError(f"Base data not found: {base_path}")
    if not feedback_path.exists():
        raise FileNotFoundError(f"Feedback data not found: {feedback_path}")

    base_df = load_base_dataset(base_path)
    feedback_df = load_feedback_dataset(feedback_path)

    combined = pd.concat([base_df, feedback_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["headline", "text", "label"])
    combined["input_text"] = combined["headline"].astype(str) + " " + combined["text"].astype(str).str[:300]

    if combined["label"].nunique() < 2:
        raise ValueError("Need at least 2 label classes to train.")

    stratify_labels = combined["label"] if combined["label"].nunique() > 1 else None
    X_train, X_test, y_train, y_test = train_test_split(
        combined["input_text"],
        combined["label"],
        test_size=args.test_size,
        random_state=args.random_state,
        stratify=stratify_labels,
    )

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=10000)
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)

    model = LogisticRegression(max_iter=1000, class_weight="balanced")
    model.fit(X_train_vec, y_train)
    y_pred = model.predict(X_test_vec)

    print(f"Base rows: {len(base_df)}")
    print(f"Feedback rows used: {len(feedback_df)}")
    print(f"Combined rows used: {len(combined)}")
    print("\nClassification report after retraining:")
    print(classification_report(y_test, y_pred, digits=4))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        pickle.dump((vectorizer, model), f)
    print(f"Saved retrained model to: {output_path}")


if __name__ == "__main__":
    main()
