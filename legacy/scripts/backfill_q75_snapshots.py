"""
Backfill forecast_snapshots with the q75 severity model variant.
Uses method='xgboost_q75' so both can coexist in the DB for comparison.
"""

import os
import sys
import logging

sys.path.append(os.getcwd())

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from src.db_config import DB_CONNECTION_STRING
from src.forecast_snapshots import snapshot_all_nodes_for_date, METHOD_XGBOOST, METHOD_XGBOOST_Q75

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def backfill():
    engine = create_engine(DB_CONNECTION_STRING)

    with Session(engine) as session:
        # Use the same dates that the mean model was backfilled on
        existing_dates = session.execute(
            text("SELECT DISTINCT forecast_date FROM forecast_snapshots WHERE method = :m ORDER BY forecast_date"),
            {"m": METHOD_XGBOOST}
        ).fetchall()
        dates = [r[0] for r in existing_dates]

        if not dates:
            logger.info("No xgboost snapshots found — run backfill_two_stage_snapshots.py first.")
            return

        logger.info(f"Backfilling {len(dates)} dates with method='{METHOD_XGBOOST_Q75}'...")

        # Delete existing q75 snapshots
        deleted = session.execute(
            text("DELETE FROM forecast_snapshots WHERE method = :m"),
            {"m": METHOD_XGBOOST_Q75}
        )
        session.commit()
        logger.info(f"Deleted {deleted.rowcount} existing q75 rows.")

        for i, forecast_date in enumerate(dates):
            logger.info(f"[{i+1}/{len(dates)}] {forecast_date}...")
            result = snapshot_all_nodes_for_date(session, forecast_date, source="backfill", method=METHOD_XGBOOST_Q75)
            logger.info(f"  saved={result['saved']}, failed={len(result['failed'])}")

    logger.info("Q75 backfill complete.")


if __name__ == "__main__":
    backfill()
