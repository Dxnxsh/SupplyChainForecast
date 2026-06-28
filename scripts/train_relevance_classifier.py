"""T5 — relevance classifier (replaces the live LLM at inference).

Distills the LLM cascade's clean-event decision into an own model: TF-IDF + XGBoost.
At inference it answers "is this article a real supply-chain disruption?" with no LLM call.

Training labels (distant supervision from the cascade):
  positive (1) = clean event            : is_risk_event AND strict_is_risk        (557)
  negative (0) = hard neg (strict-drop) : is_risk_event AND NOT strict_is_risk    (1082)
               + hard neg (lenient-rej) : NOT is_risk_event   (sampled)
               + easy neg               : easy_negatives table                    (2500)

Leakage control: the 150 gold-set titles are EXCLUDED from training, then predicted on
and scored against the HUMAN labels in data/gold_set_full.csv. Reported alongside two
baselines: the keyword pre-filter (all candidates -> positive) and the LLM strict pass.

Outputs:
  model_training/relevance_classifier.pkl   (vectorizer, model)  [gitignored]
  data/relevance_metrics.json               (metrics for the UI)  [tracked]

Usage:
  venv311/bin/python -m scripts.train_relevance_classifier
  venv311/bin/python -m scripts.train_relevance_classifier --lenient-sample 3000
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import pickle
import sys

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import precision_recall_fscore_support
from sqlalchemy import create_engine, text
from xgboost import XGBClassifier

from src.db_config import get_read_db_url

GOLD_PATH = "data/gold_set_full.csv"
MODEL_OUT = "model_training/relevance_classifier.pkl"
METRICS_OUT = "data/relevance_metrics.json"
SEED = 42


def get_engine():
    return create_engine(get_read_db_url())


def _read_gold():
    """Return {title: human_label(int)} and {title: llm_strict_label(int)} for labeled rows."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "mac-roman", "latin-1"):
        try:
            rows = list(csv.DictReader(open(GOLD_PATH, encoding=enc, newline="")))
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    human, llm = {}, {}
    for r in rows:
        h = r.get("human_is_disruption", "").strip()
        if h in ("0", "1"):
            human[r["article_title"]] = int(h)
            llm[r["article_title"]] = 1 if r.get("llm_is_disruption", "").strip() == "1" else 0
    return human, llm


def _fetch(conn, where, params=None, limit=None):
    lim = f" LIMIT {int(limit)}" if limit else ""
    q = text(f"""
        SELECT d.article_title,
               COALESCE((SELECT LEFT(event_text_segment, 1200) FROM events
                         WHERE article_title = d.article_title LIMIT 1), '') AS body
        FROM disruption_candidates d
        WHERE {where}{lim}
    """)
    return conn.execute(q, params or {}).fetchall()


def build_training(conn, gold_titles, lenient_sample):
    rows, labels = [], []

    def add(fetched, label):
        for title, body in fetched:
            if title in gold_titles:
                continue  # leakage control
            rows.append(f"{title} {body}")
            labels.append(label)

    add(_fetch(conn, "d.is_risk_event AND d.strict_is_risk"), 1)
    add(_fetch(conn, "d.is_risk_event AND d.strict_is_risk IS NOT TRUE"), 0)
    conn.execute(text("SELECT setseed(:s)"), {"s": 0.42})
    add(_fetch(conn, "NOT d.is_risk_event ORDER BY random()", limit=lenient_sample), 0)
    easy = conn.execute(text("SELECT article_title, COALESCE(body,'') FROM easy_negatives")).fetchall()
    add(easy, 0)
    return rows, np.array(labels)


def fetch_gold_text(conn, titles):
    out = {}
    for t in titles:
        r = conn.execute(text(
            "SELECT LEFT(event_text_segment, 1200) FROM events WHERE article_title = :t LIMIT 1"
        ), {"t": t}).fetchone()
        out[t] = f"{t} {(r[0] if r else '') or ''}"
    return out


def prf(y_true, y_pred):
    p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    acc = float(np.mean(np.asarray(y_true) == np.asarray(y_pred)))
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "accuracy": round(acc, 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lenient-sample", type=int, default=3000, help="how many lenient-rejected hard negatives to include")
    ap.add_argument("--threshold", type=float, default=0.5)
    args = ap.parse_args()

    human, llm_strict = _read_gold()
    gold_titles = set(human)
    print(f"Gold: {len(gold_titles)} labeled (pos={sum(human.values())}, neg={len(human)-sum(human.values())})")

    engine = get_engine()
    with engine.connect() as conn:
        texts, y = build_training(conn, gold_titles, args.lenient_sample)
        gold_text = fetch_gold_text(conn, gold_titles)

    print(f"Training rows: {len(y)}  (pos={int(y.sum())}, neg={int((y==0).sum())})")

    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=30000, sublinear_tf=True)
    X = vec.fit_transform(texts)

    spw = float((y == 0).sum()) / float(max(1, (y == 1).sum()))
    clf = XGBClassifier(
        n_estimators=300, max_depth=6, learning_rate=0.1,
        subsample=0.9, colsample_bytree=0.8, scale_pos_weight=spw,
        random_state=SEED, n_jobs=-1, eval_metric="logloss", verbosity=0,
    )
    clf.fit(X, y)

    # ---- evaluate on held-out gold ----
    g_titles = list(gold_text)
    Xg = vec.transform([gold_text[t] for t in g_titles])
    proba = clf.predict_proba(Xg)[:, 1]
    y_true = [human[t] for t in g_titles]
    y_clf = [int(p >= args.threshold) for p in proba]

    clf_m = prf(y_true, y_clf)
    # baseline 1: keyword pre-filter — every gold row is already a candidate => predict all positive
    kw_m = prf(y_true, [1] * len(y_true))
    # baseline 2: the LLM strict pass label
    llm_m = prf(y_true, [llm_strict[t] for t in g_titles])

    print("\n=== Relevance eval on held-out human gold (n={}) ===".format(len(y_true)))
    print(f"  classifier (XGBoost+TF-IDF) : P={clf_m['precision']:.0%} R={clf_m['recall']:.0%} F1={clf_m['f1']:.0%} acc={clf_m['accuracy']:.0%}")
    print(f"  keyword baseline (all-pos)  : P={kw_m['precision']:.0%} R={kw_m['recall']:.0%} F1={kw_m['f1']:.0%}")
    print(f"  LLM strict pass (oracle ref): P={llm_m['precision']:.0%} R={llm_m['recall']:.0%} F1={llm_m['f1']:.0%}")
    beats = clf_m["f1"] > kw_m["f1"]
    print(f"\n  ACCEPTANCE (classifier F1 > keyword baseline F1): {'PASS' if beats else 'FAIL'}")

    os.makedirs("model_training", exist_ok=True)
    with open(MODEL_OUT, "wb") as f:
        pickle.dump((vec, clf), f)
    metrics = {
        "task": "relevance_classifier",
        "n_train": int(len(y)), "n_train_pos": int(y.sum()),
        "gold_n": len(y_true), "threshold": args.threshold,
        "classifier": clf_m, "keyword_baseline": kw_m, "llm_strict_ref": llm_m,
        "beats_keyword_baseline": bool(beats),
    }
    os.makedirs("data", exist_ok=True)
    with open(METRICS_OUT, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nSaved model -> {MODEL_OUT}")
    print(f"Saved metrics -> {METRICS_OUT}")


if __name__ == "__main__":
    main()
