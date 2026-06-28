"""T5+ (model improvement B) — relevance classifier with sentence-transformer embeddings.

Same training pools, same leakage-free held-out gold set as train_relevance_classifier.py, but
swaps sparse TF-IDF for dense all-MiniLM-L6-v2 embeddings (semantic features). Targets the weak
link: TF-IDF recall was 59%. Reports embeddings + LogReg(balanced) and embeddings + XGBoost,
head-to-head with the TF-IDF baseline on the SAME 150 human-labeled gold rows.

Usage:
  venv311/bin/python -m scripts.train_relevance_embeddings
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
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

from src.db_config import get_read_db_url
from sqlalchemy import create_engine
from scripts.train_relevance_classifier import _read_gold, build_training, fetch_gold_text, prf

ENCODER = "sentence-transformers/all-MiniLM-L6-v2"
METRICS_OUT = "data/relevance_metrics_embeddings.json"
MODEL_OUT = "model_training/relevance_classifier_emb.pkl"
SEED = 42


def main():
    human, _ = _read_gold()
    gold_titles = set(human)
    engine = create_engine(get_read_db_url())
    with engine.connect() as conn:
        texts, y = build_training(conn, gold_titles, 3000)
        gold_text = fetch_gold_text(conn, gold_titles)
    g_titles = list(gold_text)
    y_true = np.array([human[t] for t in g_titles])
    print(f"train rows={len(y)} (pos={int(y.sum())})  gold={len(y_true)} (pos={int(y_true.sum())})")

    print(f"Embedding with {ENCODER} ...")
    enc = SentenceTransformer(ENCODER)
    X = enc.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    Xg = enc.encode([gold_text[t] for t in g_titles], normalize_embeddings=True, show_progress_bar=False)

    spw = float((y == 0).sum()) / float(max(1, (y == 1).sum()))
    models = {
        "emb_logreg": LogisticRegression(class_weight="balanced", max_iter=2000, C=1.0),
        "emb_xgboost": XGBClassifier(n_estimators=300, max_depth=5, learning_rate=0.1,
                                     subsample=0.9, colsample_bytree=0.8, scale_pos_weight=spw,
                                     random_state=SEED, n_jobs=-1, eval_metric="logloss", verbosity=0),
    }
    # TF-IDF baseline numbers from the prior run (data/relevance_metrics.json) for reference
    tfidf = json.load(open("data/relevance_metrics.json"))["classifier"] if os.path.exists("data/relevance_metrics.json") else None

    results = {}
    best_name, best_f1, best_obj = None, -1.0, None
    for name, m in models.items():
        m.fit(X, y)
        proba = m.predict_proba(Xg)[:, 1]
        at05 = prf(y_true, (proba >= 0.5).astype(int))
        # best-F1 threshold (reported separately; tuned on gold so labeled as such)
        grid = np.linspace(0.1, 0.9, 81)
        bt = float(max(grid, key=lambda t: prf(y_true, (proba >= t).astype(int))["f1"]))
        atbt = prf(y_true, (proba >= bt).astype(int))
        results[name] = {"at_0.5": at05, "best_thr": round(bt, 3), "at_best_thr": atbt}
        if at05["f1"] > best_f1:
            best_name, best_f1, best_obj = name, at05["f1"], m
        print(f"  {name:<12} @0.5: P={at05['precision']:.0%} R={at05['recall']:.0%} F1={at05['f1']:.0%}"
              f"   @thr={bt:.2f}: P={atbt['precision']:.0%} R={atbt['recall']:.0%} F1={atbt['f1']:.0%}")

    print("\n=== head-to-head on the SAME 150 gold rows (at threshold 0.5) ===")
    if tfidf:
        print(f"  TF-IDF + XGBoost (baseline): P={tfidf['precision']:.0%} R={tfidf['recall']:.0%} F1={tfidf['f1']:.0%}")
    for name, r in results.items():
        a = r["at_0.5"]
        print(f"  {name:<26}: P={a['precision']:.0%} R={a['recall']:.0%} F1={a['f1']:.0%}")

    os.makedirs("model_training", exist_ok=True)
    with open(MODEL_OUT, "wb") as f:
        pickle.dump({"encoder_name": ENCODER, "classifier": best_obj, "best_model": best_name}, f)
    out = {"task": "relevance_classifier_embeddings", "encoder": ENCODER,
           "n_train": int(len(y)), "gold_n": int(len(y_true)),
           "tfidf_baseline": tfidf, "embeddings": results, "best_model": best_name}
    with open(METRICS_OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved best ({best_name}) -> {MODEL_OUT}\nSaved metrics -> {METRICS_OUT}")


if __name__ == "__main__":
    main()
