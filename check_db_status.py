import argparse
import os
import sys

from sqlalchemy import text

sys.path.append(os.getcwd())

from src.load_to_db import get_db_engine, get_legacy_db_engine


def check_db(engine, label: str) -> None:
    if not engine:
        print(f"{label}: database engine not initialized.")
        return

    with engine.connect() as conn:
        try:
            res = conn.execute(text("SELECT COUNT(*) FROM events")).scalar()
            print(f"{label} — total events: {res}")
            res = conn.execute(text("SELECT COUNT(*) FROM events WHERE temporal_info IS NOT NULL")).scalar()
            print(f"{label} — events with temporal_info: {res}")
            res = conn.execute(text("SELECT COUNT(*) FROM events WHERE ml_risk_label IS NOT NULL")).scalar()
            print(f"{label} — events with ml_risk_label: {res}")
        except Exception as e:
            print(f"{label} — error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect Postgres event counts.")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use DB_CONNECTION_STRING_LEGACY",
    )
    args = parser.parse_args()
    if args.legacy:
        eng = get_legacy_db_engine()
        if not eng:
            print("DB_CONNECTION_STRING_LEGACY is not set or connection failed.")
            sys.exit(1)
        check_db(eng, "Legacy DB")
    else:
        check_db(get_db_engine(), "Active DB")
