import argparse
import csv
import pickle
from pathlib import Path

import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix


VALID_LABELS = {"LOW", "MEDIUM", "HIGH"}


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate classifier against manually labeled eval set.")
    parser.add_argument("--eval-csv", default="model_training/eval_set.csv", help="CSV with manual labels")
    parser.add_argument("--model", default="model_training/classifier.pkl", help="Pickle file with vectorizer/model")
    parser.add_argument("--uncertain-output", default="model_training/uncertain_candidates.csv", help="CSV path for lowest-confidence samples")
    parser.add_argument("--uncertain-count", type=int, default=100, help="How many low-confidence rows to export")
    return parser.parse_args()


def main():
    args = parse_args()
    eval_path = Path(args.eval_csv)
    model_path = Path(args.model)
    uncertain_path = Path(args.uncertain_output)

    if not eval_path.exists():
        raise FileNotFoundError(f"Eval CSV not found: {eval_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    df = pd.read_csv(eval_path)
    required_cols = {"headline", "text", "manual_label"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in eval CSV: {sorted(missing)}")

    df["manual_label"] = df["manual_label"].astype(str).str.strip().str.upper()
    labeled_df = df[df["manual_label"].isin(VALID_LABELS)].copy()
    if labeled_df.empty:
        raise ValueError("No valid manual labels found. Fill manual_label with LOW/MEDIUM/HIGH.")

    with model_path.open("rb") as f:
        vectorizer, model = pickle.load(f)

    labeled_df["input_text"] = (
        labeled_df["headline"].fillna("").astype(str)
        + " "
        + labeled_df["text"].fillna("").astype(str).str[:300]
    )
    X = vectorizer.transform(labeled_df["input_text"])
    preds = model.predict(X)
    probs = model.predict_proba(X)
    classes = list(model.classes_)

    labeled_df["pred_label"] = preds
    labeled_df["pred_confidence"] = probs.max(axis=1)
    labeled_df["pred_margin"] = [
        float(sorted(row, reverse=True)[0] - sorted(row, reverse=True)[1]) if len(row) > 1 else float(row[0])
        for row in probs
    ]

    for idx, cls in enumerate(classes):
        labeled_df[f"prob_{cls}"] = probs[:, idx]

    print(f"Evaluated rows: {len(labeled_df)}")
    print("\nClassification Report:")
    print(classification_report(labeled_df["manual_label"], labeled_df["pred_label"], digits=4))

    labels_order = ["LOW", "MEDIUM", "HIGH"]
    cm = confusion_matrix(labeled_df["manual_label"], labeled_df["pred_label"], labels=labels_order)
    print("Confusion Matrix (rows=true, cols=pred):")
    print("labels:", labels_order)
    print(cm)

    uncertain = labeled_df.sort_values(["pred_confidence", "pred_margin"], ascending=[True, True]).head(args.uncertain_count)
    uncertain_path.parent.mkdir(parents=True, exist_ok=True)
    uncertain_cols = [
        "id", "article_url", "headline", "text", "manual_label",
        "pred_label", "pred_confidence", "pred_margin",
    ] + [f"prob_{c}" for c in classes]
    uncertain[[c for c in uncertain_cols if c in uncertain.columns]].to_csv(uncertain_path, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"\nSaved uncertain candidates: {uncertain_path} ({len(uncertain)} rows)")


if __name__ == "__main__":
    main()
