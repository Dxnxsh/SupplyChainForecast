"""T4 — easy negatives for the relevance classifier (Phase 2).

Samples random NON-disruption news from the RAW `events` corpus (~180k rows) to
round out the relevance training set. "Easy" = does NOT match CANDIDATE_RE (the
disruption keyword pre-filter) and is NOT already a cascade candidate, so these
are unambiguous negatives that the keyword filter already screens out.

  positives (T2b clean)  +  hard negatives (strict-dropped / lenient-rejected)
                         +  easy negatives (THIS)   →  relevance classifier (T5)

Resumable + idempotent (article_title PK, ON CONFLICT DO NOTHING). Reproducible
sample via setseed. Default target ~2500 rows (design §12.3 / §12.5: ~2–3k).

Usage:
  venv311/bin/python -m scripts.build_easy_negatives --n 2500
  venv311/bin/python -m scripts.build_easy_negatives --report
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

from sqlalchemy import create_engine, text

from src.db_config import get_read_db_url
from scripts.build_disruption_dataset import BLOB, CANDIDATE_RE

SEED = 0.42  # reproducible random sample


def get_engine():
    return create_engine(get_read_db_url())


def create_table(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS easy_negatives (
                article_title TEXT PRIMARY KEY,
                article_id    TEXT,
                article_url   TEXT,
                article_date  DATE,
                body          TEXT,
                added_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """))


def sample(engine, n):
    """Insert up to N random non-candidate articles not already an easy-neg or a cascade candidate."""
    with engine.begin() as conn:
        conn.execute(text("SELECT setseed(:s)"), {"s": SEED})
        inserted = conn.execute(text(f"""
            WITH picked AS (
                SELECT DISTINCT ON (e.article_title)
                       e.article_title, e.id::text AS article_id, e.article_url,
                       e.article_timestamp::date AS article_date,
                       LEFT(e.event_text_segment, 1200) AS body
                FROM events e
                WHERE e.article_title IS NOT NULL
                  AND {BLOB} !~ :pat
                  AND e.article_title NOT IN (SELECT article_title FROM disruption_candidates)
                  AND e.article_title NOT IN (SELECT article_title FROM easy_negatives)
                ORDER BY e.article_title, e.id
            )
            INSERT INTO easy_negatives (article_title, article_id, article_url, article_date, body)
            SELECT article_title, article_id, article_url, article_date, body
            FROM picked ORDER BY random() LIMIT :n
            ON CONFLICT (article_title) DO NOTHING
        """), {"pat": CANDIDATE_RE, "n": n}).rowcount
    return inserted


def report(engine):
    with engine.connect() as conn:
        tot = conn.execute(text("SELECT COUNT(*) FROM easy_negatives")).scalar() or 0
        # acceptance check: none should match the disruption pre-filter
        # (qualify the blob columns to events `e` — both tables have article_title)
        blob_e = "lower(coalesce(e.article_title,'') || ' ' || coalesce(e.event_text_segment,''))"
        bad = conn.execute(text(f"""
            SELECT COUNT(*) FROM easy_negatives en
            JOIN events e ON e.article_title = en.article_title
            WHERE {blob_e} ~ :pat
        """), {"pat": CANDIDATE_RE}).scalar() or 0
        with_date = conn.execute(text("SELECT COUNT(*) FROM easy_negatives WHERE article_date IS NOT NULL")).scalar() or 0
        print(f"easy_negatives: {tot}  (with date: {with_date})")
        print(f"acceptance — rows matching CANDIDATE_RE (must be 0): {bad}")
        rows = conn.execute(text("""
            SELECT to_char(article_date,'YYYY-MM') m, COUNT(*) c
            FROM easy_negatives WHERE article_date IS NOT NULL
            GROUP BY m ORDER BY m
        """)).fetchall()
        if rows:
            print("by month:")
            for r in rows:
                print(f"  {r[0]}  {r[1]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2500, help="target easy-negative count")
    ap.add_argument("--report", action="store_true", help="print stats and exit")
    args = ap.parse_args()

    engine = get_engine()
    create_table(engine)
    if args.report:
        report(engine)
        return
    added = sample(engine, args.n)
    print(f"Inserted {added} new easy negatives.")
    print("\n--- stats ---")
    report(engine)


if __name__ == "__main__":
    main()
