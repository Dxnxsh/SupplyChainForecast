
import os
import sys
from datetime import datetime, date

# Ensure we can import from src
sys.path.append(os.getcwd())

from src.predictive_forecasting import load_temporal_enriched_events, create_future_risk_projections, get_news_risk_for_date

def verify():
    events = load_temporal_enriched_events()
    print(f"Loaded {len(events)} events")
    
    # Generate projections
    projections = create_future_risk_projections(events, forecast_days=365)
    
    # Check a date that has news risk
    any_date = next(iter(projections.keys()))
    any_node = next(iter(projections[any_date].keys()))
    
    risk = get_news_risk_for_date(projections, any_node, any_date)
    print(f"Date: {any_date}, Node: {any_node}, Risk: {risk}")
    
    assert risk > 0, "Risk should be greater than 0 for a known projection date"
    print("✅ News feature extraction verified!")

if __name__ == "__main__":
    verify()
