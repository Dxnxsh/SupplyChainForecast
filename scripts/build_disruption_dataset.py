"""Build the clean theme-level disruption dataset from the news corpus (the cascade).

Pipeline (resumable):
  RAW events  --keyword pre-filter-->  candidates  --LLM relevance+linking-->  disruption_candidates

The LLM verdict for EVERY candidate is stored (relevant or not), so:
  - re-running skips already-processed titles (survives interruptions / rate-limit windows),
  - the EVENT layer = rows WHERE is_risk_event AND themes is non-empty,
  - rejected candidates are retained (useful as hard negatives / audit).

Usage:
  venv311/bin/python -m scripts.build_disruption_dataset --limit 50      # process a chunk
  venv311/bin/python -m scripts.build_disruption_dataset                 # process all remaining
  venv311/bin/python -m scripts.build_disruption_dataset --report        # dataset stats only

Requires OPENMODEL_API_KEY in .env. Paces calls (per-user RPM limit); ~8s/candidate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

from sqlalchemy import create_engine, text

from src.db_config import get_read_db_url
from src.gemini_client import DEFAULT_MODEL, generate

THEMES = [
    "Taiwan semiconductors", "China electronics manufacturing", "South Korea memory chips",
    "Japan electronic components", "US West Coast ports", "US freight & trucking",
    "European auto supply chain", "Lithium & battery materials",
    "Strait of Hormuz / Gulf shipping", "Red Sea / Suez shipping",
    "Rare earths & export controls", "Global semiconductor supply",
]

CANDIDATE_RE = (  # middle pool: tight disruption terms + non-noisy disaster/logistics terms
    r"(halt|halts|halted|suspend|suspended|stoppage)[a-z ]{0,15}production|"
    r"production[a-z ]{0,15}(halt|suspend|stopp)|"
    r"(factory|plant|refinery|warehouse)[a-z ]{0,12}(fire|explosion|blast)|"
    r"port[a-z ]{0,12}(strike|closure|closed|congestion|shut)|dockworker|longshore|"
    r"force majeure|"
    r"(chip|semiconductor|component|memory|wafer)[a-z ]{0,10}shortage|"
    r"\m(earthquake|typhoon|hurricane|cyclone|tsunami)\M|"
    r"\m(flood|flooding|landslide|wildfire|drought|mudslide)\M|blockade|"
    r"\m(shutdown|shut down)\M|derail|evacuat[a-z]*|oil spill|chemical spill|"
    r"\m(blackout|power outage)\M"
)

SYSTEM = (
    "You are a supply-chain risk analyst. Given a news article and a list of supply-chain "
    "THEMES (regions / commodities / trade routes), decide whether the article reports a real "
    "SUPPLY-CHAIN RISK EVENT OR DEVELOPMENT relevant to one or more themes. Qualifying events "
    "include: natural disaster, industrial accident, strike/labor action, armed conflict or "
    "blockade affecting shipping, port congestion/closure, transport-route disruption, "
    "tariff / sanction / export-control action, major component or material shortage, or a "
    "regulatory action with real operational impact on supply. "
    "EXCLUDE pure stock/market price movements, earnings, product launches, personnel news / "
    "awards, opinion, sports, and routine politics with no supply-chain impact. "
    "Be disciplined: it must be an actual risk-relevant event or development affecting supply, "
    "not routine market or business-as-usual news."
)

USER_TMPL = """Supply-chain themes (only these are valid; use exact names):
{themes}

Article title: {title}
Article text: {body}

Return ONLY JSON, no prose:
{{"is_risk_event": true/false, "relevant_themes": ["exact_name", ...], "risk_type": "short label", "confidence": 0.0-1.0, "reason": "one short sentence"}}
If not a real supply-chain risk event/development relevant to a listed theme, use is_risk_event=false, relevant_themes=[]."""

BLOB = "lower(coalesce(article_title,'') || ' ' || coalesce(event_text_segment,''))"


def get_engine():
    return create_engine(get_read_db_url())


def create_tables(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS disruption_candidates (
                article_title   TEXT PRIMARY KEY,
                article_id      TEXT,
                article_url     TEXT,
                article_date    DATE,
                is_risk_event   BOOLEAN NOT NULL,
                themes          JSONB NOT NULL DEFAULT '[]'::jsonb,
                risk_type       TEXT,
                confidence      DOUBLE PRECISION,
                reason          TEXT,
                model           TEXT,
                processed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """))


def fetch_unprocessed(conn, batch):
    q = text(f"""
        SELECT DISTINCT ON (e.article_title)
               e.article_title, e.id::text, e.article_url, e.article_timestamp::date,
               LEFT(e.event_text_segment, 1200)
        FROM events e
        WHERE e.article_title IS NOT NULL
          AND {BLOB} ~ :pat
          AND e.article_title NOT IN (SELECT article_title FROM disruption_candidates)
        ORDER BY e.article_title, e.id
        LIMIT :batch
    """)
    return conn.execute(q, {"pat": CANDIDATE_RE, "batch": batch}).fetchall()


def fetch_body(conn, title):
    r = conn.execute(
        text("SELECT LEFT(event_text_segment, 1200) FROM events WHERE article_title = :t LIMIT 1"),
        {"t": title},
    ).fetchone()
    return (r[0] if r else "") or ""


def parse_json(txt):
    txt = re.sub(r"^```(json)?|```$", "", txt.strip(), flags=re.MULTILINE).strip()
    s, e = txt.find("{"), txt.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(txt[s:e + 1])
    except json.JSONDecodeError:
        return None


def insert_verdict(conn, title, aid, url, adate, v, model):
    themes = [t for t in (v.get("relevant_themes") or []) if t in THEMES]
    is_risk = bool(v.get("is_risk_event")) and bool(themes)
    conn.execute(text("""
        INSERT INTO disruption_candidates
            (article_title, article_id, article_url, article_date, is_risk_event, themes,
             risk_type, confidence, reason, model)
        VALUES (:t, :aid, :url, :adate, :is_risk, :themes, :rtype, :conf, :reason, :model)
        ON CONFLICT (article_title) DO NOTHING
    """), {
        "t": title, "aid": aid, "url": url, "adate": adate, "is_risk": is_risk,
        "themes": json.dumps(themes), "rtype": v.get("risk_type"),
        "conf": v.get("confidence"), "reason": (v.get("reason") or "")[:500], "model": model,
    })


def report(engine):
    with engine.connect() as conn:
        tot = conn.execute(text("SELECT COUNT(*) FROM disruption_candidates")).scalar() or 0
        ev = conn.execute(text("SELECT COUNT(*) FROM disruption_candidates WHERE is_risk_event")).scalar() or 0
        remaining = conn.execute(text(f"""
            SELECT COUNT(DISTINCT article_title) FROM events e
            WHERE e.article_title IS NOT NULL AND {BLOB} ~ :pat
              AND e.article_title NOT IN (SELECT article_title FROM disruption_candidates)
        """), {"pat": CANDIDATE_RE}).scalar() or 0
        print(f"processed={tot}  confirmed_events={ev}  precision={ev/tot*100 if tot else 0:.1f}%  remaining={remaining}")
        if ev:
            print("per-theme events:")
            rows = conn.execute(text("""
                SELECT t AS theme, COUNT(*) c
                FROM disruption_candidates, jsonb_array_elements_text(themes) t
                WHERE is_risk_event GROUP BY t ORDER BY c DESC
            """)).fetchall()
            for r in rows:
                print(f"  {r[0]:<34} {r[1]}")
            print("events over time (by month):")
            rows = conn.execute(text("""
                SELECT to_char(article_date,'YYYY-MM') m, COUNT(*) c
                FROM disruption_candidates WHERE is_risk_event AND article_date IS NOT NULL
                GROUP BY m ORDER BY m
            """)).fetchall()
            for r in rows:
                print(f"  {r[0]}  {r[1]}")


CIRCUIT_BREAK = 20  # consecutive LLM errors → abort (out of credit/quota)


def _classify(row, themes_str):
    """Worker: call the LLM for one candidate. Returns (row, verdict_or_None, is_error)."""
    title, aid, url, adate, body = row
    user = USER_TMPL.format(themes=themes_str, title=title, body=body or "")
    try:
        txt = generate(SYSTEM, user)
    except Exception as exc:
        print(f"  LLM error ({title[:40]}…): {exc}")
        return row, None, True
    return row, parse_json(txt), False


def run(engine, limit, workers):
    themes_str = ", ".join(THEMES)
    with engine.connect() as conn:
        batch = fetch_unprocessed(conn, limit if limit else 100000)
    total = len(batch)
    print(f"To process: {total} candidate titles (workers={workers})")
    done = events = 0
    consec_err = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_classify, r, themes_str) for r in batch]
        for i, fut in enumerate(as_completed(futures), 1):
            row, v, err = fut.result()
            if err:
                consec_err += 1
                if consec_err >= CIRCUIT_BREAK:
                    print(f"\nCircuit breaker: {CIRCUIT_BREAK} consecutive LLM errors "
                          f"(out of credit/quota?). Stopping — rerun to resume; progress is saved.")
                    for f in futures:
                        f.cancel()
                    break
                continue
            consec_err = 0
            if v is None:
                continue
            title, aid, url, adate, _ = row
            with engine.begin() as conn:
                insert_verdict(conn, title, aid, url, adate, v, DEFAULT_MODEL)
            done += 1
            if bool(v.get("is_risk_event")) and [t for t in (v.get("relevant_themes") or []) if t in THEMES]:
                events += 1
            if i % 50 == 0:
                print(f"[{i}/{total}] processed={done} events={events}")
    print(f"Done this run: processed={done} new events={events}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="process at most N candidates (0 = all remaining)")
    ap.add_argument("--workers", type=int, default=12, help="concurrent LLM requests")
    ap.add_argument("--report", action="store_true", help="print dataset stats and exit")
    args = ap.parse_args()

    engine = get_engine()
    create_tables(engine)
    if args.report:
        report(engine)
        return
    run(engine, args.limit, args.workers)
    print("\n--- dataset stats ---")
    report(engine)


if __name__ == "__main__":
    main()
