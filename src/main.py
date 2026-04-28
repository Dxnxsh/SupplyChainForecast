# src/main.py

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
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
    impact_score: Optional[float] = None # NEW: Added impact_score
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

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Supply Chain Disruption Forecaster API",
    description="API to serve risk data and forecasts for supply chain nodes and events.",
    version="1.2.0" # Updated version number
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
        risk_score = event_dict.get('risk_score', 0.0)
        criticality = criticality_map.get(node_name, 1) # Default criticality to 1 if node not found

        # Calculate impact score: Risk Score * Node Criticality
        event_dict['impact_score'] = round(risk_score * criticality, 2)
        processed.append(Event.from_orm(event_dict))
    return processed

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