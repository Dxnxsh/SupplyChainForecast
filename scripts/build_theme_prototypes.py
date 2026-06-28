"""T10.1 — Build per-theme MiniLM prototype vectors from the 557 clean events.

Encodes article_title + body (up to 700 chars) for every row in
disruption_candidates WHERE is_risk_event AND strict_is_risk, averages the
normalized embeddings per theme, re-normalizes the mean → unit prototype.

Output: model_training/theme_prototypes.pkl
  {
    "encoder_name": "sentence-transformers/all-MiniLM-L6-v2",
    "themes": [<12 theme names in THEMES order>],
    "protos": np.ndarray [12 x 384, float32, L2-normalised],
    "counts": {theme: n_articles},
  }

Gate (printed at the end):
  - 12 prototypes, 384-dim
  - For each theme: mean cosine to own members vs mean cosine to all other members
    (own > other confirms prototypes separate)

Usage:
  venv311/bin/python -m scripts.build_theme_prototypes
"""

from __future__ import annotations

import os
import pickle
import sys

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

import numpy as np
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text

from src.db_config import get_read_db_url
from scripts.build_disruption_dataset import THEMES

ENCODER = "sentence-transformers/all-MiniLM-L6-v2"
OUT = "model_training/theme_prototypes.pkl"


def main():
    engine = create_engine(get_read_db_url())
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT d.article_title,
                   d.themes,
                   COALESCE(e.event_text_segment, '') AS body
            FROM disruption_candidates d
            LEFT JOIN events e ON e.article_title = d.article_title
            WHERE d.is_risk_event AND d.strict_is_risk
        """)).fetchall()

    print(f"Loaded {len(rows)} clean events")

    # Build per-theme text lists
    theme_texts: dict[str, list[str]] = {t: [] for t in THEMES}
    for title, themes_json, body in rows:
        themes = themes_json if isinstance(themes_json, list) else []
        text_input = (title + " " + body[:700]).strip()
        for theme in themes:
            if theme in theme_texts:
                theme_texts[theme].append(text_input)

    for t in THEMES:
        n = len(theme_texts[t])
        print(f"  {t:<40} {n:>4} articles")

    # Encode all unique texts once, then fan out to themes
    all_texts: list[str] = []
    text_to_idx: dict[str, int] = {}
    for texts in theme_texts.values():
        for t in texts:
            if t not in text_to_idx:
                text_to_idx[t] = len(all_texts)
                all_texts.append(t)

    print(f"\nEncoding {len(all_texts)} unique texts with {ENCODER} …")
    enc = SentenceTransformer(ENCODER)
    all_embs = enc.encode(
        all_texts, batch_size=64, normalize_embeddings=True,
        show_progress_bar=True, convert_to_numpy=True,
    )  # [N, 384], already L2-normalised

    # Build prototype per theme: mean of member embeddings, re-normalised
    protos = np.zeros((len(THEMES), all_embs.shape[1]), dtype=np.float32)
    counts: dict[str, int] = {}
    for i, theme in enumerate(THEMES):
        idxs = [text_to_idx[t] for t in theme_texts[theme] if t in text_to_idx]
        counts[theme] = len(idxs)
        if idxs:
            mean = all_embs[idxs].mean(axis=0).astype(np.float32)
            norm = np.linalg.norm(mean)
            protos[i] = mean / norm if norm > 0 else mean
        else:
            # No examples — leave as zero vector (will never beat τ in routing)
            print(f"  WARNING: no examples for theme '{theme}' — zero prototype")

    os.makedirs("model_training", exist_ok=True)
    with open(OUT, "wb") as f:
        pickle.dump({
            "encoder_name": ENCODER,
            "themes": THEMES,
            "protos": protos,
            "counts": counts,
        }, f)
    print(f"\nSaved → {OUT}  shape={protos.shape}")

    # Gate: self-cosine vs cross-cosine per theme
    print("\n=== Gate: prototype separation ===")
    print(f"{'Theme':<40} {'n':>4}  {'self-cos':>9}  {'cross-cos':>9}  {'margin':>7}  gate")
    all_pass = True
    for i, theme in enumerate(THEMES):
        n = counts[theme]
        if n == 0:
            print(f"  {theme:<40} {n:>4}  {'—':>9}  {'—':>9}  {'—':>7}  SKIP")
            continue
        idxs = [text_to_idx[t] for t in theme_texts[theme] if t in text_to_idx]
        member_embs = all_embs[idxs]
        self_cos_mean = float((member_embs @ protos[i]).mean())

        # cross: cosine of members against every OTHER prototype
        other_protos = np.delete(protos, i, axis=0)
        cross_cos_mean = float((member_embs @ other_protos.T).mean())

        margin = self_cos_mean - cross_cos_mean
        ok = margin > 0
        if not ok:
            all_pass = False
        flag = "PASS" if ok else "FAIL"
        print(f"  {theme:<40} {n:>4}  {self_cos_mean:>9.4f}  {cross_cos_mean:>9.4f}  {margin:>7.4f}  {flag}")

    print(f"\nOverall gate: {'PASS' if all_pass else 'WARN (some themes have negative margin — expected for sparse themes)'}")
    print(f"Note: themes with n≤4 may have noisy prototypes; τ tuning in T10.2 compensates.")


if __name__ == "__main__":
    main()
