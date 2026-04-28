# src/load_to_db.py

import json
import os
from sqlalchemy import create_engine, text, Column, Integer, String, Float, DateTime, MetaData, Table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import pytz

# --- Configuration ---
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING", "postgresql://postgres:your_password@localhost:5432/supply_chain_db")

# --- Supplier Nodes Data with Criticality ---
SUPPLIER_NODES = {
    "TSMC_Hsinchu": {"latitude": 24.8016, "longitude": 120.9716, "country": "Taiwan", "criticality": 5},
    "Foxconn_Zhengzhou": {"latitude": 34.7466, "longitude": 113.6253, "country": "China", "criticality": 5},
    "Port_of_Long_Beach": {"latitude": 33.7542, "longitude": -118.2165, "country": "USA", "criticality": 4},
    "Albemarle_Chile": {"latitude": -23.5869, "longitude": -68.1533, "country": "Chile", "criticality": 3},
    "CATL_Ningde": {"latitude": 26.6577, "longitude": 119.5262, "country": "China", "criticality": 4},
    "Tesla_Berlin": {"latitude": 52.4045, "longitude": 13.7845, "country": "Germany", "criticality": 3},
    # Add more nodes here if needed, along with their criticality
}

def get_db_engine():
    """Establishes and returns a database engine."""
    try:
        engine = create_engine(DB_CONNECTION_STRING)
        with engine.connect() as connection:
            print("✅ Database connection successful.")
        return engine
    except SQLAlchemyError as e:
        print(f"❌ Error connecting to the database: {e}")
        return None

def create_tables(engine):
    """Creates the 'suppliers' and 'events' tables if they do not already exist."""
    metadata = MetaData()
    
    # Suppliers Table definition
    suppliers_table = Table('suppliers', metadata,
        Column('id', Integer, primary_key=True, autoincrement=True),
        Column('node_name', String, unique=True, nullable=False),
        Column('latitude', Float, nullable=False),
        Column('longitude', Float, nullable=False),
        Column('country', String),
        Column('current_risk_score', Float, default=0.0),
        Column('criticality', Integer, default=1)
    )
    
    # Events Table definition
    events_table = Table('events', metadata,
        Column('id', Integer, primary_key=True, autoincrement=True),
        Column('article_url', String, unique=True),
        Column('article_source', String),
        Column('article_title', String),
        Column('article_timestamp', DateTime),
        Column('event_text_segment', String),
        Column('potential_event_types', JSONB),
        Column('extracted_locations', JSONB),
        Column('matched_node', String),
        Column('risk_score', Float),
        Column('risk_relevance_score', Float),
        Column('risk_severity_score', Float),
        Column('latitude', Float),
        Column('longitude', Float),
        Column('temporal_info', JSONB),  # For forecasted events
        Column('ml_risk_label', String),
        Column('ml_risk_confidence', Float),
        Column('ml_risk_probabilities', JSONB),
    )

    try:
        print("Creating tables if they don't exist...")
        metadata.create_all(engine)
        print("✅ Tables checked/created successfully.")
    except SQLAlchemyError as e:
        print(f"❌ Error creating tables: {e}")


def ensure_events_ml_columns(engine):
    """Add ML risk columns to events if missing (existing DBs created before ML fields)."""
    stmts = [
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS ml_risk_label VARCHAR(16);",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS ml_risk_confidence DOUBLE PRECISION;",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS ml_risk_probabilities JSONB;",
    ]
    try:
        with engine.begin() as connection:
            for stmt in stmts:
                connection.execute(text(stmt))
        print("✅ ML risk columns verified on events table.")
    except SQLAlchemyError as e:
        print(f"⚠️ Could not ensure ML columns (may be non-Postgres): {e}")


def ensure_events_risk_columns(engine):
    """Add split risk scoring columns to events if missing."""
    stmts = [
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS risk_relevance_score DOUBLE PRECISION;",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS risk_severity_score DOUBLE PRECISION;",
    ]
    try:
        with engine.begin() as connection:
            for stmt in stmts:
                connection.execute(text(stmt))
        print("✅ Risk score columns verified on events table.")
    except SQLAlchemyError as e:
        print(f"⚠️ Could not ensure risk columns (may be non-Postgres): {e}")


def load_geocoded_data(filepath="data/processed/temporal_enriched_events.jsonl"):
    """Loads event data from a JSONL file, preferring temporal enriched data."""
    # Try temporal enriched events first (has temporal_info for forecasting)
    if not os.path.exists(filepath):
        print(f"⚠️ Warning: Temporal enriched events file not found at {filepath}")
        print(f"   Falling back to matched events (no temporal forecasting data)")
        filepath = "data/processed/matched_events.jsonl"
        if not os.path.exists(filepath):
            print(f"   Falling back to geocoded events (no matched_node)")
            filepath = "data/processed/geocoded_events.jsonl"
            if not os.path.exists(filepath):
                print(f"❌ Error: No event data file found")
                return []
    
    print(f"Loading data from {filepath} for database population...")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = [json.loads(line) for line in f]
    print(f"Loaded {len(data)} event entries.")
    return data

# NEW: Define common timestamp formats we expect
# The order matters: more specific formats should generally come before more general ones.
TIMESTAMP_FORMATS = [
    # RFC 2822: 'Tue, 30 Sep 2025 06:19:56 +0000'
    '%a, %d %b %Y %H:%M:%S %z',
    # RFC with explicit GMT text: 'Tue, 30 Sep 2025 06:19:56 GMT'
    '%a, %d %b %Y %H:%M:%S GMT',
    # ISO 8601 (with 'Z' for UTC): '2025-09-30T13:08:33Z'
    '%Y-%m-%dT%H:%M:%SZ',
    # ISO 8601 (with timezone offset): '2025-09-30T13:08:33+00:00'
    '%Y-%m-%dT%H:%M:%S%z',
    # ISO 8601 (without 'T' or timezone): '2025-09-29 02:00:04'
    # This one is tricky as it's naive, we'll assume UTC if no tz info
    '%Y-%m-%d %H:%M:%S',
    # Another common format: 'Mon, 2 Jan 2006 15:04:05 MST' (with named timezone, which strptime doesn't handle directly,
    # so we often drop the timezone for parsing and then assign UTC if it's not a standard numerical offset)
    # This might require more advanced parsing or regex if the named timezones are inconsistent.
    # For now, we'll rely on numerical offsets or assume UTC.
]

def parse_timestamp_robust(timestamp_str):
    """
    Attempts to parse a timestamp string using multiple known formats.
    Assumes UTC if no timezone info is present after trying all formats.
    """
    if not timestamp_str:
        return None

    timestamp_str = str(timestamp_str).strip()
    if not timestamp_str:
        return None

    # Some bad rows carry URLs or non-date fragments in timestamp fields.
    if timestamp_str.startswith('http://') or timestamp_str.startswith('https://'):
        return None

    # Try ISO 8601 first (fromisoformat is generally faster and handles more variations)
    # But for our specific case where it failed, we'll try strptime for explicit formats.
    
    for fmt in TIMESTAMP_FORMATS:
        try:
            # For formats without %z, it will be a naive datetime
            parsed_dt = datetime.strptime(timestamp_str, fmt)
            
            # If the datetime is naive (no timezone info), assume UTC
            if parsed_dt.tzinfo is None:
                return pytz.utc.localize(parsed_dt)
            
            # If it has timezone info, convert it to UTC
            return parsed_dt.astimezone(pytz.utc)
        except ValueError:
            continue # Try the next format

    print(f"⚠️ Warning: Could not parse timestamp '{timestamp_str}' after trying all known formats.")
    return None # Return None if no format matches


def _recompute_supplier_risk_scores(connection):
    print("Recomputing 'current_risk_score' for suppliers from recent event risk data...")
    update_risk_stmt = text("""
        UPDATE suppliers AS s
        SET current_risk_score = COALESCE(
            (
                SELECT ROUND(AVG(e.risk_score)::numeric, 2)
                FROM events AS e
                WHERE e.matched_node = s.node_name
                  AND e.risk_score IS NOT NULL
                  AND e.risk_score > 0
                  AND e.article_timestamp >= NOW() - INTERVAL '30 days'
            ),
            (
                SELECT ROUND(AVG(e.risk_score)::numeric, 2)
                FROM events AS e
                WHERE e.matched_node = s.node_name
                  AND e.risk_score IS NOT NULL
                  AND e.risk_score > 0
            ),
            0.0
        );
    """)
    connection.execute(update_risk_stmt)
    print("✅ Supplier risk scores updated from recent events.")


def upsert_events(engine, events_data, recompute_supplier_scores=True):
    """
    Upsert event rows only. Ensures ML columns exist on PostgreSQL.
    Used by full pipeline load and by RSS ingestion.
    """
    if not events_data:
        return 0
    ensure_events_ml_columns(engine)
    ensure_events_risk_columns(engine)
    insert_count = 0
    with engine.connect() as connection:
        print(f"Upserting {len(events_data)} event(s)...")
        for event in events_data:
            parsed_timestamp = parse_timestamp_robust(event.get('article_timestamp'))
            potential_event_types_json = json.dumps(event.get('potential_event_types')) if event.get('potential_event_types') is not None else '[]'
            extracted_locations_json = json.dumps(event.get('extracted_locations')) if event.get('extracted_locations') is not None else '[]'
            temporal_info_json = json.dumps(event.get('temporal_info')) if event.get('temporal_info') is not None else None
            ml_probs = event.get('ml_risk_probabilities')
            ml_risk_probabilities_json = json.dumps(ml_probs) if ml_probs is not None else None

            stmt = text("""
                INSERT INTO events (
                    article_url, article_source, article_title, article_timestamp, event_text_segment,
                    potential_event_types, extracted_locations, matched_node, risk_score, risk_relevance_score, risk_severity_score, latitude, longitude,
                    temporal_info, ml_risk_label, ml_risk_confidence, ml_risk_probabilities
                )
                VALUES (
                    :article_url, :article_source, :article_title, :article_timestamp, :event_text_segment,
                    :potential_event_types, :extracted_locations, :matched_node, :risk_score, :risk_relevance_score, :risk_severity_score, :latitude, :longitude,
                    :temporal_info, :ml_risk_label, :ml_risk_confidence, :ml_risk_probabilities
                )
                ON CONFLICT (article_url) DO UPDATE SET
                    article_source = COALESCE(EXCLUDED.article_source, events.article_source),
                    article_title = COALESCE(EXCLUDED.article_title, events.article_title),
                    article_timestamp = COALESCE(EXCLUDED.article_timestamp, events.article_timestamp),
                    event_text_segment = COALESCE(EXCLUDED.event_text_segment, events.event_text_segment),
                    potential_event_types = COALESCE(EXCLUDED.potential_event_types, events.potential_event_types),
                    extracted_locations = COALESCE(EXCLUDED.extracted_locations, events.extracted_locations),
                    matched_node = COALESCE(EXCLUDED.matched_node, events.matched_node),
                    risk_score = COALESCE(EXCLUDED.risk_score, events.risk_score),
                    risk_relevance_score = COALESCE(EXCLUDED.risk_relevance_score, events.risk_relevance_score),
                    risk_severity_score = COALESCE(EXCLUDED.risk_severity_score, events.risk_severity_score),
                    latitude = COALESCE(EXCLUDED.latitude, events.latitude),
                    longitude = COALESCE(EXCLUDED.longitude, events.longitude),
                    temporal_info = COALESCE(EXCLUDED.temporal_info, events.temporal_info),
                    ml_risk_label = COALESCE(EXCLUDED.ml_risk_label, events.ml_risk_label),
                    ml_risk_confidence = COALESCE(EXCLUDED.ml_risk_confidence, events.ml_risk_confidence),
                    ml_risk_probabilities = COALESCE(EXCLUDED.ml_risk_probabilities, events.ml_risk_probabilities);
            """)
            try:
                result = connection.execute(stmt, {
                    "article_url": event.get('article_url'),
                    "article_source": event.get('article_source'),
                    "article_title": event.get('article_title'),
                    "article_timestamp": parsed_timestamp,
                    "event_text_segment": event.get('event_text_segment'),
                    "potential_event_types": potential_event_types_json,
                    "extracted_locations": extracted_locations_json,
                    "matched_node": event.get('matched_node'),
                    "risk_score": event.get('risk_score'),
                    "risk_relevance_score": event.get('risk_relevance_score'),
                    "risk_severity_score": event.get('risk_severity_score'),
                    "latitude": event.get('latitude'),
                    "longitude": event.get('longitude'),
                    "temporal_info": temporal_info_json,
                    "ml_risk_label": event.get('ml_risk_label'),
                    "ml_risk_confidence": event.get('ml_risk_confidence'),
                    "ml_risk_probabilities": ml_risk_probabilities_json,
                })
                if result.rowcount > 0:
                    insert_count += 1
            except SQLAlchemyError as e:
                print(f"⚠️ Warning: Could not insert event {event.get('article_url')}. Error: {e}")
        if recompute_supplier_scores:
            _recompute_supplier_risk_scores(connection)
        connection.commit()
    print(f"✅ Events upsert complete (rows affected approx): {insert_count}")
    return insert_count


def populate_database(engine, events_data):
    """Populates the 'suppliers' and 'events' tables with data."""
    ensure_events_ml_columns(engine)
    ensure_events_risk_columns(engine)
    with engine.connect() as connection:
        print("Populating 'suppliers' table with criticality...")
        for node_name, details in SUPPLIER_NODES.items():
            stmt = text("""
                INSERT INTO suppliers (node_name, latitude, longitude, country, criticality)
                VALUES (:node_name, :latitude, :longitude, :country, :criticality)
                ON CONFLICT (node_name) DO UPDATE SET
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    country = EXCLUDED.country,
                    criticality = EXCLUDED.criticality;
            """)
            connection.execute(stmt, {"node_name": node_name, **details})
        connection.commit()
        print(f"✅ 'suppliers' table populated with {len(SUPPLIER_NODES)} nodes.")

    upsert_events(engine, events_data, recompute_supplier_scores=True)

if __name__ == "__main__":
    engine = get_db_engine()
    if engine:
        create_tables(engine)
        ensure_events_ml_columns(engine)
        events_to_load = load_geocoded_data()
        if events_to_load:
            populate_database(engine, events_to_load)
        else:
            print("🤷 No geocoded events to load.")