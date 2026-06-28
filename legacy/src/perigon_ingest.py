"""
Fetch historical and recent news from the Perigon API and push through the
standard supply-chain scoring + enrichment pipeline.

Budget: 150 requests / calendar month, 25 articles / request → 3,750 articles max.
A ledger at data/perigon_budget.json tracks usage and records completed runs.

Seen-URL cache at data/perigon_seen_urls.txt prevents re-requesting articles
already fetched from Perigon. When every URL on a fetched page is in the cache,
pagination stops early for that node.

Usage:
  python -m src.perigon_ingest --from 2026-03-01 --to 2026-06-23
  python -m src.perigon_ingest --status          # show budget + run history
  python -m src.perigon_ingest --from 2026-05-01 --dry-run
  python -m src.perigon_ingest --from 2026-05-01 --force   # re-run after completion

Environment:
  PERIGON_API_KEY   (required)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env from project root
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

PERIGON_API_BASE = "https://api.perigon.io/v1/articles/all"
PAGE_SIZE = 25
MONTHLY_REQUEST_LIMIT = 150
BUDGET_FILE = PROJECT_ROOT / "data" / "perigon_budget.json"
SEEN_URLS_FILE = PROJECT_ROOT / "data" / "perigon_seen_urls.txt"

# Supplier → Perigon search terms (derived from match_events_to_nodes anchor keywords).
# Each list is OR'd into a single Perigon q= boolean query for that node.
# Ordered by criticality descending so the budget favours critical nodes.
NODE_QUERIES: list[tuple[str, list[str]]] = [
    ("TSMC_Hsinchu",          ["tsmc", "hsinchu", "taiwan strait", "wafer fab"]),
    ("Foxconn_Zhengzhou",     ["foxconn", "zhengzhou", "hon hai"]),
    ("Port_of_Long_Beach",    ["long beach port", "los angeles port", "la port", "california port", "port of long beach"]),
    ("CATL_Ningde",           ["catl", "ningde", "ev battery"]),
    ("Pegatron_Shanghai",     ["pegatron", "shanghai fab"]),
    ("Samsung_Display_Seoul", ["samsung display", "samsung oled"]),
    ("SK_Hynix_Icheon",       ["hynix", "icheon fab"]),
    ("Broadcom_San_Jose",     ["broadcom"]),
    ("Kioxia_Tokyo",          ["kioxia"]),
    ("Luxshare_Bac_Giang",    ["luxshare", "bac giang"]),
    ("GoerTek_Bac_Ninh",      ["goertek", "bac ninh"]),
    ("LG_Energy_Nanjing",     ["lg energy", "nanjing battery"]),
    ("Panasonic_Nevada",      ["panasonic gigafactory", "panasonic nevada"]),
    ("Bosch_Stuttgart",       ["bosch stuttgart", "bosch sensor"]),
    ("Ganfeng_Lithium_Xinyu", ["ganfeng lithium", "xinyu"]),
    ("Albemarle_Chile",       ["albemarle", "atacama", "lithium brine", "chilean lithium"]),
    ("Tesla_Berlin",          ["tesla gigafactory", "tesla berlin", "tesla brandenburg"]),
    ("Sony_Kumamoto",         ["sony semiconductor", "sony sensor", "kumamoto fab"]),
    ("Corning_Kentucky",      ["corning glass", "harrodsburg"]),
    ("Micron_Boise",          ["micron", "boise fab"]),
    ("Cirrus_Logic_Austin",   ["cirrus logic"]),
    ("NXP_Eindhoven",         ["nxp", "eindhoven"]),
    ("STMicro_Geneva",        ["stmicroelectronics", "geneva fab"]),
    ("Inventec_Taipei",       ["inventec"]),
    ("Amkor_Manila",          ["amkor", "manila packaging"]),
    ("Murata_Kyoto",          ["murata"]),
    ("Varta_Ellwangen",       ["varta", "ellwangen"]),
    ("ZF_Friedrichshafen",    ["zf friedrichshafen", "zf powertrain"]),
    ("Brembo_Bergamo",        ["brembo brake"]),
    ("Valeo_Paris",           ["valeo hvac", "valeo thermal"]),
]


# ── Budget ledger ─────────────────────────────────────────────────────────────

def _load_budget() -> dict:
    if BUDGET_FILE.exists():
        try:
            return json.loads(BUDGET_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_budget(ledger: dict) -> None:
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_FILE.write_text(json.dumps(ledger, indent=2))


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def budget_used() -> int:
    return _load_budget().get(_month_key(), 0)


def budget_remaining() -> int:
    return max(0, MONTHLY_REQUEST_LIMIT - budget_used())


def _charge(n: int) -> None:
    ledger = _load_budget()
    key = _month_key()
    ledger[key] = ledger.get(key, 0) + n
    _save_budget(ledger)


def _record_completed_run(from_date: str, to_date: str, n_events: int) -> None:
    ledger = _load_budget()
    runs = ledger.setdefault("completed_runs", [])
    runs.append({
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "from_date": from_date,
        "to_date": to_date,
        "events_ingested": n_events,
    })
    _save_budget(ledger)


def _get_completed_runs() -> list[dict]:
    return _load_budget().get("completed_runs", [])


# ── Seen-URL cache ────────────────────────────────────────────────────────────

def _load_seen_urls() -> set[str]:
    if SEEN_URLS_FILE.exists():
        return set(SEEN_URLS_FILE.read_text().splitlines())
    return set()


def _append_seen_urls(urls: set[str]) -> None:
    if not urls:
        return
    SEEN_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SEEN_URLS_FILE.open("a") as f:
        for url in urls:
            f.write(url + "\n")


# ── API fetch ─────────────────────────────────────────────────────────────────

def _fetch_page(api_key: str, q: str, from_date: str, to_date: str, page: int) -> dict:
    params = {
        "q": q,
        "from": from_date,
        "to": to_date,
        "sortBy": "date",
        "language": "en",
        "showReprints": "false",
        "size": PAGE_SIZE,
        "page": page,
        "apiKey": api_key,
    }
    resp = requests.get(PERIGON_API_BASE, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_articles_for_node(
    api_key: str,
    node_name: str,
    keywords: list[str],
    from_date: str,
    to_date: str,
    max_requests: int,
    seen_urls: set[str],
) -> Iterator[dict]:
    """
    Yield raw Perigon article dicts for one supplier node.

    Early-stops pagination when every URL on a fetched page is already in
    seen_urls — those pages and everything older are already cached locally.
    """
    q = " OR ".join(f'"{kw}"' if " " in kw else kw for kw in keywords)
    requests_used = 0
    page = 0

    while requests_used < max_requests:
        data = _fetch_page(api_key, q, from_date, to_date, page)
        _charge(1)
        requests_used += 1

        articles = data.get("articles") or []
        if not articles:
            break

        page_urls = {(a.get("url") or "").strip() for a in articles if a.get("url")}
        all_seen = page_urls and page_urls.issubset(seen_urls)

        if all_seen:
            # Results are date-sorted newest-first; if the entire page is cached,
            # all older pages will also be cached — stop paginating.
            break

        for article in articles:
            url = (article.get("url") or "").strip()
            if url and url not in seen_urls:
                yield article

        num_results = data.get("numResults") or 0
        fetched_so_far = (page + 1) * PAGE_SIZE
        if fetched_so_far >= num_results:
            break

        page += 1
        time.sleep(0.3)


# ── Article → pipeline event ──────────────────────────────────────────────────

def perigon_article_to_event(article: dict, vectorizer, model, label_encoder) -> dict | None:
    from src.rss_ingest import build_scored_event_dict

    url = (article.get("url") or "").strip()
    title = (article.get("title") or "").strip()
    description = (article.get("description") or "").strip()
    content = (article.get("content") or "").strip()
    source = (article.get("source") or {}).get("domain") or "perigon"
    pub_date = article.get("pubDate") or article.get("addDate") or ""

    body = content or description
    text_segment = f"{title}. {body}".strip() if body else title

    return build_scored_event_dict(
        article_url=url,
        article_source=source,
        article_title=title,
        article_timestamp=pub_date,
        event_text_segment=text_segment,
        vectorizer=vectorizer,
        model=model,
        label_encoder=label_encoder,
    )


# ── Main ingest function ──────────────────────────────────────────────────────

def run_perigon_ingest(
    from_date: str,
    to_date: str,
    *,
    api_key: str,
    limit: int | None = None,
    dry_run: bool = False,
    skip_temporal: bool = False,
    nodes: list[str] | None = None,
    force: bool = False,
) -> int:
    # One-time guard
    completed_runs = _get_completed_runs()
    if completed_runs and not force and not dry_run:
        last = completed_runs[-1]
        print(
            f"⚠️  Perigon ingest has already been run once "
            f"(completed {last['completed_at'][:10]}, "
            f"{last['events_ingested']} events, "
            f"{last['from_date']} → {last['to_date']})."
        )
        print("   Pass --force to run again.")
        return 0

    remaining = budget_remaining()
    if remaining == 0:
        print(f"❌ Monthly Perigon budget exhausted ({MONTHLY_REQUEST_LIMIT} requests used). Try again next month.")
        return 0

    print(f"Perigon budget: {budget_used()}/{MONTHLY_REQUEST_LIMIT} requests used this month ({remaining} remaining).")

    seen_urls = _load_seen_urls()
    print(f"Seen-URL cache: {len(seen_urls)} URLs already fetched from Perigon.")

    from src.rss_ingest import (
        enrich_events_for_db,
        load_classifier,
        load_disruption_classifier,
        load_impact_regressor,
    )

    legacy_path = os.getenv("ML_CLASSIFIER_PATH", "model_training/classifier.pkl")
    disruption_path = os.getenv("DISRUPTION_CLASSIFIER_PATH", "model_training/disruption_classifier.pkl")
    impact_path = os.getenv("IMPACT_REGRESSOR_PATH", "model_training/impact_regressor_v2.pkl")

    vectorizer, model, label_encoder = load_classifier(legacy_path)
    disruption_payload = load_disruption_classifier(disruption_path)
    impact_payload = load_impact_regressor(impact_path)

    node_filter = set(nodes) if nodes else None
    query_list = [(n, kws) for n, kws in NODE_QUERIES if node_filter is None or n in node_filter]

    requests_per_node = max(1, remaining // len(query_list)) if query_list else 0
    requests_per_node = min(requests_per_node, remaining)

    all_events: list[dict] = []
    newly_seen: set[str] = set()

    for node_name, keywords in query_list:
        if budget_remaining() == 0:
            print(f"⚠️  Budget exhausted mid-run. Stopping at {node_name}.")
            break

        cap = min(requests_per_node, budget_remaining())
        print(f"  [{node_name}] fetching (up to {cap} request(s), {cap * PAGE_SIZE} articles)…")

        node_events: list[dict] = []
        try:
            for article in fetch_articles_for_node(
                api_key, node_name, keywords, from_date, to_date, cap, seen_urls
            ):
                url = (article.get("url") or "").strip()
                if url:
                    newly_seen.add(url)
                ev = perigon_article_to_event(article, vectorizer, model, label_encoder)
                if ev:
                    node_events.append(ev)
                if limit is not None and (len(all_events) + len(node_events)) >= limit:
                    break
        except requests.HTTPError as exc:
            print(f"  ⚠️  HTTP error for {node_name}: {exc}. Skipping.")
            continue

        print(f"    → {len(node_events)} new article(s) scored")
        all_events.extend(node_events)

        if limit is not None and len(all_events) >= limit:
            all_events = all_events[:limit]
            break

    # Always persist newly seen URLs (even on dry-run) so re-runs don't re-fetch
    _append_seen_urls(newly_seen)
    if newly_seen:
        print(f"Cached {len(newly_seen)} new URL(s) in seen-URL cache.")

    if not all_events:
        print("No new articles to ingest.")
        return 0

    # Deduplicate against DB
    if not dry_run:
        from src.load_to_db import filter_new_events_by_url, get_db_engine
        engine = get_db_engine()
        if engine:
            all_events, nskip = filter_new_events_by_url(engine, all_events)
            if nskip:
                print(f"Skipped {nskip} article(s) already in database.")

    if not all_events:
        print("All articles already in database.")
        _record_completed_run(from_date, to_date, 0)
        return 0

    print(f"Enriching {len(all_events)} article(s)…")
    enrich_events_for_db(
        all_events,
        disruption_payload,
        impact_payload,
        is_background=False,
        skip_temporal=skip_temporal,
        verbose=True,
    )

    if not skip_temporal:
        try:
            from src.temporal_extraction import enrich_events_with_temporal_data
            all_events[:] = enrich_events_with_temporal_data(all_events)
        except Exception as exc:
            print(f"⚠️  Temporal enrichment failed (non-fatal): {exc}")

    if dry_run:
        for ev in all_events[:20]:
            print(
                f"  [{ev.get('ml_risk_label','?')}] node={ev.get('matched_node')} "
                f"{(ev.get('article_title') or '')[:80]}"
            )
        if len(all_events) > 20:
            print(f"  … and {len(all_events) - 20} more")
        print(f"Dry-run: {len(all_events)} event(s) prepared, not written.")
        return len(all_events)

    from src.load_to_db import create_tables, get_db_engine, upsert_events
    engine = get_db_engine()
    if not engine:
        print("❌ Database engine not available.")
        return 0
    create_tables(engine)
    upsert_events(engine, all_events, recompute_supplier_scores=True)
    print(f"✅ Upserted {len(all_events)} event(s) from Perigon.")

    _record_completed_run(from_date, to_date, len(all_events))

    try:
        from sqlalchemy.orm import sessionmaker
        from src.forecast_snapshots import snapshot_all_nodes_for_date, SOURCE_SCHEDULED
        SessionLocal = sessionmaker(bind=engine)
        with SessionLocal() as sess:
            result = snapshot_all_nodes_for_date(sess, date.today(), source=SOURCE_SCHEDULED, method="xgboost")
        print(f"✅ Refreshed XGBoost forecast snapshots (saved: {result['saved']}, failed: {len(result['failed'])}).")
    except Exception as exc:
        print(f"⚠️  Forecast snapshot refresh failed (non-fatal): {exc}")

    return len(all_events)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _default_to() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _default_from() -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")


def main() -> None:
    parser = argparse.ArgumentParser(description="One-time historical news backfill from Perigon API.")
    parser.add_argument("--from", dest="from_date", default=_default_from(),
                        help="Start date YYYY-MM-DD (default: 90 days ago)")
    parser.add_argument("--to", dest="to_date", default=_default_to(),
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max articles to process across all nodes")
    parser.add_argument("--dry-run", action="store_true",
                        help="Score and enrich but do not write to database")
    parser.add_argument("--skip-temporal", action="store_true",
                        help="Skip spaCy temporal extraction (faster)")
    parser.add_argument("--nodes", nargs="+", metavar="NODE",
                        help="Restrict to specific supplier node names")
    parser.add_argument("--force", action="store_true",
                        help="Run even if a completed run already exists")
    parser.add_argument("--status", action="store_true",
                        help="Print budget and run history, then exit")
    args = parser.parse_args()

    if args.status:
        used = budget_used()
        remaining = budget_remaining()
        print(f"Perigon budget ({_month_key()}): {used}/{MONTHLY_REQUEST_LIMIT} requests used, {remaining} remaining.")
        print(f"  ≈ {remaining * PAGE_SIZE} articles remaining this month.")
        runs = _get_completed_runs()
        if runs:
            print(f"\nCompleted runs ({len(runs)}):")
            for r in runs:
                print(f"  {r['completed_at'][:19]}  {r['from_date']} → {r['to_date']}  ({r['events_ingested']} events)")
        else:
            print("\nNo completed runs yet.")
        seen = _load_seen_urls()
        print(f"\nSeen-URL cache: {len(seen)} URLs stored in {SEEN_URLS_FILE.relative_to(PROJECT_ROOT)}")
        return

    api_key = os.getenv("PERIGON_API_KEY", "").strip()
    if not api_key:
        print("❌ PERIGON_API_KEY environment variable not set.")
        sys.exit(1)

    n = run_perigon_ingest(
        from_date=args.from_date,
        to_date=args.to_date,
        api_key=api_key,
        limit=args.limit,
        dry_run=args.dry_run,
        skip_temporal=args.skip_temporal,
        nodes=args.nodes,
        force=args.force,
    )
    print(f"Done. {n} event(s) {'prepared' if args.dry_run else 'ingested'}.")


if __name__ == "__main__":
    main()
