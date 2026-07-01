"""T10.3-T10.5 — LLM-free live ingestion pipeline.

Fetches RSS feeds → sentiment → relevance + theme labeling → DB insert → snapshot rebuild.
No LLM (no gemini_client, openrouter_client, openmodel_client anywhere in this module).

Data flow per cycle:
  RSS feeds → parse → dedup (article_url) → sentiment (FinBERT, signed [-1,1])
  → geocode (optional, GLiNER2+geocoder) → INSERT events
  → relevance P(disruption) ≥ 0.59 ? → theme routing
  → INSERT disruption_candidates (is_risk_event=T, strict_is_risk=T)
  → build_ui_snapshot --as-of <max_date>

Usage:
  venv311/bin/python -m scripts.ingest_live --skip-db        # dry-run, print only
  venv311/bin/python -m scripts.ingest_live --no-geocode     # skip GLiNER2 (faster)
  venv311/bin/python -m scripts.ingest_live --limit 20       # cap articles per cycle
  venv311/bin/python -m scripts.ingest_live --interval 1800  # poll every 30 min
  venv311/bin/python -m scripts.ingest_live                  # one full cycle
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

import feedparser
from sqlalchemy import create_engine, text

from src.db_config import DB_CONNECTION_STRING
from src.sentiment_finbert import batch_analyze_finbert

# ── constants ──────────────────────────────────────────────────────────────────
FEEDS_PATH = "config/rss_feeds.json"
RELEVANCE_PKL = "model_training/relevance_classifier_emb.pkl"
PROTO_PKL = "model_training/theme_prototypes.pkl"
MODEL_EMB = "emb-minilm-logreg"

# Emerging-sectors (see EMERGING_SECTORS_PLAN.md §7). A relevant article whose top-prototype
# cosine similarity is below this is "unrouted" — a candidate for the novelty pool that the
# offline scripts.build_emerging_sectors clusterer discovers new sectors from. Starts equal to
# live_label.TAU_DEFAULT (the routing τ); tune independently once distributions are available.
TAU_NOVEL = 0.30


# ── helpers ────────────────────────────────────────────────────────────────────
def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_timestamp(entry) -> str | None:
    for attr in ("published", "updated"):
        v = getattr(entry, attr, None)
        if v:
            return str(v)
    if getattr(entry, "published_parsed", None):
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", entry.published_parsed)
        except Exception:
            pass
    return None


def load_feeds(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_rss(feeds: list[dict], limit: int | None) -> list[dict]:
    articles: list[dict] = []
    for feed in feeds:
        url = feed.get("url", "")
        source = feed.get("source", "RSS")
        if not url:
            continue
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"  [skip] {source}: fetch error: {e}")
            continue
        if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
            print(f"  [skip] {source}: bozo parse ({getattr(parsed,'bozo_exception','?')})")
            continue
        for entry in parsed.entries or []:
            link = (_strip_html(getattr(entry, "link", None) or getattr(entry, "id", None) or "")).strip()
            if not link or not link.startswith("http"):
                continue
            title = _strip_html(getattr(entry, "title", "") or "")
            summary = _strip_html(
                getattr(entry, "summary", None)
                or getattr(entry, "description", None)
                or ""
            )
            body = summary if summary else title
            ts = _entry_timestamp(entry) or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            articles.append({
                "article_url": link,
                "article_source": source,
                "article_title": title or link,
                "article_timestamp": ts,
                "event_text_segment": body[:12000],
            })
    if limit:
        articles = articles[:limit]
    return articles


def dedup_by_url(conn, articles: list[dict]) -> tuple[list[dict], int]:
    if not articles:
        return [], 0
    urls = [a["article_url"] for a in articles]
    existing = set(
        r[0] for r in conn.execute(
            text("SELECT article_url FROM events WHERE article_url = ANY(:urls)"),
            {"urls": urls},
        ).fetchall()
    )
    fresh = [a for a in articles if a["article_url"] not in existing]
    return fresh, len(articles) - len(fresh)


def add_sentiment(articles: list[dict]) -> None:
    if not articles:
        return
    texts = [
        (a["article_title"] + " " + a["event_text_segment"])[:4000]
        for a in articles
    ]
    results = batch_analyze_finbert(texts)
    for article, r in zip(articles, results):
        article["sentiment_score"] = r["sentiment_score"]    # signed [-1,1]
        article["sentiment_label"] = r["sentiment_label"]   # positive/negative/neutral


def add_geocode(articles: list[dict]) -> None:
    from src.preprocessing import extract_locations_batch
    from src.geocoding import geocode_batch

    texts = [a["event_text_segment"] for a in articles]
    locs_batch = extract_locations_batch(texts)
    loc_strings = [locs[0] for locs in locs_batch if locs]
    coords = geocode_batch(loc_strings)
    for article, locs in zip(articles, locs_batch):
        if locs:
            lat, lon = coords.get(locs[0], (None, None))
            article["latitude"] = lat
            article["longitude"] = lon
        else:
            article.setdefault("latitude", None)
            article.setdefault("longitude", None)


def insert_events(conn, articles: list[dict]) -> list[int]:
    inserted_ids: list[int] = []
    for a in articles:
        row = conn.execute(text("""
            INSERT INTO events (
                article_url, article_source, article_title, article_timestamp,
                event_text_segment, sentiment_score, sentiment_label,
                latitude, longitude,
                potential_event_types, extracted_locations, matched_node,
                risk_score, risk_relevance_score, risk_severity_score
            ) VALUES (
                :url, :source, :title, :ts,
                :body, :sent_score, :sent_label,
                :lat, :lon,
                '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                0.0, 0.0, 0.0
            )
            ON CONFLICT (article_url) DO NOTHING
            RETURNING id
        """), {
            "url": a["article_url"],
            "source": a["article_source"],
            "title": a["article_title"],
            "ts": a["article_timestamp"],
            "body": a["event_text_segment"],
            "sent_score": a.get("sentiment_score"),
            "sent_label": a.get("sentiment_label"),
            "lat": a.get("latitude"),
            "lon": a.get("longitude"),
        }).fetchone()
        a["_db_id"] = row[0] if row else None
        if row:
            inserted_ids.append(row[0])
    return inserted_ids


CANDIDATE_P_THR = 0.75


def _ensure_novelty_columns(conn) -> None:
    """Emerging-sectors P1 (EMERGING_SECTORS_PLAN.md §4.1): additive, idempotent."""
    conn.execute(text("""
        ALTER TABLE disruption_candidates
          ADD COLUMN IF NOT EXISTS top_sim double precision,
          ADD COLUMN IF NOT EXISTS is_unrouted boolean DEFAULT false
    """))


def insert_candidates(conn, articles: list[dict], label_results) -> int:
    n = 0
    from scripts.build_disruption_dataset import THEMES
    for article, result in zip(articles, label_results):
        if not result.relevant or result.P < CANDIDATE_P_THR:
            continue
        themes = [t for t in result.themes if t in THEMES][:2]
        if not themes:
            continue
        is_unrouted = result.top_sim < TAU_NOVEL
        conn.execute(text("""
            INSERT INTO disruption_candidates (
                article_title, article_id, article_url, article_date,
                is_risk_event, strict_is_risk,
                themes, risk_type, confidence, reason,
                model, strict_model,
                top_sim, is_unrouted
            ) VALUES (
                :title, :aid, :url, :adate,
                true, true,
                CAST(:themes AS jsonb), :rtype, :conf, :reason,
                :model, :model,
                :top_sim, :is_unrouted
            )
            ON CONFLICT (article_title) DO NOTHING
        """), {
            "title": article["article_title"],
            "aid": str(article.get("_db_id", "")),
            "url": article["article_url"],
            "adate": _parse_date(article["article_timestamp"]),
            "themes": json.dumps(themes),
            "rtype": result.top_theme,
            "conf": result.P,
            "reason": f"emb-relevance P={result.P:.3f} ≥ 0.59; top_theme_sim={result.top_sim:.3f}",
            "model": MODEL_EMB,
            "top_sim": result.top_sim,
            "is_unrouted": is_unrouted,
        })
        n += 1
    return n


def _parse_date(ts_str: str) -> str | None:
    if not ts_str:
        return None
    # ISO and common variants
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(ts_str[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # RFC 2822 (standard RSS): "Sun, 29 Jun 2025 12:34:00 GMT"
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(ts_str).strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def build_feed_block(conn, articles: list[dict], label_results) -> list[dict]:
    """Build the feed[] entries for the snapshot (relevant + sample of scored-but-rejected)."""
    feed = []
    from scripts.train_predictor import TARGET_KEYWORDS, TARGETS

    # Map theme → sector key
    theme_to_sector: dict[str, str] = {}
    for sector, themes in TARGETS.items():
        for t in themes:
            theme_to_sector[t] = sector

    for article, result in zip(articles, label_results):
        entry: dict = {
            "ts": article["article_timestamp"],
            "source": article["article_source"],
            "title": article["article_title"][:120],
            "url": article["article_url"],
            "relevance_p": result.P,
            "relevant": result.relevant,
            "theme": result.top_theme,
            "sentiment_score": round(article.get("sentiment_score") or 0.0, 3),
            "sector_key": theme_to_sector.get(result.top_theme) if result.top_theme else None,
        }
        feed.append(entry)
    return feed


def rebuild_snapshot(max_date: str | None = None) -> None:
    cmd = [sys.executable, "-m", "scripts.build_ui_snapshot"]
    if max_date:
        cmd += ["--as-of", max_date]
    print(f"  Rebuilding snapshot (as-of={max_date or 'auto'}) …")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [warn] snapshot rebuild failed: {result.stderr[:300]}")
    else:
        for line in result.stdout.strip().splitlines()[-4:]:
            print(f"  {line}")


def run_cycle(
    *,
    skip_db: bool,
    geocode: bool,
    limit: int | None,
    verbose: bool,
) -> dict:
    feeds = load_feeds(FEEDS_PATH)
    print(f"Fetching {len(feeds)} feeds …")
    articles = fetch_rss(feeds, limit)
    print(f"  fetched {len(articles)} articles")

    if not articles:
        return {"fetched": 0, "new": 0, "relevant": 0, "candidates": 0}

    engine = create_engine(DB_CONNECTION_STRING)
    with engine.begin() as conn:
        articles, n_skipped = dedup_by_url(conn, articles)
    print(f"  {n_skipped} already in DB → {len(articles)} new to process")

    if not articles:
        return {"fetched": len(articles) + n_skipped, "new": 0, "relevant": 0, "candidates": 0}

    # Sentiment (FinBERT, signed [-1,1] — matches corpus convention)
    print(f"  Sentiment (FinBERT) on {len(articles)} articles …")
    add_sentiment(articles)

    # Geocode (optional — heavy, only feeds map dots)
    if geocode:
        print(f"  Geocoding (GLiNER2) …")
        try:
            add_geocode(articles)
        except Exception as e:
            print(f"  [warn] geocode failed (non-fatal): {e}")
    else:
        for a in articles:
            a.setdefault("latitude", None)
            a.setdefault("longitude", None)

    # Relevance + theme routing (single MiniLM encode)
    from scripts.live_label import Labeler
    print(f"  Labeling (relevance + theme routing) …")
    labeler = Labeler()
    texts = [(a["article_title"] + " " + a["event_text_segment"][:700]).strip() for a in articles]
    label_results = labeler.label_batch(texts)

    n_relevant = sum(1 for r in label_results if r.relevant)
    print(f"  → {n_relevant}/{len(articles)} relevant (P≥0.59)")

    if verbose:
        for a, r in zip(articles, label_results):
            marker = "✓" if r.relevant else "·"
            print(f"  {marker} P={r.P:.3f} {r.themes or '—'!s:<40} {a['article_title'][:60]}")

    if skip_db:
        print("\n[--skip-db] Dry run — nothing written.")
        return {"fetched": len(articles) + n_skipped, "new": len(articles),
                "relevant": n_relevant, "candidates": 0}

    # DB writes
    with engine.begin() as conn:
        _ensure_novelty_columns(conn)
        inserted_ids = insert_events(conn, articles)
        n_events = len(inserted_ids)
        n_candidates = insert_candidates(conn, articles, label_results)
        feed_entries = build_feed_block(conn, articles, label_results)

    print(f"  DB: inserted {n_events} events, {n_candidates} disruption_candidates")

    # Persist feed[] to snapshot-side file for build_ui_snapshot to pick up
    os.makedirs("data", exist_ok=True)
    feed_path = "data/live_feed.json"
    existing_feed: list[dict] = []
    if os.path.exists(feed_path):
        try:
            existing_feed = json.load(open(feed_path))
        except Exception:
            pass
    # prepend new entries; cap at 200
    merged = feed_entries + existing_feed
    merged = merged[:200]
    with open(feed_path, "w") as f:
        json.dump(merged, f, indent=2)

    # Rebuild snapshot
    max_date: str | None = None
    if inserted_ids:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT MAX(article_timestamp)::date FROM events"
            )).fetchone()
            max_date = str(row[0]) if row and row[0] else None
    rebuild_snapshot(max_date)

    return {"fetched": len(articles) + n_skipped, "new": n_events,
            "relevant": n_relevant, "candidates": n_candidates}


def main():
    ap = argparse.ArgumentParser(description="LLM-free live ingestion pipeline (T10)")
    ap.add_argument("--interval", type=int, default=0,
                    help="Re-run every N seconds (0 = run once)")
    ap.add_argument("--skip-db", action="store_true",
                    help="Dry-run: fetch, score, print — no DB writes")
    ap.add_argument("--no-geocode", action="store_true",
                    help="Skip GLiNER2 geocoding (faster)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap articles fetched per cycle")
    ap.add_argument("--verbose", action="store_true",
                    help="Print per-article relevance scores")
    args = ap.parse_args()

    # No-LLM assert: no actual import of any LLM client in this file
    import_lines = [
        ln for ln in Path(__file__).read_text().splitlines()
        if ln.strip().startswith(("import ", "from ")) and not ln.strip().startswith("#")
    ]
    import_block = "\n".join(import_lines)
    for bad in ("gemini_client", "openrouter_client", "openmodel_client"):
        assert bad not in import_block, f"LLM import found in ingest_live.py: {bad}"

    if args.interval > 0:
        print(f"Poll mode: interval={args.interval}s  Ctrl-C to stop")
        while True:
            try:
                t0 = time.time()
                summary = run_cycle(
                    skip_db=args.skip_db, geocode=not args.no_geocode,
                    limit=args.limit, verbose=args.verbose,
                )
                elapsed = time.time() - t0
                print(f"\nCycle done in {elapsed:.0f}s: {summary}")
                time.sleep(max(0, args.interval - elapsed))
            except KeyboardInterrupt:
                print("\nStopped.")
                break
            except Exception as e:
                print(f"Cycle error (continuing): {e}")
                time.sleep(60)
    else:
        summary = run_cycle(
            skip_db=args.skip_db, geocode=not args.no_geocode,
            limit=args.limit, verbose=args.verbose,
        )
        print(f"\nDone: {summary}")


if __name__ == "__main__":
    main()
