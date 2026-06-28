"""T6 — open-vocabulary topic model over the clean disruption events (BERTopic).

Unsupervised discovery layer (NOT a predictor feature — see design §11/§14). Clusters the 557
clean disruption events into emergent themes, then cross-tabs each topic against the 5 fixed
consolidated targets to (a) validate the discovered themes map to the supervised targets and
(b) surface emergent / drift themes not captured by the fixed list. Also reports each topic's
recent share (drift signal).

Pipeline: MiniLM embeddings -> UMAP -> HDBSCAN -> c-TF-IDF keywords.

Outputs:
  data/topic_model_summary.json   (topics, keywords, target mapping, drift)  [tracked, for UI]
  data/topic_assignments.csv      (per-event topic + primary target)         [tracked]
  model_training/bertopic_model/  (saved model)                              [gitignored]

Usage:
  venv311/bin/python -m scripts.build_topic_model
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from src.db_config import get_read_db_url
from scripts.train_predictor import TARGETS

SUMMARY_OUT = "data/topic_model_summary.json"
ASSIGN_OUT = "data/topic_assignments.csv"
MODEL_DIR = "model_training/bertopic_model"
ENCODER = "sentence-transformers/all-MiniLM-L6-v2"
SEED = 42

# invert target->themes into theme->target for per-event primary-target assignment
THEME_TO_TARGET = {theme: tgt for tgt, themes in TARGETS.items() for theme in themes}


def primary_target(themes):
    for t in (themes or []):
        if t in THEME_TO_TARGET:
            return THEME_TO_TARGET[t]
    return "unmapped"


def load_events():
    engine = create_engine(get_read_db_url())
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT d.article_title, d.article_date, d.themes::text,
                   COALESCE((SELECT LEFT(article_title||'. '||event_text_segment, 800) FROM events
                             WHERE article_title=d.article_title LIMIT 1), d.article_title) AS doc
            FROM disruption_candidates d
            WHERE d.is_risk_event AND d.strict_is_risk
        """)).fetchall()
    df = pd.DataFrame(rows, columns=["title", "date", "themes_json", "doc"])
    df["date"] = pd.to_datetime(df["date"])
    df["themes"] = df["themes_json"].apply(lambda s: json.loads(s) if s else [])
    df["target"] = df["themes"].apply(primary_target)
    return df


def main():
    from bertopic import BERTopic
    from hdbscan import HDBSCAN
    from sentence_transformers import SentenceTransformer
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    df = load_events()
    docs = df["doc"].tolist()
    print(f"Topic-modeling {len(docs)} clean disruption events")

    enc = SentenceTransformer(ENCODER)
    emb = enc.encode(docs, normalize_embeddings=True, show_progress_bar=False)

    umap_model = UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=SEED)
    hdbscan_model = HDBSCAN(min_cluster_size=8, metric="euclidean",
                            cluster_selection_method="eom", prediction_data=True)
    vectorizer = CountVectorizer(stop_words="english", ngram_range=(1, 2), min_df=3)
    topic_model = BERTopic(umap_model=umap_model, hdbscan_model=hdbscan_model,
                           vectorizer_model=vectorizer, calculate_probabilities=False, verbose=False)
    topics, _ = topic_model.fit_transform(docs, embeddings=emb)

    # reassign outliers (-1) to their nearest topic via embeddings for a cleaner picture
    try:
        topics = topic_model.reduce_outliers(docs, topics, strategy="embeddings", embeddings=emb)
        topic_model.update_topics(docs, topics=topics, vectorizer_model=vectorizer)
    except Exception as e:
        print(f"  (outlier reduction skipped: {e})")

    df["topic"] = topics
    info = topic_model.get_topic_info()
    real_topics = [t for t in sorted(set(topics)) if t != -1]
    print(f"Discovered {len(real_topics)} topics (+{int((np.array(topics)==-1).sum())} outliers)")

    # ---- topic -> consolidated-target mapping + drift ----
    recent_cut = df["date"].max() - pd.Timedelta(days=90)
    topic_rows = []
    print("\n  topic | size | dominant target (share) | recent% | top keywords")
    for tid in real_topics:
        sub = df[df["topic"] == tid]
        kws = [w for w, _ in topic_model.get_topic(tid)[:6]]
        tgt_counts = Counter(sub["target"])
        dom_tgt, dom_n = tgt_counts.most_common(1)[0]
        dom_share = dom_n / len(sub)
        recent_share = float((sub["date"] >= recent_cut).mean())
        topic_rows.append({
            "topic": int(tid), "size": int(len(sub)),
            "keywords": kws,
            "dominant_target": dom_tgt, "dominant_share": round(dom_share, 3),
            "target_distribution": {k: int(v) for k, v in tgt_counts.items()},
            "recent_90d_share": round(recent_share, 3),
            "example": sub.iloc[0]["title"][:90],
            "emergent": bool(dom_share < 0.5 or dom_tgt == "unmapped"),
        })
        print(f"   {tid:>4} | {len(sub):>4} | {dom_tgt:<24} {dom_share:.0%} | {recent_share:>4.0%} | {', '.join(kws[:5])}")

    n_mapped = sum(1 for r in topic_rows if r["dominant_share"] >= 0.5 and r["dominant_target"] != "unmapped")
    n_emergent = sum(1 for r in topic_rows if r["emergent"])
    accept = len(real_topics) >= 3 and n_mapped >= 3
    print(f"\n  topics mapping cleanly to a target (>=50%): {n_mapped}")
    print(f"  emergent / mixed topics (drift candidates): {n_emergent}")
    print(f"  ACCEPTANCE (>=3 topics, >=3 map to targets): {'PASS' if accept else 'FAIL'}")

    os.makedirs("data", exist_ok=True)
    df[["title", "date", "target", "topic"]].to_csv(ASSIGN_OUT, index=False)
    summary = {
        "task": "topic_model", "encoder": ENCODER, "n_docs": len(docs),
        "n_topics": len(real_topics), "n_outliers": int((np.array(topics) == -1).sum()),
        "n_topics_mapping_to_target": n_mapped, "n_emergent": n_emergent,
        "acceptance_pass": bool(accept), "topics": topic_rows,
    }
    with open(SUMMARY_OUT, "w") as f:
        json.dump(summary, f, indent=2)
    try:
        os.makedirs(MODEL_DIR, exist_ok=True)
        topic_model.save(MODEL_DIR, serialization="safetensors", save_ctfidf=True, save_embedding_model=False)
    except Exception as e:
        print(f"  (model save skipped: {e})")
    print(f"\nSaved summary -> {SUMMARY_OUT}\nSaved assignments -> {ASSIGN_OUT}")


if __name__ == "__main__":
    main()
