# src/main.py

from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import threading
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date
import pandas as pd
import xgboost as xgb
import os
import logging
import json
from datetime import datetime, date, timedelta

from src.db_config import DB_CONNECTION_STRING

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- SQLAlchemy Setup ---
engine = None
SessionLocal = None
try:
    engine = create_engine(DB_CONNECTION_STRING)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("✅ Database engine created successfully.")
except Exception as e:
    logger.error(f"❌ Error creating database engine: {e}")

# Dependency to get a DB session
def get_db():
    if SessionLocal is None:
        logger.error("Database session not configured, cannot provide a session.")
        raise HTTPException(status_code=500, detail="Database session not configured.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic Models (Data Shapes) ---

class Supplier(BaseModel):
    id: int
    node_name: str
    latitude: float
    longitude: float
    country: Optional[str] = None
    current_risk_score: Optional[float] = None
    criticality: int = 1 # NEW: Added criticality
    products: Optional[List[str]] = None # NEW: Added products
    class Config:
        from_attributes = True

class Event(BaseModel):
    id: int
    article_url: str
    article_source: Optional[str] = None
    article_title: Optional[str] = None
    article_timestamp: Optional[datetime] = None
    event_text_segment: Optional[str] = None
    potential_event_types: Optional[List[str]] = None
    extracted_locations: Optional[List[str]] = None
    matched_node: Optional[str] = None
    risk_score: Optional[float] = None
    risk_relevance_score: Optional[float] = None
    risk_severity_score: Optional[float] = None
    impact_score: Optional[float] = None # NEW: Added impact_score
    predicted_impact_score: Optional[float] = None
    predicted_disruption_probability: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    temporal_info: Optional[dict] = None # NEW: Temporal prediction data
    ml_risk_label: Optional[str] = None
    ml_risk_confidence: Optional[float] = None
    ml_risk_probabilities: Optional[dict] = None
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None
    class Config:
        from_attributes = True

class EventSummary(BaseModel):
    total_events: int
    avg_risk_score: Optional[float] = None
    most_common_event_type: Optional[str] = None
    
    class Config:
        from_attributes = True


class NodeAiSummaryRequest(BaseModel):
    """Optional body for POST /suppliers/{node_name}/ai-summary."""
    model: Optional[str] = None


class NodeAiSummaryResponse(BaseModel):
    summary: str
    model_used: str
    node_name: str

class ForecastPoint(BaseModel):
    ds: date # The date for the forecast point
    yhat: float # The forecasted value
    yhat_lower: float # The lower bound of the confidence interval
    yhat_upper: float # The upper bound of the confidence interval
    class Config:
        from_attributes = True

class HybridForecastPoint(BaseModel):
    ds: date # The date for the forecast point
    yhat: float # The hybrid forecasted value
    yhat_lower: float # The lower bound
    yhat_upper: float # The upper bound
    news_contribution: float # Risk from predictive news articles
    historical_contribution: float # Risk from historical trends
    method: str # "hybrid" or "historical_only"
    class Config:
        from_attributes = True


class ForecastSnapshotPoint(BaseModel):
    ds: date
    yhat: float
    yhat_lower: float
    yhat_upper: float
    y_actual: Optional[float] = None


class ForecastSnapshotResponse(BaseModel):
    node_name: str
    forecast_date: date
    points: List[ForecastSnapshotPoint]
    generated_on_demand: bool
    mae: Optional[float] = None
    completed_days: int = 0
    horizon_days: int = 14

# --- Background Tasks ---
def rss_ingest_worker():
    from pathlib import Path
    from src.rss_ingest import run_once
    import os
    
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    feeds_path = os.getenv("RSS_FEEDS_PATH", str(PROJECT_ROOT / "config" / "rss_feeds.json"))
    model_path = os.getenv("ML_CLASSIFIER_PATH", str(PROJECT_ROOT / "model_training" / "classifier.pkl"))
    disruption_model_path = os.getenv("DISRUPTION_CLASSIFIER_PATH", str(PROJECT_ROOT / "model_training" / "disruption_classifier.pkl"))
    impact_model_path = os.getenv("IMPACT_REGRESSOR_PATH", str(PROJECT_ROOT / "model_training" / "impact_regressor_v2.pkl"))
    
    interval = 600 # 10 minutes
    logger.info("RSS Ingest background worker started.")
    while True:
        try:
            logger.info("Running RSS ingest cycle...")
            run_once(feeds_path, model_path, disruption_model_path, impact_model_path, False, True)
        except Exception as e:
            logger.error(f"RSS Ingest cycle failed: {e}")
        time.sleep(interval)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if engine is not None:
        try:
            from src.forecast_snapshots import ensure_forecast_snapshots_table

            ensure_forecast_snapshots_table(engine)
            logger.info("✅ forecast_snapshots table ensured.")
        except Exception as e:
            logger.error("Could not ensure forecast_snapshots table: %s", e, exc_info=True)
    worker_thread = threading.Thread(target=rss_ingest_worker, daemon=True)
    worker_thread.start()
    yield
    # Shutdown
    # Daemon thread will exit automatically

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Supply Chain Disruption Forecaster API",
    description="API to serve risk data and forecasts for supply chain nodes and events.",
    version="1.2.0", # Updated version number
    lifespan=lifespan
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for development. Be more specific in production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper Functions for API Endpoints ---
def get_criticality_map(db: Session):
    """Fetches all supplier criticalities into a dictionary for quick lookup."""
    suppliers = db.execute(text("SELECT node_name, criticality FROM suppliers")).fetchall()
    return {s.node_name: s.criticality for s in suppliers}

def process_events_with_impact(event_rows, criticality_map):
    """Calculates impact score and converts rows to Pydantic Event models."""
    processed = []
    for row in event_rows:
        event_dict = dict(row._mapping)
        matched_node = event_dict.get('matched_node')
        risk_score = event_dict.get('risk_score') or 0.0
        
        # matched_node can now be a list (from JSONB array)
        if isinstance(matched_node, list):
            if matched_node:
                # Use the maximum criticality among all matched nodes
                criticality = max([criticality_map.get(n, 1) for n in matched_node])
                # For display/serialization, join them or pick the first? 
                # The Event model likely expects a string.
                event_dict['matched_node'] = ", ".join(matched_node)
            else:
                criticality = 1
                event_dict['matched_node'] = None
        else:
            # Fallback for legacy data or single strings
            criticality = criticality_map.get(matched_node, 1)

        # Calculate impact score: Risk Score * Node Criticality
        event_dict['impact_score'] = round(risk_score * criticality, 2)
        if event_dict.get('predicted_impact_score') is not None:
            try:
                event_dict['predicted_impact_score'] = float(event_dict['predicted_impact_score'])
            except (TypeError, ValueError):
                event_dict['predicted_impact_score'] = None
        
        # Ensure it fits the Pydantic model (which might expect a string for matched_node)
        processed.append(Event.from_orm(event_dict))
    return processed


def _rollup_time_clause(use_30d: bool) -> str:
    return (
        "AND article_timestamp >= NOW() - INTERVAL '30 days'"
        if use_30d
        else ""
    )


def _exposure_rollup_stats(db: Session, node_name: str):
    """
    Recompute exposure rollup stats using the same rules as load_to_db._recompute_supplier_risk_scores:
    strength = LEAST(100, COALESCE(predicted_impact/3, risk_score)); exposure = LEAST(100, 0.62*AVG + 0.38*MAX).
    Prefers events in the last 30 days; if none qualify, uses all-time (matching DB COALESCE fallback).

    Returns (stats_row_dict, use_30d, top_driver_rows) where use_30d is True iff the stats come from the 30-day window.
    """
    base_where = """
        matched_node @> jsonb_build_array(:n)
        AND (
            (risk_score IS NOT NULL AND risk_score > 0)
            OR predicted_impact_score IS NOT NULL
        )
    """
    stats_sql = text(
        f"""
        SELECT
            COUNT(*)::int AS n_events,
            ROUND(AVG(strength)::numeric, 2) AS avg_strength,
            ROUND(MAX(strength)::numeric, 2) AS max_strength,
            ROUND(LEAST(100.0, 0.62 * AVG(strength) + 0.38 * MAX(strength))::numeric, 2) AS rolled_exposure
        FROM (
            SELECT LEAST(
                100.0,
                COALESCE(
                    predicted_impact_score::double precision / 3.0,
                    risk_score::double precision
                )
            ) AS strength
            FROM events
            WHERE {base_where}
            {_rollup_time_clause(True)}
        ) t
        """
    )
    row = db.execute(stats_sql, {"n": node_name}).fetchone()
    d = dict(row._mapping) if row else {}
    n = d.get("n_events") or 0
    use_30d = True
    if n == 0:
        stats_sql_all = text(
            f"""
            SELECT
                COUNT(*)::int AS n_events,
                ROUND(AVG(strength)::numeric, 2) AS avg_strength,
                ROUND(MAX(strength)::numeric, 2) AS max_strength,
                ROUND(LEAST(100.0, 0.62 * AVG(strength) + 0.38 * MAX(strength))::numeric, 2) AS rolled_exposure
            FROM (
                SELECT LEAST(
                    100.0,
                    COALESCE(
                        predicted_impact_score::double precision / 3.0,
                        risk_score::double precision
                    )
                ) AS strength
                FROM events
                WHERE {base_where}
            ) t
            """
        )
        row = db.execute(stats_sql_all, {"n": node_name}).fetchone()
        d = dict(row._mapping) if row else {}
        use_30d = False
    top_sql = text(
        f"""
        SELECT article_title, article_source, article_timestamp::text AS ts,
               risk_score, predicted_impact_score, predicted_disruption_probability,
               LEAST(
                   100.0,
                   COALESCE(
                       predicted_impact_score::double precision / 3.0,
                       risk_score::double precision
                   )
               ) AS strength
        FROM events
        WHERE {base_where}
        {_rollup_time_clause(use_30d)}
        ORDER BY strength DESC NULLS LAST, article_timestamp DESC NULLS LAST
        LIMIT 5
        """
    )

    top_rows = db.execute(top_sql, {"n": node_name}).fetchall()
    return d, use_30d, top_rows


def _parse_as_of_optional(as_of: Optional[str] = Query(None, description="Rewind: include only data on or before this date (YYYY-MM-DD, UTC calendar day)")) -> Optional[date]:
    if as_of is None or as_of.strip() == "":
        return None
    try:
        return date.fromisoformat(as_of.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid as_of; use YYYY-MM-DD.")


def _supplier_exposure_as_of(db: Session, node_name: str, as_of: date) -> float:
    """
    Match load_to_db rollup with NOW replaced by as_of: 30d window ending as_of, else all-time through as_of.
    """
    base_filter = """
        matched_node @> jsonb_build_array(:node_name)
        AND article_timestamp IS NOT NULL
        AND article_timestamp::date <= :as_of
        AND (
            (risk_score IS NOT NULL AND risk_score > 0)
            OR predicted_impact_score IS NOT NULL
        )
    """
    stmt_30 = text(
        f"""
        SELECT ROUND(LEAST(100.0, 0.62 * AVG(strength) + 0.38 * MAX(strength))::numeric, 2) AS exposure
        FROM (
            SELECT LEAST(
                100.0,
                COALESCE(
                    predicted_impact_score::double precision / 3.0,
                    risk_score::double precision
                )
            ) AS strength
            FROM events
            WHERE {base_filter}
              AND article_timestamp::date > :as_of - INTERVAL '30 days'
        ) t
        """
    )
    row = db.execute(stmt_30, {"node_name": node_name, "as_of": as_of}).fetchone()
    val = row[0] if row and row[0] is not None else None
    if val is not None:
        return float(val)
    stmt_all = text(
        f"""
        SELECT ROUND(LEAST(100.0, 0.62 * AVG(strength) + 0.38 * MAX(strength))::numeric, 2) AS exposure
        FROM (
            SELECT LEAST(
                100.0,
                COALESCE(
                    predicted_impact_score::double precision / 3.0,
                    risk_score::double precision
                )
            ) AS strength
            FROM events
            WHERE {base_filter}
        ) t
        """
    )
    row2 = db.execute(stmt_all, {"node_name": node_name, "as_of": as_of}).fetchone()
    if row2 and row2[0] is not None:
        return float(row2[0])
    return 0.0


# --- API Endpoints ---

@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Welcome to the Supply Chain Forecaster API!"}

@app.get("/suppliers", response_model=List[Supplier], tags=["Suppliers"])
def get_all_suppliers(
    db: Session = Depends(get_db),
    as_of: Optional[date] = Depends(_parse_as_of_optional),
):
    """
    Retrieves a list of all defined supply chain nodes/suppliers, including their criticality.
    Optional as_of recomputes current_risk_score from events through that UTC date.
    """
    try:
        query = text("SELECT id, node_name, latitude, longitude, country, current_risk_score, criticality, products FROM suppliers")
        result = db.execute(query).fetchall()
        rows = [dict(row._mapping) for row in result]
        if as_of is not None:
            today = date.today()
            if as_of > today:
                raise HTTPException(status_code=400, detail="as_of cannot be in the future.")
            for r in rows:
                r["current_risk_score"] = _supplier_exposure_as_of(db, r["node_name"], as_of)
        return [Supplier.from_orm(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching suppliers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not fetch suppliers: {e}")

@app.get("/events/latest", response_model=List[Event], tags=["Events"])
def get_latest_events(
    count: int = Query(50, description="Number of latest events to retrieve", ge=1, le=200),
    db: Session = Depends(get_db),
    as_of: Optional[date] = Depends(_parse_as_of_optional),
):
    """
    Retrieves the latest supply chain events, ordered by timestamp,
    calculating an impact score for each.
    Only includes events with valid latitude and longitude.
    """
    try:
        if as_of is not None and as_of > date.today():
            raise HTTPException(status_code=400, detail="as_of cannot be in the future.")
        criticality_map = get_criticality_map(db)
        as_filter = ""
        params = {"count": count}
        if as_of is not None:
            as_filter = "AND article_timestamp::date <= :as_of"
            params["as_of"] = as_of
        query = text(f"""
            SELECT * FROM events
                        WHERE latitude IS NOT NULL
                            AND longitude IS NOT NULL
                            AND article_timestamp IS NOT NULL
                            {as_filter}
                        ORDER BY article_timestamp DESC NULLS LAST
            LIMIT :count;
        """)
        result = db.execute(query, params).fetchall()
        return process_events_with_impact(result, criticality_map)
    except Exception as e:
        logger.error(f"Error fetching latest events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not fetch latest events: {e}")

@app.get("/events/by_node/{node_name}", response_model=List[Event], tags=["Events"])
def get_events_by_node(
    node_name: str,
    limit: int = Query(100, description="Max number of events for the node", ge=1, le=200),
    db: Session = Depends(get_db),
    as_of: Optional[date] = Depends(_parse_as_of_optional),
):
    """
    Retrieves events associated with a specific supply chain node,
    calculating an impact score for each.
    Only includes events with valid latitude and longitude.
    """
    try:
        if as_of is not None and as_of > date.today():
            raise HTTPException(status_code=400, detail="as_of cannot be in the future.")
        criticality_map = get_criticality_map(db)
        as_filter = ""
        params = {"node_name": node_name, "limit": limit}
        if as_of is not None:
            as_filter = "AND article_timestamp::date <= :as_of"
            params["as_of"] = as_of
        query = text(f"""
            SELECT * FROM events
                        WHERE matched_node @> :node_name_json
                            AND latitude IS NOT NULL
                            AND longitude IS NOT NULL
                            AND article_timestamp IS NOT NULL
                            {as_filter}
                        ORDER BY article_timestamp DESC NULLS LAST
            LIMIT :limit;
        """)
        params["node_name_json"] = json.dumps([node_name])
        result = db.execute(query, params).fetchall()
        return process_events_with_impact(result, criticality_map)
    except Exception as e:
        logger.error(f"Error fetching events for node '{node_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not fetch events for node '{node_name}': {e}")


@app.post(
    "/suppliers/{node_name}/ai-summary",
    response_model=NodeAiSummaryResponse,
    tags=["Suppliers"],
)
@app.post(
    "/api/suppliers/{node_name}/ai-summary",
    response_model=NodeAiSummaryResponse,
    tags=["Suppliers"],
    include_in_schema=False,
)
def post_supplier_ai_summary(
    node_name: str,
    db: Session = Depends(get_db),
    req: NodeAiSummaryRequest = NodeAiSummaryRequest(),
):
    """
    On-demand AI summary for one supplier node (OpenRouter). User must trigger via UI;
    this endpoint is not called automatically on page load.
    """
    from src.openrouter_client import chat_completion

    try:
        sup_row = db.execute(
            text(
                "SELECT node_name, country, criticality, current_risk_score "
                "FROM suppliers WHERE node_name = :n"
            ),
            {"n": node_name},
        ).fetchone()
    except Exception as e:
        logger.error(f"DB error loading supplier '{node_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    if not sup_row:
        raise HTTPException(status_code=404, detail=f"Unknown supplier node: {node_name}")

    mapping = dict(sup_row._mapping)
    try:
        rollup_d, rollup_use_30d, top_driver_rows = _exposure_rollup_stats(db, node_name)
    except Exception as e:
        logger.error(f"DB error computing rollup for '{node_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    rollup_window = "last 30 days" if rollup_use_30d else "all time (no qualifying events in the last 30 days)"
    n_ev = rollup_d.get("n_events") or 0
    avg_s = rollup_d.get("avg_strength")
    max_s = rollup_d.get("max_strength")
    rolled = rollup_d.get("rolled_exposure")
    stored = mapping.get("current_risk_score")

    driver_lines = []
    for r in top_driver_rows:
        td = dict(r._mapping)
        title = (td.get("article_title") or "").replace("\n", " ")[:160]
        st = td.get("strength")
        meta = [f"strength={st}"]
        if td.get("risk_score") is not None:
            meta.append(f"risk_score={td.get('risk_score')}")
        if td.get("predicted_impact_score") is not None:
            meta.append(f"predicted_impact_raw={td.get('predicted_impact_score')}")
        if td.get("predicted_disruption_probability") is not None:
            meta.append(f"p_disruption={td.get('predicted_disruption_probability')}")
        driver_lines.append(f"- {title}  ({', '.join(meta)})")

    try:
        ev_rows = db.execute(
            text(
                f"""
                SELECT article_title, article_source,
                       article_timestamp::text AS ts,
                       risk_score, ml_risk_label,
                       predicted_impact_score, predicted_disruption_probability
                FROM events
                WHERE matched_node @> jsonb_build_array(:n)
                  AND (
                    (risk_score IS NOT NULL AND risk_score > 0)
                    OR predicted_impact_score IS NOT NULL
                  )
                  {_rollup_time_clause(rollup_use_30d)}
                ORDER BY article_timestamp DESC NULLS LAST
                LIMIT 24
                """
            ),
            {"n": node_name},
        ).fetchall()
    except Exception as e:
        logger.error(f"DB error loading events for '{node_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    event_lines = []
    for r in ev_rows:
        d = dict(r._mapping)
        title = (d.get("article_title") or "").replace("\n", " ")[:160]
        src = d.get("article_source") or ""
        ts = d.get("ts") or ""
        rs = d.get("risk_score")
        ml = d.get("ml_risk_label") or ""
        pi = d.get("predicted_impact_score")
        pd = d.get("predicted_disruption_probability")
        bits = [f"- {title}"]
        meta = []
        if src:
            meta.append(f"source={src}")
        if ts:
            meta.append(f"time={ts}")
        if rs is not None:
            meta.append(f"risk_score={rs}")
        if ml:
            meta.append(f"ml_label={ml}")
        if pi is not None:
            meta.append(f"predicted_impact={pi}")
        if pd is not None:
            meta.append(f"p_disruption={pd}")
        if meta:
            bits.append("  (" + ", ".join(meta) + ")")
        event_lines.append("\n".join(bits))

    formula_blurb = (
        "Per-event strength = min(100, predicted_impact_score/3 if present else risk_score). "
        "Exposure index = min(100, 0.62 * average(strength) + 0.38 * max(strength)) over contributing events. "
        "Criticality is separate metadata (importance of the node) and is not multiplied into this exposure index."
    )

    rollup_block = (
        f"Rollup window used: {rollup_window}.\n"
        f"{formula_blurb}\n"
        f"- Contributing events: {n_ev}\n"
        f"- Average strength: {avg_s}\n"
        f"- Max strength: {max_s}\n"
        f"- Blended exposure from formula: {rolled}\n"
        f"- Stored exposure on supplier row (may differ slightly if data changed since last recompute): {stored}\n"
        f"Highest-strength headlines (primary drivers of a high max term):\n"
        + (
            "\n".join(driver_lines)
            if driver_lines
            else "(no contributing events; exposure may be stale or zero)"
        )
    )

    context = (
        f"Supplier node: {mapping.get('node_name')}\n"
        f"Country: {mapping.get('country')}\n"
        f"Criticality (1–5): {mapping.get('criticality')}\n\n"
        f"{rollup_block}\n\n"
        f"Contributing events, newest first (up to 24, same filter as rollup):\n"
        + (
            "\n".join(event_lines)
            if event_lines
            else "(none in this window — see rollup note above)"
        )
    )

    system = (
        "You explain supplier exposure for operations teams. Use ONLY the user message. "
        "Your first section MUST be titled 'Why this exposure index' and MUST: (1) restate the numeric "
        "drivers — contributing event count, average strength, max strength, and how the 0.62/0.38 blend "
        "produces the score; (2) name the top headlines that carry the highest strength and tie the score "
        "to those specific rows (quote short phrases from titles, no new facts). "
        "If headlines do not mention the supplier site by name, say clearly that the score comes from "
        "articles the pipeline matched to this node plus their model scores, not from a direct site-specific story. "
        "Do NOT invent geopolitical narratives or causes that are not grounded in the listed titles/scores. "
        "After that, add a short 'Criticality' note and a 'Caveats' note (e.g. matching noise, stale rollup). "
        "Keep under 320 words."
    )

    try:
        summary_text, model_used = chat_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": context},
            ],
            model=req.model,
            temperature=0.35,
        )
    except RuntimeError as e:
        if "OPENROUTER_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e)) from e
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.error(f"OpenRouter error for node '{node_name}': {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"AI provider request failed: {e}",
        ) from e

    return NodeAiSummaryResponse(
        summary=summary_text,
        model_used=model_used,
        node_name=node_name,
    )


@app.post("/admin/rss-ingest/trigger", tags=["Admin"])
def trigger_rss_ingest(background_tasks: BackgroundTasks):
    """
    Manually triggers an RSS ingestion cycle in the background.
    """
    from pathlib import Path
    from src.rss_ingest import run_once
    import os
    
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    feeds_path = os.getenv("RSS_FEEDS_PATH", str(PROJECT_ROOT / "config" / "rss_feeds.json"))
    model_path = os.getenv("ML_CLASSIFIER_PATH", str(PROJECT_ROOT / "model_training" / "classifier.pkl"))
    disruption_model_path = os.getenv("DISRUPTION_CLASSIFIER_PATH", str(PROJECT_ROOT / "model_training" / "disruption_classifier.pkl"))
    impact_model_path = os.getenv("IMPACT_REGRESSOR_PATH", str(PROJECT_ROOT / "model_training" / "impact_regressor_v2.pkl"))
    
    # Run the ingestion in the background so we don't block the API response
    background_tasks.add_task(
        run_once,
        feeds_path,
        model_path,
        disruption_model_path,
        impact_model_path,
        False,
        True,
    )
    return {"status": "success", "message": "RSS ingestion started in the background."}

@app.get("/admin/rss-ingest/status", tags=["Admin"])
def get_rss_ingest_status():
    """
    Returns the current progress of the background RSS ingestion.
    """
    from src.rss_ingest import ingestion_status
    return ingestion_status

@app.get("/summary", response_model=EventSummary, tags=["Dashboard Data"])
def get_dashboard_summary(
    db: Session = Depends(get_db),
    as_of: Optional[date] = Depends(_parse_as_of_optional),
):
    """
    Provides a summary of total events, average risk, and most common event type across all data.
    Optional as_of restricts aggregates to events on or before that UTC date.
    """
    try:
        if as_of is not None and as_of > date.today():
            raise HTTPException(status_code=400, detail="as_of cannot be in the future.")
        as_filter = ""
        params = {}
        if as_of is not None:
            as_filter = "WHERE article_timestamp IS NOT NULL AND article_timestamp::date <= :as_of"
            params["as_of"] = as_of

        total_events_query = text(f"SELECT COUNT(*) FROM events {as_filter};")
        total_events = db.execute(total_events_query, params).scalar()

        avg_risk_query = text(
            f"SELECT AVG(risk_score) FROM events WHERE risk_score IS NOT NULL "
            f"{'AND article_timestamp::date <= :as_of' if as_of is not None else ''};"
        )
        avg_params = {"as_of": as_of} if as_of is not None else {}
        avg_risk_score = db.execute(avg_risk_query, avg_params).scalar()

        mct_filter = ""
        if as_of is not None:
            mct_filter = "AND article_timestamp::date <= :as_of"
        most_common_event_type_query = text(f"""
            SELECT jsonb_array_elements_text(potential_event_types) as event_type
            FROM events
            WHERE potential_event_types IS NOT NULL AND potential_event_types != '[]'::jsonb
            {mct_filter}
            GROUP BY event_type
            ORDER BY COUNT(*) DESC
            LIMIT 1;
        """)
        most_common_event_type_result = db.execute(
            most_common_event_type_query, params if as_of is not None else {}
        ).scalar()

        return EventSummary(
            total_events=total_events,
            avg_risk_score=avg_risk_score,
            most_common_event_type=most_common_event_type_result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching summary data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not fetch summary: {e}")

@app.get("/suppliers/{node_name}/forecast", response_model=List[HybridForecastPoint], tags=["Forecasting"])
def get_risk_forecast(
    node_name: str, 
    as_of: Optional[date] = Depends(_parse_as_of_optional),
    db: Session = Depends(get_db)
):
    """
    Generates a 14-day risk score forecast for a specific supplier node using recursive XGBoost.
    """
    try:
        target_date = as_of or date.today()
        
        # Try running EDSF forecasting as primary
        try:
            from src.predictive_forecasting import generate_edsf_forecast
            forecast_df = generate_edsf_forecast(
                node_name=node_name,
                forecast_days=14,
                session=db,
                target_date=target_date
            )
            forecast_points = forecast_df.to_dict('records')
            
            # Map clean dates to strings/dates expected by response schema
            return [
                {
                    "ds": p["ds"],
                    "yhat": p["yhat"],
                    "yhat_lower": p["yhat_lower"],
                    "yhat_upper": p["yhat_upper"],
                    "news_contribution": p["news_contribution"],
                    "historical_contribution": p["historical_contribution"],
                    "method": "xgboost-news"  # Retain tag for UI schema compatibility
                }
                for p in forecast_points
            ]
        except Exception as edsf_err:
            logger.warning(f"⚠️ EDSF forecast failed for node '{node_name}', falling back to recursive XGBoost: {edsf_err}", exc_info=True)
            
            # Legacy Recursive XGBoost Fallback
            # 1. Fetch historical risk data for the node up to as_of
            query = text("""
                SELECT article_timestamp::date as ds, AVG(risk_score) as y, COUNT(*) as event_count
                FROM events
                WHERE matched_node @> jsonb_build_array(:node_name) 
                  AND article_timestamp IS NOT NULL 
                  AND risk_score IS NOT NULL
                  AND article_timestamp::date <= :as_of
                GROUP BY ds
                ORDER BY ds;
            """)
            result = db.execute(query, {"node_name": node_name, "as_of": target_date}).fetchall()
            
            raw_df = pd.DataFrame(result, columns=['ds', 'y', 'event_count'])
            raw_df['ds'] = pd.to_datetime(raw_df['ds'])
            
            start_date = target_date - timedelta(days=30)
            full_range = pd.date_range(start=start_date, end=target_date, freq='D')
            df = pd.DataFrame({'ds': full_range})
            df = df.merge(raw_df, on='ds', how='left').fillna(0)
            
            model_path = "models/forecast_xgboost_news.json"
            if not os.path.exists(model_path):
                model_path = "models/forecast_xgboost.json"
                
            model = xgb.XGBRegressor()
            model.load_model(model_path)
            
            from src.predictive_forecasting import load_temporal_enriched_events, create_future_risk_projections, get_news_risk_for_date
            events = load_temporal_enriched_events()
            news_projections = create_future_risk_projections(events, forecast_days=30)
            
            forecast_points = []
            current_df = df.copy()
            
            for i in range(1, 15):
                next_date = target_date + timedelta(days=i)
                news_risk = get_news_risk_for_date(news_projections, node_name, next_date)
                
                features = {
                    'risk_lag_1': current_df['y'].iloc[-1],
                    'risk_lag_2': current_df['y'].iloc[-2],
                    'risk_lag_3': current_df['y'].iloc[-3],
                    'risk_lag_7': current_df['y'].iloc[-7],
                    'rolling_avg_7': current_df['y'].tail(7).mean(),
                    'news_risk': news_risk
                }
                
                X = pd.DataFrame([features])
                yhat = model.predict(X)[0]
                yhat = max(0, float(yhat))
                
                margin = 35.0 + 5.0 * i + 0.4 * yhat
                yhat_lower = max(0.0, yhat - margin)
                yhat_upper = yhat + margin
                
                forecast_points.append({
                    "ds": next_date,
                    "yhat": round(yhat, 2),
                    "yhat_lower": round(yhat_lower, 2),
                    "yhat_upper": round(yhat_upper, 2),
                    "news_contribution": round(news_risk, 2),
                    "historical_contribution": round(yhat - news_risk if yhat > news_risk else 0, 2)
                })
                
                new_row = pd.DataFrame({
                    'ds': [pd.Timestamp(next_date)],
                    'y': [yhat],
                    'event_count': [0]
                })
                current_df = pd.concat([current_df, new_row], ignore_index=True)
    
            return [
                {
                    **p,
                    "method": "xgboost-news"
                }
                for p in forecast_points
            ]
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Unhandled error generating forecast for '{node_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not generate forecast: {e}")

@app.get("/suppliers/{node_name}/hybrid_forecast", response_model=List[HybridForecastPoint], tags=["Forecasting"])
def get_hybrid_forecast(
    node_name: str, 
    as_of: Optional[date] = Depends(_parse_as_of_optional),
    db: Session = Depends(get_db)
):
    """
    Legacy endpoint redirected to use the new XGBoost forecast logic.
    """
    try:
        points = get_risk_forecast(node_name, as_of, db)
        # Add dummy news/historical breakdown for UI compatibility
        return [
            {
                **p,
                "news_contribution": 0.0,
                "historical_contribution": p["yhat"],
                "method": "xgboost-recursive"
            }
            for p in points
        ]
    except Exception as e:
        logger.error(f"❌ Error in hybrid forecast redirect: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/forecast-snapshots/dates", tags=["Forecasting"])
@app.get("/api/forecast-snapshots/dates", tags=["Forecasting"], include_in_schema=False)
def get_forecast_snapshot_dates(
    node_name: Optional[str] = Query(None, description="Limit to dates that exist for this node"),
    method: str = Query("xgboost", description="Forecast method (xgboost or prophet)"),
    db: Session = Depends(get_db),
):
    """Distinct forecast_date values stored (newest first)."""
    from src.forecast_snapshots import list_snapshot_dates

    try:
        dates = list_snapshot_dates(db, node_name, method=method)
        return {"dates": [d.isoformat() for d in dates]}
    except Exception as e:
        logger.error("Error listing forecast snapshot dates: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/suppliers/{node_name}/forecast_snapshot",
    response_model=ForecastSnapshotResponse,
    tags=["Forecasting"],
)
@app.get(
    "/api/suppliers/{node_name}/forecast_snapshot",
    response_model=ForecastSnapshotResponse,
    tags=["Forecasting"],
    include_in_schema=False,
)
def get_forecast_snapshot(
    node_name: str,
    snapshot_date: date = Query(..., alias="date", description="Forecast origin date (YYYY-MM-DD)"),
    include_actuals: bool = Query(True, description="Include realized daily sum(risk_score) per horizon day"),
    method: str = Query("xgboost", description="Forecast method (xgboost or prophet)"),
    db: Session = Depends(get_db),
):
    """
    Load persisted daily Prophet snapshot for this node and date; if missing, generate, store (first write wins), return.
    """
    from src.forecast_snapshots import (
        SOURCE_ON_DEMAND,
        compute_accuracy_metrics,
        ensure_snapshot_for_node,
        fetch_actuals_for_horizon,
        utc_today,
    )

    try:
        today = utc_today()
        if snapshot_date > today:
            raise HTTPException(status_code=400, detail="forecast snapshot date cannot be in the future.")
        row = db.execute(
            text("SELECT 1 FROM suppliers WHERE node_name = :n LIMIT 1"),
            {"n": node_name},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Unknown supplier node: {node_name}")

        rows, generated = ensure_snapshot_for_node(db, node_name, snapshot_date, SOURCE_ON_DEMAND, method=method)
        if len(rows) < 14:
            raise HTTPException(
                status_code=404,
                detail=f"Could not build a 14-day forecast snapshot for '{node_name}' on {snapshot_date}.",
            )

        horizon_days = [r["ds"] if not isinstance(r["ds"], datetime) else r["ds"].date() for r in rows]
        actuals_map = (
            fetch_actuals_for_horizon(db, node_name, horizon_days) if include_actuals else {}
        )

        points: List[ForecastSnapshotPoint] = []
        for r in rows:
            ds = r["ds"]
            if isinstance(ds, datetime):
                ds = ds.date()
            y_act = None
            if include_actuals:
                y_act = None if ds > today else actuals_map.get(ds, 0.0)
            points.append(
                ForecastSnapshotPoint(
                    ds=ds,
                    yhat=float(r["yhat"]),
                    yhat_lower=float(r["yhat_lower"]),
                    yhat_upper=float(r["yhat_upper"]),
                    y_actual=y_act,
                )
            )

        mae = None
        completed = 0
        if include_actuals:
            mae, completed, _ = compute_accuracy_metrics([p.model_dump() for p in points], today)

        return ForecastSnapshotResponse(
            node_name=node_name,
            forecast_date=snapshot_date,
            points=points,
            generated_on_demand=generated,
            mae=mae,
            completed_days=completed,
            horizon_days=len(points),
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error("forecast_snapshot failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


def _run_snapshot_job_sync(forecast_date: date, method: str = "xgboost") -> None:
    if SessionLocal is None:
        logger.error("SessionLocal not configured; skip snapshot job")
        return
    from src.forecast_snapshots import SOURCE_SCHEDULED, snapshot_all_nodes_for_date

    s = SessionLocal()
    try:
        snapshot_all_nodes_for_date(s, forecast_date, SOURCE_SCHEDULED, method=method)
    except Exception as e:
        logger.error("Background forecast snapshot job failed: %s", e, exc_info=True)
    finally:
        s.close()


@app.post("/admin/forecast-snapshots/run", tags=["Admin"])
def admin_run_forecast_snapshots(
    background_tasks: BackgroundTasks,
    forecast_date: Optional[date] = Query(
        None,
        description="Defaults to today (UTC). Generates snapshots for all suppliers.",
    ),
    method: str = Query("xgboost", description="Forecast method (xgboost or prophet)"),
):
    """Queue daily snapshot generation for all supplier nodes (non-blocking)."""
    from src.forecast_snapshots import utc_today
 
    fd = forecast_date or utc_today()
    background_tasks.add_task(_run_snapshot_job_sync, fd, method)
    return {"status": "queued", "forecast_date": fd.isoformat(), "method": method}


@app.get("/events/forecasted", response_model=List[Event], tags=["Events"])
def get_forecasted_events(
    count: int = Query(50, description="Number of forecasted events to retrieve", ge=1, le=200),
    db: Session = Depends(get_db),
    as_of: Optional[date] = Depends(_parse_as_of_optional),
):
    """
    Retrieves events that are PREDICTIVE (about future events like upcoming hurricanes, strikes).
    These events have temporal information indicating they predict future occurrences.
    Only includes events with valid latitude, longitude, and future predicted dates.
    """
    try:
        if as_of is not None and as_of > date.today():
            raise HTTPException(status_code=400, detail="as_of cannot be in the future.")
        criticality_map = get_criticality_map(db)
        as_filter = ""
        params = {"count": count}
        if as_of is not None:
            as_filter = "AND article_timestamp::date <= :as_of"
            params["as_of"] = as_of

        # Query for events with predictive temporal information
        # We're using jsonb operators to filter for is_predictive = true
        query = text(f"""
            SELECT * FROM events
            WHERE latitude IS NOT NULL 
            AND longitude IS NOT NULL
            AND temporal_info IS NOT NULL
            AND temporal_info->>'is_predictive' = 'true'
            AND temporal_info->>'predicted_date' IS NOT NULL
            {as_filter}
            ORDER BY 
                CASE 
                    WHEN temporal_info->>'predicted_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                    THEN (temporal_info->>'predicted_date')::date
                    ELSE CURRENT_DATE + INTERVAL '100 years'
                END ASC
            LIMIT :count;
        """)
        result = db.execute(query, params).fetchall()
        
        events = process_events_with_impact(result, criticality_map)
        logger.info(f"✅ Retrieved {len(events)} forecasted events")
        return events
        
    except Exception as e:
        logger.error(f"Error fetching forecasted events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not fetch forecasted events: {e}")

@app.get("/events/forecasted/by_node/{node_name}", response_model=List[Event], tags=["Events"])
def get_forecasted_events_by_node(
    node_name: str,
    limit: int = Query(50, description="Max number of forecasted events for the node", ge=1, le=200),
    db: Session = Depends(get_db),
    as_of: Optional[date] = Depends(_parse_as_of_optional),
):
    """
    Retrieves PREDICTIVE events for a specific node.
    These are events that predict future occurrences (hurricanes, strikes, etc).
    """
    try:
        if as_of is not None and as_of > date.today():
            raise HTTPException(status_code=400, detail="as_of cannot be in the future.")
        criticality_map = get_criticality_map(db)
        as_filter = ""
        params = {"node_name": node_name, "limit": limit}
        if as_of is not None:
            as_filter = "AND article_timestamp::date <= :as_of"
            params["as_of"] = as_of

        query = text(f"""
            SELECT * FROM events
            WHERE matched_node @> :node_name_json
            AND latitude IS NOT NULL 
            AND longitude IS NOT NULL
            AND temporal_info IS NOT NULL
            AND temporal_info->>'is_predictive' = 'true'
            AND temporal_info->>'predicted_date' IS NOT NULL
            {as_filter}
            ORDER BY 
                CASE 
                    WHEN temporal_info->>'predicted_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                    THEN (temporal_info->>'predicted_date')::date
                    ELSE CURRENT_DATE + INTERVAL '100 years'
                END ASC
            LIMIT :limit;
        """)
        params["node_name_json"] = json.dumps([node_name])
        result = db.execute(query, params).fetchall()
        
        events = process_events_with_impact(result, criticality_map)
        logger.info(f"✅ Retrieved {len(events)} forecasted events for node '{node_name}'")
        return events
        
    except Exception as e:
        logger.error(f"Error fetching forecasted events for node '{node_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not fetch forecasted events for node '{node_name}': {e}")