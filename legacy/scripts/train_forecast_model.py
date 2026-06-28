import os
import sys
import json
import pandas as pd
import xgboost as xgb
from sqlalchemy import text
from datetime import date, timedelta
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.append(os.getcwd())
from src.load_to_db import get_db_engine

def get_training_data(engine):
    query = text("""
        SELECT 
            matched_node_element as node_name,
            article_timestamp::date as ds,
            SUM(risk_score) as y,
            COUNT(*) as event_count
        FROM events, jsonb_array_elements_text(matched_node) as matched_node_element
        WHERE article_timestamp IS NOT NULL AND risk_score IS NOT NULL
        GROUP BY node_name, ds
        ORDER BY node_name, ds;
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

def create_features(df):
    """Generates lag and rolling window features for recursive forecasting."""
    df = df.sort_values(['node_name', 'ds'])
    
    # Fill gaps with 0 to ensure continuous time-series for lags
    all_nodes = df['node_name'].unique()
    all_dfs = []
    for node in all_nodes:
        node_df = df[df['node_name'] == node].copy()
        node_df['ds'] = pd.to_datetime(node_df['ds'])
        
        full_range = pd.date_range(start=node_df['ds'].min(), end=node_df['ds'].max(), freq='D')
        full_df = pd.DataFrame({'ds': full_range, 'node_name': node})
        full_df = full_df.merge(node_df, on=['ds', 'node_name'], how='left').fillna(0)
        
        # Lag features (1-7 days)
        for i in range(1, 8):
            full_df[f'risk_lag_{i}'] = full_df['y'].shift(i)
        
        # Rolling window features
        full_df['rolling_avg_7'] = full_df['y'].rolling(window=7).mean()
        full_df['rolling_avg_14'] = full_df['y'].rolling(window=14).mean()
        full_df['event_count_7'] = full_df['event_count'].rolling(window=7).sum()
        
        all_dfs.append(full_df)
    
    final_df = pd.concat(all_dfs).dropna()
    return final_df

def train_model():
    engine = get_db_engine()
    if not engine:
        logger.error("Could not connect to database.")
        return

    logger.info("📊 Fetching training data...")
    df = get_training_data(engine)
    if df.empty:
        logger.warning("No training data found.")
        return

    logger.info("🛠 Engineering features...")
    featured_df = create_features(df)
    
    X = featured_df[[
        'risk_lag_1', 'risk_lag_2', 'risk_lag_3', 'risk_lag_4', 
        'risk_lag_5', 'risk_lag_6', 'risk_lag_7',
        'rolling_avg_7', 'rolling_avg_14', 'event_count_7'
    ]]
    y = featured_df['y']

    logger.info(f"🚀 Training XGBoost model on {len(featured_df)} samples...")
    model = xgb.XGBRegressor(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        colsample_bytree=0.8,
        objective='reg:squarederror'
    )
    model.fit(X, y)

    # Save model
    os.makedirs("models", exist_ok=True)
    model.save_model("models/forecast_xgboost.json")
    logger.info("✅ Model saved to models/forecast_xgboost.json")

if __name__ == "__main__":
    train_model()
