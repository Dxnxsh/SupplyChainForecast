import pickle
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split


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

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=10000)
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)

    model = LogisticRegression(max_iter=1000, class_weight="balanced")
    model.fit(X_train_vec, y_train)

    y_pred = model.predict(X_test_vec)
    print(classification_report(y_test, y_pred))

    with output_model.open("wb") as f:
        pickle.dump((vectorizer, model), f)

    print(f"Saved {output_model}")


if __name__ == "__main__":
    main()
