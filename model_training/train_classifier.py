import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier


def main():
    base_dir = Path(__file__).resolve().parent
    input_csv = base_dir / "labeled_data.csv"
    output_model = base_dir / "classifier.pkl"

    if not input_csv.exists():
        raise FileNotFoundError(
            f"{input_csv} not found. Run label_data.py first."
        )

    df = pd.read_csv(input_csv).dropna(subset=["headline", "text", "risk"])
    if df.empty:
        raise ValueError("No labeled rows found in labeled_data.csv.")

    # Use headline + first 300 chars of text as model input.
    df["input"] = df["headline"].astype(str) + " " + df["text"].astype(str).str[:300]

    X_train, X_test, y_train, y_test = train_test_split(
        df["input"],
        df["risk"],
        test_size=0.2,
        random_state=42,
        stratify=df["risk"] if df["risk"].nunique() > 1 else None,
    )

    label_encoder = LabelEncoder()
    label_encoder.fit(df["risk"])
    y_train_enc = label_encoder.transform(y_train)
    y_test_enc = label_encoder.transform(y_test)

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=10000)
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)

    n_class = int(len(label_encoder.classes_))
    eval_metric = "logloss" if n_class == 2 else "mlogloss"
    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        eval_metric=eval_metric,
    )
    model.fit(X_train_vec, y_train_enc)

    y_pred = label_encoder.inverse_transform(np.asarray(model.predict(X_test_vec), dtype=int))
    print(classification_report(y_test, y_pred))

    with output_model.open("wb") as f:
        pickle.dump((vectorizer, model, label_encoder), f)

    print(f"Saved {output_model}")


if __name__ == "__main__":
    main()
