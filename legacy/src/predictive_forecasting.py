# src/predictive_forecasting.py
"""
Enhanced forecasting that combines:
1. Historical time-series forecasting (Prophet)
2. Forward-looking predictions from news content (temporal extraction)
3. Hybrid model that weights both approaches

This enables predictions based on news about upcoming events (hurricanes, strikes, etc.)
"""

import json
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
from prophet import Prophet
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Configuration ---
CONFIDENCE_WEIGHTS = {
    'high': 1.0,
    'medium': 0.7,
    'low': 0.4,
    'none': 0.0
}

TIME_DECAY_FACTOR = 0.85  # How much to decay predicted risk as we move away from predicted date


def _build_recent_average_baseline(node_events, forecast_days):
    """
    Build a lightweight fallback baseline from recent historical risk.

    Prophet can fail or become uninformative when a node has too few observations or
    when the historical series is extremely sparse. In that case we still want a
    stable historical contribution so the hybrid forecast is not driven entirely by
    news heuristics.
    """
    risk_by_date = defaultdict(float)

    for event in node_events:
        timestamp = event.get('article_timestamp')
        risk_score = event.get('risk_score', 0)

        if timestamp and risk_score > 0:
            try:
                date = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date()
                risk_by_date[date] += risk_score
            except Exception:
                continue

    if not risk_by_date:
        return None

    recent_dates = sorted(risk_by_date.keys())[-min(7, len(risk_by_date)) :]
    recent_values = [risk_by_date[d] for d in recent_dates]

    if not recent_values:
        return None

    baseline_value = float(np.mean(recent_values))
    if baseline_value <= 0:
        return None

    dates = [datetime.now().date() + timedelta(days=i) for i in range(1, forecast_days + 1)]
    return pd.DataFrame({
        'ds': pd.to_datetime(dates),
        'yhat': [baseline_value] * forecast_days,
        'yhat_lower': [baseline_value * 0.8] * forecast_days,
        'yhat_upper': [baseline_value * 1.2] * forecast_days,
    })


def load_temporal_enriched_events(filepath="data/processed/temporal_enriched_events.jsonl"):
    """Load events with temporal information."""
    if not os.path.exists(filepath):
        logger.error(f"Temporal enriched events not found at {filepath}")
        return []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f]


def create_future_risk_projections(events, forecast_days=14):
    """
    Creates a forward-looking risk projection based on predicted event dates.
    Returns a DataFrame with dates and projected risk scores.
    """
    logger.info(f"Creating future risk projections for {len(events)} events...")
    
    # Dictionary to accumulate risk by date and node
    future_risk_by_date_node = defaultdict(lambda: defaultdict(float))
    
    today = datetime.now().date()
    
    for event in events:
        temporal_info = event.get('temporal_info') or {}
        
        # Only process events with predicted future dates
        if not temporal_info.get('is_predictive') or not temporal_info.get('predicted_date'):
            continue
        
        predicted_date_str = temporal_info['predicted_date']
        confidence = temporal_info.get('predicted_date_confidence', 'none')
        risk_score = event.get('risk_score', 0)
        node_name_raw = event.get('matched_node')
        if not node_name_raw or risk_score == 0:
            continue

        # Handle matched_node being either a string or a list of strings
        if isinstance(node_name_raw, list):
            target_nodes = node_name_raw
        else:
            target_nodes = [node_name_raw]
        
        try:
            predicted_date = datetime.fromisoformat(predicted_date_str).date()
        except:
            continue

        # Reproject historical predictions forward using the original lead-time so that
        # articles from months ago still contribute to the near-future forecast window.
        days_until = temporal_info.get('days_until_event')
        if days_until is not None and days_until >= 0:
            projected_date = today + timedelta(days=max(1, days_until))
        else:
            projected_date = predicted_date

        if (projected_date - today).days <= 0 or (projected_date - today).days > forecast_days:
            continue

        predicted_date = projected_date
        
        # Apply confidence weight to the risk score
        confidence_weight = CONFIDENCE_WEIGHTS.get(confidence, 0.5)
        weighted_risk = risk_score * confidence_weight
        
        # Project risk around the predicted date (peak on predicted date, decay before/after)
        # This creates a bell curve of risk around the predicted event
        for offset in range(-2, 3):  # 2 days before and after
            projection_date = predicted_date + timedelta(days=offset)
            if projection_date > today and (projection_date - today).days <= forecast_days:
                # Calculate decay based on distance from predicted date
                if offset == 0:
                    decay = 1.0  # Peak on predicted date
                else:
                    decay = TIME_DECAY_FACTOR ** abs(offset)
                
                projected_risk = weighted_risk * decay
                for node_name in target_nodes:
                    if node_name: # Ensure node_name is not None or empty
                        future_risk_by_date_node[projection_date][node_name] += projected_risk
    
    logger.info(f"Generated projections for {len(future_risk_by_date_node)} dates")
    return future_risk_by_date_node


def get_news_risk_for_date(future_risk_by_date, node_name, target_date):
    """
    Returns aggregated news risk for a specific node and date from the projection dict.
    """
    if isinstance(target_date, datetime):
        target_date = target_date.date()
    
    date_data = future_risk_by_date.get(target_date, {})
    return date_data.get(node_name, 0.0)


def get_historical_prophet_forecast(events, node_name, forecast_days=14):
    """
    Generates a Prophet-based forecast using historical data.
    Returns a DataFrame with dates and forecasted values.
    """
    # Filter events for this node
    node_events = []
    for e in events:
        matched = e.get('matched_node')
        if isinstance(matched, list):
            if node_name in matched:
                node_events.append(e)
        elif matched == node_name:
            node_events.append(e)
    
    if not node_events:
        return None
    
    # Aggregate historical risk by date
    risk_by_date = defaultdict(float)
    for event in node_events:
        timestamp = event.get('article_timestamp')
        risk_score = event.get('risk_score', 0)
        
        if timestamp and risk_score > 0:
            try:
                date = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date()
                risk_by_date[date] += risk_score
            except:
                continue
    
    if len(risk_by_date) < 2:
        return None

    # Build a continuous daily series (zero-fill gaps so Prophet has enough data points)
    min_date = min(risk_by_date.keys())
    max_date = max(risk_by_date.keys())
    all_dates = pd.date_range(start=min_date, end=max_date, freq='D')
    df = pd.DataFrame({'ds': all_dates, 'y': 0.0})
    for d, risk in risk_by_date.items():
        df.loc[df['ds'].dt.date == d, 'y'] = risk
    
    try:
        # Train Prophet model
        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=True,
            changepoint_prior_scale=0.05
        )
        model.fit(df)
        
        # Generate future dates aligned to actual forecast dates (today + 1 to today + forecast_days)
        today = datetime.now().date()
        future_dates = [today + timedelta(days=i+1) for i in range(forecast_days)]
        future_df = pd.DataFrame({'ds': pd.to_datetime(future_dates)})
        
        # Predict for the actual future dates
        forecast = model.predict(future_df)
        
        # Extract the relevant columns
        future_forecast = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].copy()
        future_forecast['yhat'] = future_forecast['yhat'].clip(lower=0)
        future_forecast['yhat_lower'] = future_forecast['yhat_lower'].clip(lower=0)
        future_forecast['yhat_upper'] = future_forecast['yhat_upper'].clip(lower=0)

        result = future_forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]
        if result.empty or result['yhat'].sum() <= 0:
            return _build_recent_average_baseline(node_events, forecast_days)
        return result
        
    except Exception as e:
        logger.warning(f"Prophet forecast failed for {node_name}: {e}")
        return _build_recent_average_baseline(node_events, forecast_days)


def create_hybrid_forecast(events, node_name, forecast_days=14, alpha=0.6):
    """
    Creates a hybrid forecast that combines:
    - Historical trend forecasting (Prophet) with weight (1-alpha)
    - Forward-looking news projections with weight alpha
    
    Args:
        alpha: Weight for news-based projections (0-1). Higher = more weight on news.
    
    Returns a DataFrame with hybrid forecast.
    """
    logger.info(f"Creating hybrid forecast for {node_name}...")
    
    # Get future risk projections from news
    future_risk_by_date = create_future_risk_projections(events, forecast_days)
    
    # Get historical Prophet forecast
    prophet_forecast = get_historical_prophet_forecast(events, node_name, forecast_days)

    if prophet_forecast is None:
        node_events = []
        for e in events:
            matched = e.get('matched_node')
            if isinstance(matched, list):
                if node_name in matched:
                    node_events.append(e)
            elif matched == node_name:
                node_events.append(e)
        prophet_forecast = _build_recent_average_baseline(node_events, forecast_days)
    
    # Create date range for forecast
    start_date = datetime.now().date() + timedelta(days=1)
    dates = [start_date + timedelta(days=i) for i in range(forecast_days)]
    
    # Initialize forecast data
    forecast_data = []
    
    for date in dates:
        # Get news-based projection for this date and node
        news_risk = future_risk_by_date.get(date, {}).get(node_name, 0.0)
        
        # Get Prophet forecast for this date
        prophet_risk = 0.0
        prophet_lower = 0.0
        prophet_upper = 0.0
        
        if prophet_forecast is not None:
            matching_rows = prophet_forecast[prophet_forecast['ds'].dt.date == date]
            if not matching_rows.empty:
                prophet_risk = matching_rows.iloc[0]['yhat']
                prophet_lower = matching_rows.iloc[0]['yhat_lower']
                prophet_upper = matching_rows.iloc[0]['yhat_upper']
        
        # Combine using weighted average
        if news_risk > 0:
            # If we have news-based projection, use weighted combination
            hybrid_risk = (alpha * news_risk) + ((1 - alpha) * prophet_risk)
            # Boost confidence intervals when we have news
            hybrid_lower = hybrid_risk * 0.7
            hybrid_upper = hybrid_risk * 1.3
        else:
            # If no news projection, fall back to Prophet
            hybrid_risk = prophet_risk
            hybrid_lower = prophet_lower
            hybrid_upper = prophet_upper
        
        forecast_data.append({
            'ds': date,
            'yhat': round(hybrid_risk, 2),
            'yhat_lower': round(max(0, hybrid_lower), 2),
            'yhat_upper': round(hybrid_upper, 2),
            'news_contribution': round(news_risk, 2),
            'historical_contribution': round(prophet_risk, 2),
            'method': 'hybrid' if news_risk > 0 else 'historical_only'
        })
    
    df = pd.DataFrame(forecast_data)
    logger.info(f"Hybrid forecast created with {len(df)} days")
    return df


from src.load_to_db import SUPPLIER_NODES

def generate_all_node_forecasts(events, forecast_days=14, output_dir="data/forecasts"):
    """
    Generates hybrid forecasts for all nodes defined in SUPPLIER_NODES.
    Saves individual JSON files for each node.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Get all defined nodes
    nodes = list(SUPPLIER_NODES.keys())
    logger.info(f"Generating forecasts for {len(nodes)} defined nodes...")
    
    forecasts = {}
    
    for node in nodes:
        try:
            forecast_df = create_hybrid_forecast(events, node, forecast_days)
            
            if forecast_df is not None:
                # Convert to JSON-serializable format
                forecast_dict = forecast_df.to_dict('records')
                
                # Convert date objects to strings
                for record in forecast_dict:
                    if isinstance(record['ds'], datetime):
                        record['ds'] = record['ds'].date().isoformat()
                    elif hasattr(record['ds'], 'isoformat'):
                        record['ds'] = record['ds'].isoformat()
                
                forecasts[node] = forecast_dict
                
                # Save individual node forecast
                node_filename = f"{output_dir}/{node.replace(' ', '_')}_forecast.json"
                with open(node_filename, 'w') as f:
                    json.dump(forecast_dict, f, indent=2)
                
                logger.info(f"✅ Forecast generated for {node}")
        
        except Exception as e:
            logger.error(f"❌ Failed to generate forecast for {node}: {e}")
            continue
    
    # Save all forecasts in one file
    all_forecasts_path = f"{output_dir}/all_forecasts.json"
    with open(all_forecasts_path, 'w') as f:
        json.dump(forecasts, f, indent=2)
    
    logger.info(f"✅ All forecasts saved to {output_dir}")
    return forecasts


def analyze_forecast_drivers(forecast_df):
    """
    Analyzes what's driving the forecast (news vs historical trends).
    """
    total_risk = forecast_df['yhat'].sum()
    news_contribution = forecast_df['news_contribution'].sum()
    historical_contribution = forecast_df['historical_contribution'].sum()
    
    if total_risk > 0:
        news_pct = (news_contribution / (news_contribution + historical_contribution)) * 100
        historical_pct = (historical_contribution / (news_contribution + historical_contribution)) * 100
    else:
        news_pct = 0
        historical_pct = 0
    
    return {
        'total_forecasted_risk': round(total_risk, 2),
        'news_driven_percentage': round(news_pct, 1),
        'historical_driven_percentage': round(historical_pct, 1),
        'days_with_news_signals': int((forecast_df['news_contribution'] > 0).sum())
    }


def prepare_training_data_with_news(events, start_date="2025-07-01", end_date="2026-05-20"):
    """
    Prepares training data by joining historical risk with news projections.
    """
    logger.info(f"Preparing training data from {start_date} to {end_date}...")
    
    # 1. Calculate future_risk_by_date for the whole range
    # We use a large forecast_days to cover the whole training period
    news_risk_projections = create_future_risk_projections(events, forecast_days=365)
    
    training_rows = []
    
    # 2. Extract daily actual risk from events for each node
    from src.load_to_db import SUPPLIER_NODES
    nodes = list(SUPPLIER_NODES.keys())
    
    all_dates = pd.date_range(start=start_date, end=end_date, freq='D').date
    
    for node in nodes:
        # Get actual risk for this node
        node_actuals = defaultdict(float)
        for e in events:
            matched = e.get('matched_node')
            if (isinstance(matched, list) and node in matched) or (matched == node):
                ts = e.get('article_timestamp')
                if ts:
                    try:
                        d = pd.to_datetime(ts).date()
                        node_actuals[d] += e.get('risk_score', 0)
                    except:
                        continue
        
        # Build features for each date
        node_history = pd.DataFrame({'ds': all_dates, 'y': [node_actuals.get(d, 0.0) for d in all_dates]})
        
        for i in range(14, len(node_history)):
            current_date = node_history.iloc[i]['ds']
            y_target = node_history.iloc[i]['y']
            
            # Lag features
            features = {
                'target': y_target,
                'risk_lag_1': node_history.iloc[i-1]['y'],
                'risk_lag_2': node_history.iloc[i-2]['y'],
                'risk_lag_3': node_history.iloc[i-3]['y'],
                'risk_lag_7': node_history.iloc[i-7]['y'],
                'rolling_avg_7': node_history.iloc[i-7:i]['y'].mean(),
                'news_risk': get_news_risk_for_date(news_risk_projections, node, current_date)
            }
            training_rows.append(features)
            
    return pd.DataFrame(training_rows)


def train_news_enriched_model(events):
    """
    Trains and saves the news-enriched XGBoost model.
    """
    df = prepare_training_data_with_news(events)
    if df.empty:
        logger.error("No training data generated.")
        return
    
    import xgboost as xgb
    X = df.drop(columns=['target'])
    y = df['target']
    
    model = xgb.XGBRegressor(
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        random_state=42
    )
    
    logger.info(f"Training XGBoost on {len(df)} rows...")
    model.fit(X, y)
    
    model_dir = "models"
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "forecast_xgboost_news.json")
    model.save_model(model_path)
    logger.info(f"✅ Model saved to {model_path}")


def generate_edsf_forecast(events=None, node_name=None, forecast_days=14, session=None, target_date=None):
    """
    Generates a 14-day risk forecast using the Approach A model:
    A calibrated Prophet baseline (trained on average risk) with a 
    gated news boost for high-confidence, future-dated events.
    """
    from sqlalchemy import text
    
    if target_date is None:
        target_date = datetime.now().date()
    elif isinstance(target_date, str):
        target_date = datetime.fromisoformat(target_date[:10]).date()
    elif isinstance(target_date, datetime):
        target_date = target_date.date()
        
    logger.info(f"Generating Prophet forecast for node '{node_name}' as of {target_date}...")

    # --- Step 1: Aggregate Historical Risk (Average) ---
    risk_by_date = defaultdict(list)
    
    if session is not None:
        # Query database directly for history using AVG
        q = text("""
            SELECT article_timestamp::date AS ds, AVG(risk_score) AS y
            FROM events
            WHERE matched_node @> jsonb_build_array(:node_name)
              AND article_timestamp IS NOT NULL
              AND risk_score IS NOT NULL
              AND article_timestamp::date <= :target_date
            GROUP BY ds
            ORDER BY ds;
        """)
        result = session.execute(q, {"node_name": node_name, "target_date": target_date}).fetchall()
        avg_risk_by_date = {row[0]: float(row[1]) for row in result if row[0]}
    else:
        # Filter from memory events list
        if not events:
            events = load_temporal_enriched_events()
            
        for e in events:
            matched = e.get('matched_node')
            is_match = False
            if isinstance(matched, list):
                if node_name in matched:
                    is_match = True
            elif matched == node_name:
                is_match = True
                
            if is_match:
                ts = e.get('article_timestamp')
                risk_score = e.get('risk_score', 0)
                if ts and risk_score > 0:
                    try:
                        d = pd.to_datetime(ts).date()
                        if d <= target_date:
                            risk_by_date[d].append(risk_score)
                    except:
                        continue
        avg_risk_by_date = {d: float(np.mean(scores)) for d, scores in risk_by_date.items() if scores}

    # --- Step 2: Training Window & Gap Handling ---
    # Cap training to last 120 days — older sparse history dilutes the learned baseline.
    train_start = target_date - timedelta(days=120)
    if avg_risk_by_date:
        min_date = max(min(avg_risk_by_date.keys()), train_start)
        if (target_date - min_date).days < 30:
            min_date = target_date - timedelta(days=30)
    else:
        min_date = target_date - timedelta(days=30)

    all_dates = pd.date_range(start=min_date, end=target_date, freq='D').date
    df = pd.DataFrame({'ds': all_dates, 'y': 0.0})
    for d, risk in avg_risk_by_date.items():
        mask = df['ds'] == d
        if mask.any():
            df.loc[mask, 'y'] = risk

    df['y_filtered'] = df['y']

    # Compute the all-days mean (including zero-event days) as the calibration target.
    # This is the correct level: Prophet should predict the unconditional daily average,
    # not just the average conditioned on having events.
    recent_30_start = target_date - timedelta(days=30)
    recent_30_dates = [d for d in all_dates if d >= recent_30_start]
    if len(recent_30_dates) >= 14:
        recent_mean = float(np.mean([avg_risk_by_date.get(d, 0.0) for d in recent_30_dates]))
    else:
        recent_mean = float(np.mean([avg_risk_by_date.get(d, 0.0) for d in all_dates]))
    recent_mean = recent_mean if recent_mean > 0 else None

    # --- Step 3: Compute Prophet Baseline & Intervals ---
    baseline_forecast = None
    if len(df[df['y_filtered'] > 0]) >= 2:
        try:
            prophet_df = pd.DataFrame({
                'ds': pd.to_datetime(df['ds']),
                'y': df['y_filtered']
            })
            model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=False,
                changepoint_prior_scale=0.25,  # more responsive to recent trend shifts
                interval_width=0.80,
            )
            model.fit(prophet_df)

            future_dates = [target_date + timedelta(days=i) for i in range(1, forecast_days + 1)]
            future_df = pd.DataFrame({'ds': pd.to_datetime(future_dates)})
            forecast = model.predict(future_df)

            baseline_forecast = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].copy()
            baseline_forecast['ds'] = baseline_forecast['ds'].dt.date
            baseline_forecast['yhat'] = baseline_forecast['yhat'].clip(lower=0)
            baseline_forecast['yhat_lower'] = baseline_forecast['yhat_lower'].clip(lower=0)
            baseline_forecast['yhat_upper'] = baseline_forecast['yhat_upper'].clip(lower=0)

            # --- Level calibration: shift Prophet output to match recent realized mean ---
            # Prophet converges to the training series mean; when the series mean is
            # suppressed by ffill gaps the forecast undershoots. Correct by rescaling
            # so the average predicted level matches the recent non-zero event mean.
            if recent_mean is not None and recent_mean > 0:
                prophet_mean = float(baseline_forecast['yhat'].mean())
                if prophet_mean > 0:
                    scale = recent_mean / prophet_mean
                    # Clamp scale to [0.5, 3.0] to avoid wild extrapolation
                    scale = max(0.5, min(3.0, scale))
                    baseline_forecast['yhat'] = (baseline_forecast['yhat'] * scale).clip(lower=0)
                    baseline_forecast['yhat_lower'] = (baseline_forecast['yhat_lower'] * scale).clip(lower=0)
                    baseline_forecast['yhat_upper'] = (baseline_forecast['yhat_upper'] * scale).clip(lower=0)

        except Exception as e:
            logger.warning(f"Prophet baseline fit failed for {node_name}: {e}")

    # Fallback to recent mean if Prophet cannot be fitted or fails
    if baseline_forecast is None or baseline_forecast.empty:
        non_zero_filtered = df[df['y_filtered'] > 0]['y_filtered']
        fallback_val = float(recent_mean) if recent_mean else (float(non_zero_filtered.median()) if not non_zero_filtered.empty else 10.0)
        if fallback_val <= 0:
            fallback_val = 10.0
        std_val = float(non_zero_filtered.std()) if len(non_zero_filtered) > 1 else fallback_val * 0.3
        future_dates = [target_date + timedelta(days=i) for i in range(1, forecast_days + 1)]
        baseline_forecast = pd.DataFrame({
            'ds': future_dates,
            'yhat': [fallback_val] * forecast_days,
            'yhat_lower': [max(0.0, fallback_val - std_val)] * forecast_days,
            'yhat_upper': [fallback_val + std_val] * forecast_days
        })

    # --- Step 4: Gated News Boost ---
    if not events:
        events = load_temporal_enriched_events()
        
    predictive_events = []
    for e in events:
        matched = e.get('matched_node')
        is_match = False
        if isinstance(matched, list):
            if node_name in matched:
                is_match = True
        elif matched == node_name:
            is_match = True
            
        if is_match:
            temporal_info = e.get('temporal_info') or {}
            # GATED LOGIC: Only strictly future events (>=2 days lead) with high confidence
            days_until = temporal_info.get('days_until_event')
            confidence = temporal_info.get('predicted_date_confidence', 'none')
            
            if (temporal_info.get('is_predictive') and 
                temporal_info.get('predicted_date') and
                days_until is not None and days_until >= 2 and
                confidence == 'high'):
                predictive_events.append(e)
                
    news_by_date = defaultdict(float)
    sigma = 0.5  # Tighter sigma so it doesn't bleed everywhere
    future_dates = [target_date + timedelta(days=i) for i in range(1, forecast_days + 1)]
    
    for fd in future_dates:
        total_news_risk = 0.0
        for e in predictive_events:
            temporal_info = e['temporal_info']
            pred_date_str = temporal_info['predicted_date']
            try:
                pred_date = datetime.fromisoformat(pred_date_str).date()
            except:
                continue
                
            weighted_risk = e.get('risk_score', 0) * 1.0 # High confidence weight
            
            # Reproject using original lead-time
            days_until = temporal_info.get('days_until_event')
            projected_date = target_date + timedelta(days=days_until)
                
            delta_days = (fd - projected_date).days
            if abs(delta_days) <= 2:  # 2-day truncation limit for bell-curve
                bell_factor = np.exp(-(delta_days ** 2) / (2 * (sigma ** 2)))
                total_news_risk += weighted_risk * bell_factor
                
        # Cap the maximum news uplift to prevent runaway scaling (e.g. max 50 points of boost)
        news_by_date[fd] = min(total_news_risk, 50.0)

    # --- Step 5: Fusion ---
    forecast_points = []
    for i in range(1, forecast_days + 1):
        fd = target_date + timedelta(days=i)
        
        baseline_row = baseline_forecast[baseline_forecast['ds'] == fd]
        baseline_risk = float(baseline_row.iloc[0]['yhat']) if not baseline_row.empty else 10.0
        yhat_lower = float(baseline_row.iloc[0]['yhat_lower']) if not baseline_row.empty else baseline_risk * 0.8
        yhat_upper = float(baseline_row.iloc[0]['yhat_upper']) if not baseline_row.empty else baseline_risk * 1.2
        
        news_risk = news_by_date[fd]
        yhat = baseline_risk + news_risk
        
        # News expands the upper bound only
        yhat_upper = yhat_upper + (news_risk * 1.5)
        
        # Ensure values stay roughly within 0-100 scale logically
        yhat = min(100.0, yhat)
        yhat_lower = min(100.0, max(0.0, yhat_lower))
        yhat_upper = min(100.0, yhat_upper)
        
        forecast_points.append({
            'ds': fd,
            'yhat': round(yhat, 2),
            'yhat_lower': round(yhat_lower, 2),
            'yhat_upper': round(yhat_upper, 2),
            'news_contribution': round(news_risk, 2),
            'historical_contribution': round(baseline_risk, 2),
            'method': 'edsf'
        })
        
    return pd.DataFrame(forecast_points)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    
    events = load_temporal_enriched_events()
    if args.train:
        train_news_enriched_model(events)
    else:
        # Original main logic (optional)
        pass

