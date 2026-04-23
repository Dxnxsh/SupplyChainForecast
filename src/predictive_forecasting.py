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
        temporal_info = event.get('temporal_info', {})
        
        # Only process events with predicted future dates
        if not temporal_info.get('is_predictive') or not temporal_info.get('predicted_date'):
            continue
        
        predicted_date_str = temporal_info['predicted_date']
        confidence = temporal_info.get('predicted_date_confidence', 'none')
        risk_score = event.get('risk_score', 0)
        node_name = event.get('matched_node')
        
        if not node_name or risk_score == 0:
            continue
        
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
                future_risk_by_date_node[projection_date][node_name] += projected_risk
    
    logger.info(f"Generated projections for {len(future_risk_by_date_node)} dates")
    return future_risk_by_date_node


def get_historical_prophet_forecast(events, node_name, forecast_days=14):
    """
    Generates a Prophet-based forecast using historical data.
    Returns a DataFrame with dates and forecasted values.
    """
    # Filter events for this node
    node_events = [e for e in events if e.get('matched_node') == node_name]
    
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
        node_events = [e for e in events if e.get('matched_node') == node_name]
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


def generate_all_node_forecasts(events, forecast_days=14, output_dir="data/forecasts"):
    """
    Generates hybrid forecasts for all nodes with sufficient data.
    Saves individual JSON files for each node.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Get unique nodes
    nodes = set(e.get('matched_node') for e in events if e.get('matched_node'))
    logger.info(f"Generating forecasts for {len(nodes)} nodes...")
    
    forecasts = {}
    
    for node in nodes:
        try:
            forecast_df = create_hybrid_forecast(events, node, forecast_days)
            
            if forecast_df is not None and not forecast_df.empty:
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


if __name__ == "__main__":
    # Load temporal enriched events
    events = load_temporal_enriched_events()
    
    if not events:
        print("❌ No temporal enriched events found. Run temporal_extraction.py first.")
        exit(1)
    
    print(f"\n📊 Loaded {len(events)} events")
    
    # Generate forecasts for all nodes
    forecasts = generate_all_node_forecasts(events, forecast_days=14)
    
    print(f"\n✅ Generated forecasts for {len(forecasts)} nodes")
    
    # Show example analysis for first node
    if forecasts:
        example_node = list(forecasts.keys())[0]
        example_forecast = pd.DataFrame(forecasts[example_node])
        
        print(f"\n📈 Example Forecast Analysis for '{example_node}':")
        analysis = analyze_forecast_drivers(example_forecast)
        for key, value in analysis.items():
            print(f"  {key}: {value}")
        
        print("\n📅 First 7 days of forecast:")
        for _, row in example_forecast.head(7).iterrows():
            print(f"  {row['ds']}: Risk={row['yhat']:.1f} (News={row['news_contribution']:.1f}, Historical={row['historical_contribution']:.1f}) [{row['method']}]")

