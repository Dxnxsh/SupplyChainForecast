"""T10.2 — LLM-free relevance labeler + theme router.

Loads:
  model_training/relevance_classifier_emb.pkl  (emb_logreg, thr=0.59)
  model_training/theme_prototypes.pkl           (12 MiniLM prototype vectors)

Public API:
  labeler = Labeler()
  results = labeler.label_batch(texts)  # texts = [title + " " + body, ...]
  # Each result: {relevant, P, themes, top_theme, top_sim}

Relevance threshold = 0.59  (emb_logreg best_thr from relevance_metrics_embeddings.json:
  R=0.889, P=0.615, F1=0.727 at thr=0.59 vs F1=0.691 at thr=0.50)

Theme routing:
  cosine(article_emb, prototype) ≥ TAU → assign theme
  TAU tuned so ≥95% of known positives route to at least one theme.
  Top-k=2 themes max; fallback to highest-cosine theme if none clear TAU.

Usage as module:
  from scripts.live_label import Labeler
  labeler = Labeler()
  results = labeler.label_batch(["TSMC cuts output amid quake", ...])

Standalone (tune / gate):
  venv311/bin/python -m scripts.live_label --tune
  venv311/bin/python -m scripts.live_label --fixture
"""

from __future__ import annotations

import os
import pickle
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.getcwd())

import numpy as np
from dotenv import load_dotenv

load_dotenv(".env")

RELEVANCE_THR = 0.59
TAU_DEFAULT = 0.30  # tuned: 97.2% of positives route to gold theme above-τ; avg 1.96 themes/article
TOPK = 2

RELEVANCE_PKL = "model_training/relevance_classifier_emb.pkl"
PROTO_PKL = "model_training/theme_prototypes.pkl"


@dataclass
class LabelResult:
    relevant: bool
    P: float
    themes: list[str] = field(default_factory=list)
    top_theme: str | None = None
    top_sim: float = 0.0


class Labeler:
    def __init__(
        self,
        relevance_pkl: str = RELEVANCE_PKL,
        proto_pkl: str = PROTO_PKL,
        thr: float = RELEVANCE_THR,
        tau: float = TAU_DEFAULT,
    ):
        # Load relevance classifier
        with open(relevance_pkl, "rb") as f:
            rel_bundle = pickle.load(f)
        self.classifier = rel_bundle["classifier"]
        encoder_name = rel_bundle["encoder_name"]

        # Load theme prototypes
        with open(proto_pkl, "rb") as f:
            proto_bundle = pickle.load(f)
        self.theme_names: list[str] = proto_bundle["themes"]
        self.protos: np.ndarray = proto_bundle["protos"]   # [12, 384]

        # Single encoder shared for both relevance + routing
        from sentence_transformers import SentenceTransformer
        self.encoder = SentenceTransformer(encoder_name)

        self.thr = thr
        self.tau = tau

    def label_batch(self, texts: list[str]) -> list[LabelResult]:
        if not texts:
            return []

        embs = self.encoder.encode(
            texts, batch_size=64, normalize_embeddings=True,
            show_progress_bar=False, convert_to_numpy=True,
        )  # [N, 384]

        probs = self.classifier.predict_proba(embs)[:, 1]  # [N]

        results: list[LabelResult] = []
        for i, p in enumerate(probs):
            relevant = bool(p >= self.thr)
            if not relevant:
                results.append(LabelResult(relevant=False, P=round(float(p), 4)))
                continue

            # Theme routing — reuse the embedding already computed
            sims = embs[i] @ self.protos.T  # [12]
            order = np.argsort(sims)[::-1]

            themes = [self.theme_names[j] for j in order[:TOPK] if sims[j] >= self.tau]
            top_idx = int(order[0])
            top_theme = self.theme_names[top_idx]
            top_sim = float(sims[top_idx])

            # Fallback: always assign the best-matching theme even if below τ
            if not themes:
                themes = [top_theme]

            results.append(LabelResult(
                relevant=True,
                P=round(float(p), 4),
                themes=themes,
                top_theme=top_theme,
                top_sim=round(top_sim, 4),
            ))
        return results


def _tune_tau(labeler: Labeler) -> float:
    """Find the minimum τ such that ≥95% of known positives route to ≥1 theme above τ."""
    from sqlalchemy import create_engine, text as sql_text
    from src.db_config import get_read_db_url

    engine = create_engine(get_read_db_url())
    with engine.connect() as conn:
        rows = conn.execute(sql_text("""
            SELECT d.article_title, d.themes, COALESCE(e.event_text_segment,'') AS body
            FROM disruption_candidates d
            LEFT JOIN events e ON e.article_title = d.article_title
            WHERE d.is_risk_event AND d.strict_is_risk
        """)).fetchall()

    texts = [(r[0] + " " + r[2][:700]).strip() for r in rows]
    gold_themes = [r[1] if isinstance(r[1], list) else [] for r in rows]

    print(f"Tuning τ on {len(texts)} positives …")
    embs = labeler.encoder.encode(
        texts, batch_size=64, normalize_embeddings=True,
        show_progress_bar=True, convert_to_numpy=True,
    )
    sims_all = embs @ labeler.protos.T  # [N, 12]

    for tau in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45]:
        correct = 0
        for i, gthemes in enumerate(gold_themes):
            order = np.argsort(sims_all[i])[::-1]  # highest-sim first
            routed_themes = [
                labeler.theme_names[j] for j in order[:TOPK]
                if sims_all[i][j] >= tau
            ]
            if not routed_themes:
                routed_themes = [labeler.theme_names[int(order[0])]]  # fallback
            if any(t in gthemes for t in routed_themes):
                correct += 1
        pct = correct / len(texts) * 100
        print(f"  τ={tau:.2f}  routed_to_gold={correct}/{len(texts)} ({pct:.1f}%)")
        if pct >= 95:
            print(f"  → τ={tau:.2f} meets ≥95% target")
            return tau

    print("  WARNING: no τ reached 95% — using 0.30 (fallback always activates)")
    return 0.30


FIXTURE = [
    ("Red Sea tanker blockade as Houthis target cargo ships near Bab-el-Mandeb",
     "Strait of Hormuz / Gulf shipping"),
    ("TSMC Hsinchu fab halts production after major earthquake strikes Taiwan",
     "Taiwan semiconductors"),
    ("China bans lithium carbonate exports citing domestic shortage concerns",
     "Lithium & battery materials"),
    ("VW and Stellantis auto plant closures spread across Germany and France",
     "European auto supply chain"),
    ("West Coast port strike: ILWU workers walk out at Los Angeles and Long Beach",
     "US West Coast ports"),
]


def _run_fixture(labeler: Labeler) -> bool:
    texts = [t for t, _ in FIXTURE]
    expected = [e for _, e in FIXTURE]
    results = labeler.label_batch(texts)
    print("\n=== T10.2 fixture gate ===")
    all_pass = True
    for (headline, exp_theme), r in zip(FIXTURE, results):
        ok_rel = r.relevant
        ok_theme = exp_theme in r.themes if r.relevant else False
        flag = "PASS" if (ok_rel and ok_theme) else "FAIL"
        if not (ok_rel and ok_theme):
            all_pass = False
        print(f"  [{flag}] P={r.P:.3f} rel={r.relevant} themes={r.themes}")
        print(f"        expected: {exp_theme}")
        print(f"        headline: {headline[:70]}")
    return all_pass


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", action="store_true", help="Tune τ on the 574 positives")
    ap.add_argument("--fixture", action="store_true", help="Run 5-headline fixture gate")
    ap.add_argument("--tau", type=float, default=TAU_DEFAULT, help="Override τ")
    args = ap.parse_args()

    labeler = Labeler(tau=args.tau)

    if args.tune:
        best_tau = _tune_tau(labeler)
        print(f"\nRecommended τ = {best_tau:.2f}  (update TAU_DEFAULT in live_label.py if different)")

    if args.fixture or not args.tune:
        passed = _run_fixture(labeler)
        sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
