"""Postgres URLs: active DB for the app; optional legacy URL (read-only / operator reference)."""

from __future__ import annotations

import os

_DEFAULT = "postgresql://postgres:your_password@localhost:5432/supply_chain_db"

DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING", _DEFAULT)
DB_CONNECTION_STRING_LEGACY = os.getenv("DB_CONNECTION_STRING_LEGACY") or None


def get_read_db_url() -> str:
    """CLI reads: DB_READ_URL overrides active URL (e.g. export from legacy while app uses new DB)."""
    return os.getenv("DB_READ_URL") or DB_CONNECTION_STRING
