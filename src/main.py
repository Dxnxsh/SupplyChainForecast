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
from prophet import Prophet
import os
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration: Database Connection ---
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING", "postgresql://postgres:your_password@localhost:5432/supply_chain_db")

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
        node_name = event_dict.get('matched_node')
        risk_score = event_dict.get('risk_score') or 0.0
        criticality = criticality_map.get(node_name, 1) # Default criticality to 1 if node not found

        # Calculate impact score: Risk Score * Node Criticality
        event_dict['impact_score'] = round(risk_score * criticality, 2)
        if event_dict.get('predicted_impact_score') is not None:
            try:
                event_dict['predicted_impact_score'] = float(event_dict['predicted_impact_score'])
            except (TypeError, ValueError):
                event_dict['predicted_impact_score'] = None
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
        matched_node = :n
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


# --- API Endpoints ---

@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Welcome to the Supply Chain Forecaster API!"}

@app.get("/suppliers", response_model=List[Supplier], tags=["Suppliers"])
def get_all_suppliers(db: Session = Depends(get_db)):
    """
    Retrieves a list of all defined supply chain nodes/suppliers, including their criticality.
    """
    try:
        # NEW: Ensure 'criticality' column is selected
        query = text("SELECT id, node_name, latitude, longitude, country, current_risk_score, criticality FROM suppliers")
        result = db.execute(query).fetchall()
        return [Supplier.from_orm(row._mapping) for row in result]
    except Exception as e:
        logger.error(f"Error fetching suppliers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not fetch suppliers: {e}")

@app.get("/events/latest", response_model=List[Event], tags=["Events"])
def get_latest_events(
    count: int = Query(50, description="Number of latest events to retrieve", ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Retrieves the latest supply chain events, ordered by timestamp,
    calculating an impact score for each.
    Only includes events with valid latitude and longitude.
    """
    try:
        criticality_map = get_criticality_map(db)
        query = text(f"""
            SELECT * FROM events
                        WHERE latitude IS NOT NULL
                            AND longitude IS NOT NULL
                            AND article_timestamp IS NOT NULL
                        ORDER BY article_timestamp DESC NULLS LAST
            LIMIT :count;
        """)
        result = db.execute(query, {"count": count}).fetchall()
        return process_events_with_impact(result, criticality_map)
    except Exception as e:
        logger.error(f"Error fetching latest events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not fetch latest events: {e}")

@app.get("/events/by_node/{node_name}", response_model=List[Event], tags=["Events"])
def get_events_by_node(
    node_name: str,
    limit: int = Query(100, description="Max number of events for the node", ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Retrieves events associated with a specific supply chain node,
    calculating an impact score for each.
    Only includes events with valid latitude and longitude.
    """
    try:
        criticality_map = get_criticality_map(db)
        query = text("""
            SELECT * FROM events
                        WHERE matched_node = :node_name
                            AND latitude IS NOT NULL
                            AND longitude IS NOT NULL
                            AND article_timestamp IS NOT NULL
                        ORDER BY article_timestamp DESC NULLS LAST
            LIMIT :limit;
        """)
        result = db.execute(query, {"node_name": node_name, "limit": limit}).fetchall()
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
                WHERE matched_node = :n
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
def get_dashboard_summary(db: Session = Depends(get_db)):
    """
    Provides a summary of total events, average risk, and most common event type across all data.
    """
    try:
        total_events_query = text("SELECT COUNT(*) FROM events;")
        total_events = db.execute(total_events_query).scalar()

        avg_risk_query = text("SELECT AVG(risk_score) FROM events WHERE risk_score IS NOT NULL;")
        avg_risk_score = db.execute(avg_risk_query).scalar()

        # Most common event type using jsonb_array_elements_text for robustness
        most_common_event_type_query = text("""
            SELECT jsonb_array_elements_text(potential_event_types) as event_type
            FROM events
            WHERE potential_event_types IS NOT NULL AND potential_event_types != '[]'::jsonb
            GROUP BY event_type
            ORDER BY COUNT(*) DESC
            LIMIT 1;
        """)
        most_common_event_type_result = db.execute(most_common_event_type_query).scalar()

        return EventSummary(
            total_events=total_events,
            avg_risk_score=avg_risk_score,
            most_common_event_type=most_common_event_type_result
        )
    except Exception as e:
        logger.error(f"Error fetching summary data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not fetch summary: {e}")

@app.get("/suppliers/{node_name}/forecast", response_model=List[ForecastPoint], tags=["Forecasting"])
def get_risk_forecast(node_name: str, db: Session = Depends(get_db)):
    """
    Generates a 14-day risk score forecast for a specific supplier node using Facebook Prophet.
    """
    try:
        # 1. Fetch historical risk data for the node
        query = text("""
            SELECT article_timestamp::date as ds, SUM(risk_score) as y
            FROM events
            WHERE matched_node = :node_name AND article_timestamp IS NOT NULL AND risk_score IS NOT NULL
            GROUP BY ds
            ORDER BY ds;
        """)
        result = db.execute(query, {"node_name": node_name}).fetchall()
        
        if len(result) < 2:
            logger.warning(f"Not enough historical data ({len(result)} points) for node '{node_name}' to generate a forecast.")
            raise HTTPException(
                status_code=404,
                detail=f"Not enough historical data to generate a forecast for '{node_name}'. Need at least 2 days of data."
            )

        # 2. Prepare data for Prophet — zero-fill gaps so seasonality has enough points
        raw_df = pd.DataFrame(result, columns=['ds', 'y'])
        raw_df['ds'] = pd.to_datetime(raw_df['ds'])
        raw_df['y'] = pd.to_numeric(raw_df['y'])

        full_range = pd.date_range(start=raw_df['ds'].min(), end=raw_df['ds'].max(), freq='D')
        df = pd.DataFrame({'ds': full_range, 'y': 0.0})
        df = df.merge(raw_df.rename(columns={'y': 'y_actual'}), on='ds', how='left')
        df['y'] = df['y_actual'].fillna(df['y'])
        df = df[['ds', 'y']]

        # 3. Train the Prophet model
        model = Prophet(
            daily_seasonality=False, 
            weekly_seasonality=True, 
            yearly_seasonality=True,
            changepoint_prior_scale=0.05
        )
        model.fit(df)
        
        # 4. Generate future dates and make a prediction
        future = model.make_future_dataframe(periods=14) # Forecast for the next 14 days
        forecast = model.predict(future)
        
        # 5. Format the response
        forecast_data = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(14).copy()
        
        # Clip values to ensure they are non-negative
        forecast_data['yhat'] = forecast_data['yhat'].clip(lower=0)
        forecast_data['yhat_lower'] = forecast_data['yhat_lower'].clip(lower=0)
        forecast_data['yhat_upper'] = forecast_data['yhat_upper'].clip(lower=0)
        
        # Convert 'ds' to date object for Pydantic model
        forecast_data['ds'] = forecast_data['ds'].dt.date

        # Convert DataFrame to a list of dictionaries for Pydantic
        response_data = forecast_data.to_dict('records')
        return response_data
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Unhandled error generating forecast for '{node_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not generate forecast: {e}")

@app.get("/suppliers/{node_name}/hybrid_forecast", response_model=List[HybridForecastPoint], tags=["Forecasting"])
def get_hybrid_forecast(node_name: str):
    """
    Generates a 14-day HYBRID forecast that combines:
    1. Historical trends (Prophet time-series)
    2. Forward-looking predictions from news about upcoming events (hurricanes, strikes, etc.)
    
    This endpoint reads from pre-generated forecast files created by predictive_forecasting.py
    """
    try:
        # Try to load pre-generated forecast
        forecast_file = f"data/forecasts/{node_name.replace(' ', '_')}_forecast.json"
        
        if not os.path.exists(forecast_file):
            logger.warning(f"No hybrid forecast file found for '{node_name}' at {forecast_file}")
            raise HTTPException(
                status_code=404,
                detail=f"No hybrid forecast available for '{node_name}'. Run predictive_forecasting.py to generate forecasts."
            )
        
        with open(forecast_file, 'r') as f:
            forecast_data = json.load(f)
        
        # Validate and return
        if not forecast_data:
            raise HTTPException(
                status_code=404,
                detail=f"Forecast file is empty for '{node_name}'."
            )
        
        return forecast_data
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Error loading hybrid forecast for '{node_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not load hybrid forecast: {e}")

@app.get("/events/forecasted", response_model=List[Event], tags=["Events"])
def get_forecasted_events(
    count: int = Query(50, description="Number of forecasted events to retrieve", ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Retrieves events that are PREDICTIVE (about future events like upcoming hurricanes, strikes).
    These events have temporal information indicating they predict future occurrences.
    Only includes events with valid latitude, longitude, and future predicted dates.
    """
    try:
        criticality_map = get_criticality_map(db)
        
        # Query for events with predictive temporal information
        # We're using jsonb operators to filter for is_predictive = true
        query = text("""
            SELECT * FROM events
            WHERE latitude IS NOT NULL 
            AND longitude IS NOT NULL
            AND temporal_info IS NOT NULL
            AND temporal_info->>'is_predictive' = 'true'
            AND temporal_info->>'predicted_date' IS NOT NULL
            ORDER BY 
                CASE 
                    WHEN temporal_info->>'predicted_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                    THEN (temporal_info->>'predicted_date')::date
                    ELSE CURRENT_DATE + INTERVAL '100 years'
                END ASC
            LIMIT :count;
        """)
        result = db.execute(query, {"count": count}).fetchall()
        
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
    db: Session = Depends(get_db)
):
    """
    Retrieves PREDICTIVE events for a specific node.
    These are events that predict future occurrences (hurricanes, strikes, etc).
    """
    try:
        criticality_map = get_criticality_map(db)
        
        query = text("""
            SELECT * FROM events
            WHERE matched_node = :node_name
            AND latitude IS NOT NULL 
            AND longitude IS NOT NULL
            AND temporal_info IS NOT NULL
            AND temporal_info->>'is_predictive' = 'true'
            AND temporal_info->>'predicted_date' IS NOT NULL
            ORDER BY 
                CASE 
                    WHEN temporal_info->>'predicted_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                    THEN (temporal_info->>'predicted_date')::date
                    ELSE CURRENT_DATE + INTERVAL '100 years'
                END ASC
            LIMIT :limit;
        """)
        result = db.execute(query, {"node_name": node_name, "limit": limit}).fetchall()
        
        events = process_events_with_impact(result, criticality_map)
        logger.info(f"✅ Retrieved {len(events)} forecasted events for node '{node_name}'")
        return events
        
    except Exception as e:
        logger.error(f"Error fetching forecasted events for node '{node_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not fetch forecasted events for node '{node_name}': {e}")