"""
Backfill all forecast_snapshots with the new two-stage XGBoost model.
Deletes existing method='xgboost' rows and regenerates for all historical forecast_dates.
"""

import os
import sys
import logging

sys.path.append(os.getcwd())

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from src.db_config import DB_CONNECTION_STRING
from src.forecast_snapshots import snapshot_all_nodes_for_date, METHOD_XGBOOST

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def backfill():
    engine = create_engine(DB_CONNECTION_STRING)

    with Session(engine) as session:
        # Get all existing forecast dates
        existing_dates = session.execute(
            text("SELECT DISTINCT forecast_date FROM forecast_snapshots WHERE method = :m ORDER BY forecast_date"),
            {"m": METHOD_XGBOOST}
        ).fetchall()
        dates = [r[0] for r in existing_dates]
        logger.info(f"Found {len(dates)} existing xgboost snapshot dates to regenerate")

        if not dates:
            logger.info("No existing snapshots to regenerate. Generating for last 30 days...")
            from datetime import date, timedelta
            today = date.today()
            dates = [today - timedelta(days=i) for i in range(30, 0, -1)]

        # Delete all existing xgboost snapshots
        logger.info("Deleting all existing method='xgboost' snapshots...")
        session.execute(text("DELETE FROM forecast_snapshots WHERE method = :m"), {"m": METHOD_XGBOOST})
        session.commit()
        logger.info("Deleted.")

        # Regenerate
        for i, forecast_date in enumerate(dates):
            logger.info(f"[{i+1}/{len(dates)}] Regenerating snapshots for {forecast_date}...")
            result = snapshot_all_nodes_for_date(session, forecast_date, source="backfill", method=METHOD_XGBOOST)
            logger.info(f"  saved={result['saved']}, failed={len(result['failed'])}")
            if result["failed"]:
                for f in result["failed"][:3]:
                    logger.warning(f"    {f['node_name']}: {f['error']}")

    logger.info("Backfill complete.")


if __name__ == "__main__":
    backfill()
