"""Strict precision pass: re-verify the LLM-positive events with a stronger model + a
hard-exclude prompt, to cut the false positives (market/speculation) the lenient pass let in.

Adds `strict_is_risk` / `strict_model` to disruption_candidates. Cleaned positive set =
is_risk_event AND strict_is_risk. Resumable (skips rows already re-verified).

Usage:
  venv311/bin/python -m scripts.reverify_positives --workers 12
  venv311/bin/python -m scripts.reverify_positives --score-gold   # precision vs gold after
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

from sqlalchemy import create_engine, text

from src.db_config import get_read_db_url
from src.gemini_client import generate

MODEL = "gemini-3.5-flash"

STRICT_SYSTEM = (
    "You are a STRICT supply-chain disruption auditor. Mark is_disruption=true ONLY if the "
    "article reports a CONCRETE real-world disruptive event that has happened, is happening, or "
    "is imminent-and-announced, with a DIRECT operational impact on physical supply "
    "(manufacturing, shipping, ports, transport routes, or material availability). "
    "QUALIFIES: factory fire/explosion, production halt, an active strike or one announced for a "
    "specific date, port closure/blockade, a natural disaster striking a production/shipping "
    "region, an imposed export ban/sanction, a confirmed component shortage. "
    "HARD EXCLUDE (always false): stock prices, market cap, earnings, analyst ratings, "
    "investments, M&A, product launches/announcements, financial results; speculation or "
    "hypotheticals ('could', 'may', 'discussed', 'plans to', 'fears', 'warns of', 'risk of'); "
    "diplomacy/talks/negotiations; political commentary; opinion; sports; personnel/awards. "
    "A mere threat being discussed, or a market reaction, is false."
)

STRICT_USER = """Article title: {title}
Article text: {body}

Return ONLY JSON: {{"is_disruption": true/false, "reason": "one short sentence"}}"""

import json
import re


def get_engine():
    return create_engine(get_read_db_url())


def add_columns(engine):
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE disruption_candidates ADD COLUMN IF NOT EXISTS strict_is_risk BOOLEAN"))
        conn.execute(text("ALTER TABLE disruption_candidates ADD COLUMN IF NOT EXISTS strict_model TEXT"))


def parse_json(txt):
    txt = re.sub(r"^```(json)?|```$", "", txt.strip(), flags=re.MULTILINE).strip()
    s, e = txt.find("{"), txt.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(txt[s:e + 1])
    except json.JSONDecodeError:
        return None


def fetch_pending(conn):
    return conn.execute(text("""
        SELECT d.article_title, LEFT(e.event_text_segment, 1200)
        FROM disruption_candidates d
        LEFT JOIN LATERAL (
            SELECT event_text_segment FROM events
            WHERE article_title = d.article_title LIMIT 1
        ) e ON true
        WHERE d.is_risk_event AND d.strict_is_risk IS NULL
    """)).fetchall()


CIRCUIT_BREAK = 20  # consecutive LLM errors → abort (out of credit/quota)


def _verify(row):
    title, body = row
    try:
        txt = generate(STRICT_SYSTEM, STRICT_USER.format(title=title, body=body or ""), model=MODEL)
    except Exception as exc:
        print(f"  err ({title[:40]}…): {exc}")
        return title, None, True
    v = parse_json(txt)
    if v is None:
        return title, None, False
    return title, bool(v.get("is_disruption")), False


def run(engine, workers):
    with engine.connect() as conn:
        pending = fetch_pending(conn)
    print(f"Re-verifying {len(pending)} positives with {MODEL} (workers={workers})")
    kept = dropped = 0
    consec_err = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_verify, r) for r in pending]
        for i, fut in enumerate(as_completed(futs), 1):
            title, verdict, err = fut.result()
            if err:
                consec_err += 1
                if consec_err >= CIRCUIT_BREAK:
                    print(f"\nCircuit breaker: {CIRCUIT_BREAK} consecutive LLM errors "
                          f"(out of credit/quota?). Stopping — rerun to resume; progress is saved.")
                    for f in futs:
                        f.cancel()
                    break
                continue
            consec_err = 0
            if verdict is None:
                continue
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE disruption_candidates SET strict_is_risk=:v, strict_model=:m WHERE article_title=:t"
                ), {"v": verdict, "m": MODEL, "t": title})
            kept += verdict
            dropped += (not verdict)
            if i % 50 == 0:
                print(f"[{i}/{len(pending)}] kept={kept} dropped={dropped}")
    with engine.connect() as conn:
        tot = conn.execute(text("SELECT COUNT(*) FROM disruption_candidates WHERE is_risk_event")).scalar()
        survive = conn.execute(text("SELECT COUNT(*) FROM disruption_candidates WHERE is_risk_event AND strict_is_risk")).scalar()
    print(f"\nStrict pass: {survive}/{tot} positives survived ({survive/tot*100:.0f}%)")


def score_gold(engine):
    human = {}
    with open("data/gold_set.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["llm_is_disruption"].strip() == "1" and r["human_is_disruption"].strip() in ("0", "1"):
                human[r["article_title"]] = int(r["human_is_disruption"])
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT article_title, strict_is_risk FROM disruption_candidates WHERE is_risk_event AND strict_is_risk IS NOT NULL"
        )).fetchall()
    strict = {t: s for t, s in rows if t in human}
    kept = [(t, human[t]) for t, s in strict.items() if s]
    dropped_real = [t for t, s in strict.items() if not s and human[t] == 1]
    if not kept:
        print("No strict-kept gold rows yet.")
        return
    prec = sum(h for _, h in kept) / len(kept)
    print(f"Gold (LLM-positives re-verified): {len(strict)}")
    print(f"  strict KEPT: {len(kept)}  → precision {prec:.0%} (was 40%)")
    print(f"  strict DROPPED a real disruption (lost TP): {len(dropped_real)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--score-gold", action="store_true")
    args = ap.parse_args()
    engine = get_engine()
    add_columns(engine)
    if args.score_gold:
        score_gold(engine)
    else:
        run(engine, args.workers)
        score_gold(engine)


if __name__ == "__main__":
    main()
