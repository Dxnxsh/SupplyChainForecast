"""Postgres URLs: active DB for the app; optional legacy URL (read-only / operator reference)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_DEFAULT = "postgresql://postgres:your_password@localhost:5432/supply_chain_db"

DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING", _DEFAULT)
if DB_CONNECTION_STRING and DB_CONNECTION_STRING.startswith("postgres://"):
    DB_CONNECTION_STRING = DB_CONNECTION_STRING.replace("postgres://", "postgresql://", 1)

DB_CONNECTION_STRING_LEGACY = os.getenv("DB_CONNECTION_STRING_LEGACY") or None
if DB_CONNECTION_STRING_LEGACY and DB_CONNECTION_STRING_LEGACY.startswith("postgres://"):
    DB_CONNECTION_STRING_LEGACY = DB_CONNECTION_STRING_LEGACY.replace("postgres://", "postgresql://", 1)


def get_read_db_url() -> str:
    """CLI reads: DB_READ_URL overrides active URL (e.g. export from legacy while app uses new DB)."""
    db_url = os.getenv("DB_READ_URL") or DB_CONNECTION_STRING
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    return db_url
