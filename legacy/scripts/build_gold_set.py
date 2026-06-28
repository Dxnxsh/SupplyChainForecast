"""Gold-set tool: validate the LLM's disruption labels against human judgment.

Two modes:
  export  — sample a stratified set (half LLM-positive, half LLM-negative) to a CSV
            for hand-labeling. Fill the `human_is_disruption` column with 1/0.
  score   — read the labeled CSV back and report the LLM labeler's precision / recall /
            agreement vs your human labels.

Usage:
  venv311/bin/python -m scripts.build_gold_set export --n 150
  # ... hand-label data/gold_set.csv (human_is_disruption = 1 or 0) ...
  venv311/bin/python -m scripts.build_gold_set score
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.getcwd())

from sqlalchemy import create_engine, text

from src.db_config import get_read_db_url

GOLD_PATH = "data/gold_set.csv"
GOLD_PATH_STRICT = "data/gold_set_full.csv"
FIELDS = ["article_title", "article_date", "llm_is_disruption", "llm_themes",
          "llm_reason", "human_is_disruption", "human_notes"]


def export(n, strict=False):
    engine = create_engine(get_read_db_url())
    path = GOLD_PATH_STRICT if strict else GOLD_PATH
    half = n // 2
    rows = []
    with engine.connect() as conn:
        for flag, k in ((True, half), (False, n - half)):
            if strict:
                # final clean labels: positives = strict-kept, negatives = strict-dropped
                q = text("""
                    SELECT article_title, article_date, strict_is_risk, themes::text, reason
                    FROM disruption_candidates
                    WHERE is_risk_event AND strict_is_risk = :flag
                    ORDER BY random() LIMIT :k
                """)
            else:
                q = text("""
                    SELECT article_title, article_date, is_risk_event, themes::text, reason
                    FROM disruption_candidates
                    WHERE is_risk_event = :flag
                    ORDER BY random() LIMIT :k
                """)
            for r in conn.execute(q, {"flag": flag, "k": k}).fetchall():
                rows.append({
                    "article_title": r[0], "article_date": r[1],
                    "llm_is_disruption": 1 if r[2] else 0, "llm_themes": r[3],
                    "llm_reason": r[4], "human_is_disruption": "", "human_notes": "",
                })
    os.makedirs("data", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    score_flag = " --strict" if strict else ""
    print(f"Wrote {len(rows)} rows to {path}")
    print("Hand-label the `human_is_disruption` column (1 = real supply-chain disruption, 0 = not),")
    print(f"then run: venv311/bin/python -m scripts.build_gold_set score{score_flag}")


def _read_csv_rows(path):
    """Read CSV tolerant of editor re-encodings (Excel/Numbers → cp1252 / mac-roman)."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "mac-roman", "latin-1"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return list(csv.DictReader(f)), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f)), "utf-8(replace)"


def score(strict=False):
    path = GOLD_PATH_STRICT if strict else GOLD_PATH
    if not os.path.exists(path):
        print(f"{path} not found — run `export` first.")
        return
    tp = fp = fn = tn = unlabeled = 0
    rows, enc = _read_csv_rows(path)
    if enc != "utf-8":
        print(f"(read as {enc})")
    for row in rows:
            h = row.get("human_is_disruption", "").strip()
            if h not in ("0", "1"):
                unlabeled += 1
                continue
            llm = row["llm_is_disruption"].strip() == "1"
            human = h == "1"
            if llm and human:
                tp += 1
            elif llm and not human:
                fp += 1
            elif not llm and human:
                fn += 1
            else:
                tn += 1
    labeled = tp + fp + fn + tn
    if labeled == 0:
        print(f"No labeled rows yet ({unlabeled} unlabeled). Fill human_is_disruption first.")
        return
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    acc = (tp + tn) / labeled
    print(f"Labeled: {labeled}  (unlabeled skipped: {unlabeled})")
    print(f"Confusion — TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"LLM-labeler precision: {precision:.1%}")
    print(f"LLM-labeler recall:    {recall:.1%}")
    print(f"F1: {f1:.1%}   Agreement (accuracy): {acc:.1%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["export", "score"])
    ap.add_argument("--n", type=int, default=150, help="gold-set size (export)")
    ap.add_argument("--strict", action="store_true", help="use the final strict-clean set → data/gold_set_full.csv")
    args = ap.parse_args()
    if args.mode == "export":
        export(args.n, strict=args.strict)
    else:
        score(strict=args.strict)


if __name__ == "__main__":
    main()
