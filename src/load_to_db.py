# src/load_to_db.py

import json
import os
import argparse
from sqlalchemy import create_engine, text, Column, Integer, String, Float, DateTime, MetaData, Table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import pytz

from src.db_config import DB_CONNECTION_STRING, DB_CONNECTION_STRING_LEGACY

# --- Supplier Nodes Data with Criticality ---
SUPPLIER_NODES = {
    # iPhone & AirPods & Shared
    "TSMC_Hsinchu": {"latitude": 24.8016, "longitude": 120.9716, "country": "Taiwan", "criticality": 5, "products": ["iPhone", "AirPods"]},
    "Foxconn_Zhengzhou": {"latitude": 34.7466, "longitude": 113.6253, "country": "China", "criticality": 5, "products": ["iPhone"]},
    "Port_of_Long_Beach": {"latitude": 33.7542, "longitude": -118.2165, "country": "USA", "criticality": 4, "products": ["iPhone"]},
    # Tesla Shared
    "Albemarle_Chile": {"latitude": -23.5869, "longitude": -68.1533, "country": "Chile", "criticality": 3, "products": ["Tesla Model Y"]},
    "CATL_Ningde": {"latitude": 26.6577, "longitude": 119.5262, "country": "China", "criticality": 4, "products": ["Tesla Model Y"]},
    "Tesla_Berlin": {"latitude": 52.4045, "longitude": 13.7845, "country": "Germany", "criticality": 3, "products": ["Tesla Model Y"]},
    
    # iPhone specific new nodes
    "Pegatron_Shanghai": {"latitude": 31.1448, "longitude": 121.5546, "country": "China", "criticality": 4, "products": ["iPhone"]},
    "Samsung_Display_Seoul": {"latitude": 37.5665, "longitude": 126.9780, "country": "South Korea", "criticality": 4, "products": ["iPhone"]},
    "Sony_Kumamoto": {"latitude": 32.8032, "longitude": 130.7079, "country": "Japan", "criticality": 3, "products": ["iPhone"]},
    "Corning_Kentucky": {"latitude": 37.7554, "longitude": -84.8250, "country": "USA", "criticality": 3, "products": ["iPhone"]},
    "SK_Hynix_Icheon": {"latitude": 37.2642, "longitude": 127.4725, "country": "South Korea", "criticality": 4, "products": ["iPhone"]},
    "Micron_Boise": {"latitude": 43.5350, "longitude": -116.1419, "country": "USA", "criticality": 3, "products": ["iPhone"]},
    "Cirrus_Logic_Austin": {"latitude": 30.2711, "longitude": -97.7437, "country": "USA", "criticality": 3, "products": ["iPhone"]},
    "NXP_Eindhoven": {"latitude": 51.4116, "longitude": 5.4594, "country": "Netherlands", "criticality": 3, "products": ["iPhone"]},
    "STMicro_Geneva": {"latitude": 46.2238, "longitude": 6.0463, "country": "Switzerland", "criticality": 3, "products": ["iPhone"]},
    "Broadcom_San_Jose": {"latitude": 37.4093, "longitude": -121.9333, "country": "USA", "criticality": 4, "products": ["iPhone"]},
    "Kioxia_Tokyo": {"latitude": 35.6441, "longitude": 139.7437, "country": "Japan", "criticality": 4, "products": ["iPhone"]},

    # AirPods specific new nodes
    "Luxshare_Bac_Giang": {"latitude": 21.2731, "longitude": 106.1946, "country": "Vietnam", "criticality": 4, "products": ["AirPods"]},
    "GoerTek_Bac_Ninh": {"latitude": 21.1861, "longitude": 106.0763, "country": "Vietnam", "criticality": 4, "products": ["AirPods"]},
    "Murata_Kyoto": {"latitude": 34.9294, "longitude": 135.6980, "country": "Japan", "criticality": 3, "products": ["AirPods"]},
    "Varta_Ellwangen": {"latitude": 48.9602, "longitude": 10.1332, "country": "Germany", "criticality": 3, "products": ["AirPods"]},
    "Inventec_Taipei": {"latitude": 25.0881, "longitude": 121.5647, "country": "Taiwan", "criticality": 4, "products": ["AirPods"]},
    "Amkor_Manila": {"latitude": 14.3644, "longitude": 121.0531, "country": "Philippines", "criticality": 3, "products": ["AirPods"]},

    # Tesla specific new nodes
    "LG_Energy_Nanjing": {"latitude": 32.1462, "longitude": 118.9328, "country": "China", "criticality": 4, "products": ["Tesla Model Y"]},
    "Panasonic_Nevada": {"latitude": 39.5392, "longitude": -119.4398, "country": "USA", "criticality": 4, "products": ["Tesla Model Y"]},
    "ZF_Friedrichshafen": {"latitude": 47.6536, "longitude": 9.4735, "country": "Germany", "criticality": 3, "products": ["Tesla Model Y"]},
    "Bosch_Stuttgart": {"latitude": 48.7833, "longitude": 9.1833, "country": "Germany", "criticality": 4, "products": ["Tesla Model Y"]},
    "Brembo_Bergamo": {"latitude": 45.6961, "longitude": 9.6672, "country": "Italy", "criticality": 3, "products": ["Tesla Model Y"]},
    "Valeo_Paris": {"latitude": 48.8785, "longitude": 2.3082, "country": "France", "criticality": 3, "products": ["Tesla Model Y"]},
    "Ganfeng_Lithium_Xinyu": {"latitude": 27.8188, "longitude": 114.9351, "country": "China", "criticality": 4, "products": ["Tesla Model Y"]},
}

def get_db_engine():
    """Active database (DB_CONNECTION_STRING)."""
    try:
        engine = create_engine(DB_CONNECTION_STRING)
        with engine.connect() as connection:
            print("✅ Database connection successful.")
        return engine
    except SQLAlchemyError as e:
        print(f"❌ Error connecting to the database: {e}")
        return None


def get_legacy_db_engine():
    if not DB_CONNECTION_STRING_LEGACY:
        return None
    try:
        engine = create_engine(DB_CONNECTION_STRING_LEGACY)
        with engine.connect():
            print("✅ Legacy database connection successful.")
        return engine
    except SQLAlchemyError as e:
        print(f"❌ Error connecting to the legacy database: {e}")
        return None


def fetch_existing_article_urls(engine, urls: list) -> set:
    """Return article_url values that already exist in events (chunked IN queries)."""
    if not urls:
        return set()
    # Dedupe while keeping stable order
    unique = list(dict.fromkeys(str(u) for u in urls if u))
    if not unique:
        return set()
    from sqlalchemy import bindparam
    from sqlalchemy.exc import SQLAlchemyError

    found: set = set()
    chunk_size = 400
    stmt = text("SELECT article_url FROM events WHERE article_url IN :url_list").bindparams(
        bindparam("url_list", expanding=True)
    )
    try:
        with engine.connect() as conn:
            for i in range(0, len(unique), chunk_size):
                chunk = unique[i : i + chunk_size]
                result = conn.execute(stmt, {"url_list": chunk})
                found.update(row[0] for row in result if row[0])
    except SQLAlchemyError as e:
        # Table might not exist yet; return empty set
        pass
    return found


def filter_new_events_by_url(engine, events_data: list) -> tuple:
    """
    Drop events whose article_url is already in the database (avoids duplicate enrichment work).
    Returns (new_events, skipped_count). Upsert still dedupes on conflict if you skip this filter.
    """
    if not events_data:
        return [], 0
    urls = [e.get("article_url") for e in events_data if e.get("article_url")]
    existing = fetch_existing_article_urls(engine, urls)
    new_events = [e for e in events_data if e.get("article_url") and e["article_url"] not in existing]
    skipped = len(events_data) - len(new_events)
    return new_events, skipped

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
        Column('criticality', Integer, default=1),
        Column('products', JSONB)
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
        Column('matched_node', JSONB),
        Column('risk_score', Float),
        Column('risk_relevance_score', Float),
        Column('risk_severity_score', Float),
        Column('latitude', Float),
        Column('longitude', Float),
        Column('temporal_info', JSONB),  # For forecasted events
        Column('ml_risk_label', String),
        Column('ml_risk_confidence', Float),
        Column('ml_risk_probabilities', JSONB),
        Column('predicted_disruption_probability', Float),
        Column('predicted_impact_score', Float),
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

def ensure_suppliers_products_column(engine):
    """Add products column to suppliers table if missing."""
    stmts = [
        "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS products JSONB;"
    ]
    try:
        with engine.begin() as connection:
            for stmt in stmts:
                connection.execute(text(stmt))
        print("✅ Products column verified on suppliers table.")
    except SQLAlchemyError as e:
        print(f"⚠️ Could not ensure products column (may be non-Postgres): {e}")


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


def ensure_events_impact_columns(engine):
    """Add impact prediction columns to events if missing."""
    stmts = [
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS predicted_disruption_probability DOUBLE PRECISION;",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS predicted_impact_score DOUBLE PRECISION;",
    ]
    try:
        with engine.begin() as connection:
            for stmt in stmts:
                connection.execute(text(stmt))
        print("✅ Impact prediction columns verified on events table.")
    except SQLAlchemyError as e:
        print(f"⚠️ Could not ensure impact columns (may be non-Postgres): {e}")


def ensure_events_sentiment_columns(engine):
    stmts = [
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS sentiment_label VARCHAR(32);",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS sentiment_score DOUBLE PRECISION;",
    ]
    try:
        with engine.begin() as connection:
            for stmt in stmts:
                connection.execute(text(stmt))
        print("✅ Sentiment columns verified on events table.")
    except SQLAlchemyError as e:
        print(f"⚠️ Could not ensure sentiment columns (may be non-Postgres): {e}")


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


def _recompute_supplier_risk_scores(connection, node_name=None):
    """
    Roll up per-node exposure to 0–100 for the suppliers table.

    Per-event strength uses predicted_impact_score (training scale ~0–300) scaled to 0–100
    when present; otherwise risk_score. Blend is softer than the old avg + 0.8*max formula,
    which saturated at 100 for most nodes whenever any HIGH-risk headlines appeared.
    """
    print(f"Recomputing 'current_risk_score' for suppliers {'(node: ' + node_name + ')' if node_name else 'all'} from recent event risk data...")
    
    where_clause = ""
    params = {}
    if node_name:
        where_clause = "WHERE s.node_name = :node_name"
        params["node_name"] = node_name

    update_risk_stmt = text(f"""
        UPDATE suppliers AS s
        SET current_risk_score = COALESCE(
            (
                SELECT ROUND(LEAST(100.0, COALESCE(0.62 * AVG(t.strength) + 0.38 * MAX(t.strength), 0.0))::numeric, 2)
                FROM (
                    SELECT LEAST(
                        100.0,
                        COALESCE(
                            e.predicted_impact_score::double precision / 3.0,
                            e.risk_score::double precision
                        )
                    ) AS strength
                    FROM events AS e
                    WHERE e.matched_node @> jsonb_build_array(s.node_name)
                      AND e.article_timestamp >= NOW() - INTERVAL '30 days'
                      AND (
                          (e.risk_score IS NOT NULL AND e.risk_score > 0)
                          OR e.predicted_impact_score IS NOT NULL
                      )
                ) AS t
            ),
            0.0
        )
        {where_clause};
    """)
    connection.execute(update_risk_stmt, params)
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
    ensure_events_impact_columns(engine)
    ensure_events_sentiment_columns(engine)
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
                    temporal_info, ml_risk_label, ml_risk_confidence, ml_risk_probabilities, predicted_disruption_probability, predicted_impact_score,
                    sentiment_label, sentiment_score
                )
                VALUES (
                    :article_url, :article_source, :article_title, :article_timestamp, :event_text_segment,
                    :potential_event_types, :extracted_locations, :matched_node, :risk_score, :risk_relevance_score, :risk_severity_score, :latitude, :longitude,
                    :temporal_info, :ml_risk_label, :ml_risk_confidence, :ml_risk_probabilities, :predicted_disruption_probability, :predicted_impact_score,
                    :sentiment_label, :sentiment_score
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
                    ml_risk_probabilities = COALESCE(EXCLUDED.ml_risk_probabilities, events.ml_risk_probabilities),
                    predicted_disruption_probability = COALESCE(EXCLUDED.predicted_disruption_probability, events.predicted_disruption_probability),
                    predicted_impact_score = COALESCE(EXCLUDED.predicted_impact_score, events.predicted_impact_score),
                    sentiment_label = COALESCE(EXCLUDED.sentiment_label, events.sentiment_label),
                    sentiment_score = COALESCE(EXCLUDED.sentiment_score, events.sentiment_score);
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
                    "matched_node": json.dumps(event.get('matched_node')) if isinstance(event.get('matched_node'), list) else json.dumps([event.get('matched_node')]) if event.get('matched_node') else '[]',
                    "risk_score": event.get('risk_score'),
                    "risk_relevance_score": event.get('risk_relevance_score'),
                    "risk_severity_score": event.get('risk_severity_score'),
                    "latitude": event.get('latitude'),
                    "longitude": event.get('longitude'),
                    "temporal_info": temporal_info_json,
                    "ml_risk_label": event.get('ml_risk_label'),
                    "ml_risk_confidence": event.get('ml_risk_confidence'),
                    "ml_risk_probabilities": ml_risk_probabilities_json,
                    "predicted_disruption_probability": event.get('predicted_disruption_probability'),
                    "predicted_impact_score": event.get('predicted_impact_score'),
                    "sentiment_label": event.get('sentiment_label'),
                    "sentiment_score": event.get('sentiment_score'),
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
    ensure_suppliers_products_column(engine)
    ensure_events_ml_columns(engine)
    ensure_events_risk_columns(engine)
    ensure_events_impact_columns(engine)
    ensure_events_sentiment_columns(engine)
    with engine.connect() as connection:
        print("Populating 'suppliers' table with criticality and products...")
        for node_name, details in SUPPLIER_NODES.items():
            products_json = json.dumps(details.get("products", []))
            stmt = text("""
                INSERT INTO suppliers (node_name, latitude, longitude, country, criticality, products)
                VALUES (:node_name, :latitude, :longitude, :country, :criticality, :products)
                ON CONFLICT (node_name) DO UPDATE SET
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    country = EXCLUDED.country,
                    criticality = EXCLUDED.criticality,
                    products = EXCLUDED.products;
            """)
            connection.execute(stmt, {
                "node_name": node_name, 
                "latitude": details["latitude"],
                "longitude": details["longitude"],
                "country": details["country"],
                "criticality": details["criticality"],
                "products": products_json
            })
        connection.commit()
        print(f"✅ 'suppliers' table populated with {len(SUPPLIER_NODES)} nodes.")

    upsert_events(engine, events_data, recompute_supplier_scores=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load geocoded events to DB.")
    parser.add_argument("--recompute-risk", action="store_true", help="Recompute supplier risk scores from existing events")
    args = parser.parse_args()

    engine = get_db_engine()
    if engine:
        if args.recompute_risk:
            with engine.connect() as connection:
                _recompute_supplier_risk_scores(connection)
                connection.commit()
        else:
            create_tables(engine)
            ensure_suppliers_products_column(engine)
            ensure_events_ml_columns(engine)
            events_to_load = load_geocoded_data()
            if events_to_load:
                populate_database(engine, events_to_load)
            else:
                print("🤷 No geocoded events to load.")

def get_all_events(engine):
    """Fetches all events from the database and returns them as a list of dicts."""
    events = []
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT * FROM events"))
            for row in result:
                event_dict = dict(row._mapping)
                if isinstance(event_dict.get('article_timestamp'), datetime):
                    event_dict['article_timestamp'] = event_dict['article_timestamp'].isoformat()
                events.append(event_dict)
    except SQLAlchemyError as e:
        print(f"❌ Error fetching all events: {e}")
    return events