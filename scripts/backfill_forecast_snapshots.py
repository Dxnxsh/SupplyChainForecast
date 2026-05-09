#!/usr/bin/env python3
"""Backfill forecast_snapshots for a date range (UTC calendar days)."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.forecast_snapshots import (  # noqa: E402
    SOURCE_SCHEDULED,
    ensure_forecast_snapshots_table,
    snapshot_all_nodes_for_date,
)


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill Prophet forecast snapshots per day per node.")
    p.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD (inclusive)")
    p.add_argument("--to", dest="to_date", required=True, help="End date YYYY-MM-DD (inclusive)")
    args = p.parse_args()
    d0 = parse_date(args.from_date)
    d1 = parse_date(args.to_date)
    if d1 < d0:
        raise SystemExit("--to must be >= --from")

    conn = os.getenv(
        "DB_CONNECTION_STRING",
        "postgresql://postgres:your_password@localhost:5432/supply_chain_db",
    )
    engine = create_engine(conn)
    ensure_forecast_snapshots_table(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    cur = d0
    while cur <= d1:
        print(f"Snapshotting all nodes for {cur} ...", flush=True)
        s = SessionLocal()
        try:
            out = snapshot_all_nodes_for_date(s, cur, SOURCE_SCHEDULED)
            print(f"  saved rows for {out['saved']} nodes; failures: {len(out['failed'])}", flush=True)
            for f in out["failed"][:5]:
                print(f"    - {f['node_name']}: {f['error']}", flush=True)
        finally:
            s.close()
        cur += timedelta(days=1)

    print("Done.", flush=True)


if __name__ == "__main__":
    main()
