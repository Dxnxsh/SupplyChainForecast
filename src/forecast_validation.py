"""
Forecast Validation & Backtesting Harness

Measures forecast quality by:
1. Comparing forecasted risk to actual observed risk in a future test window
2. Computing MAE, RMSE, and ranking stability metrics
3. Tracking improvement over multiple runs
"""

import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def load_temporal_enriched_events():
    """Load preprocessed events with temporal information."""
    events = []
    with open('data/processed/temporal_enriched_events.jsonl', 'r') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events


def compute_actual_risk_by_date_and_node(events):
    """
    Compute actual observed risk by aggregating events by date and node.
    Returns dict: {date -> {node -> total_risk_score}}
    """
    risk_by_date_node = defaultdict(lambda: defaultdict(float))
    
    for event in events:
        # Use article_timestamp as the "actual" observation time
        timestamp = event.get('article_timestamp')
        node = event.get('matched_node')
        risk = event.get('risk_score', 0)
        
        if timestamp and node and risk > 0:
            try:
                date = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date()
                risk_by_date_node[date][node] += risk
            except:
                continue
    
    return risk_by_date_node


def load_forecast(node_name):
    """Load a generated forecast JSON file."""
    filepath = f'data/forecasts/{node_name}_forecast.json'
    if not os.path.exists(filepath):
        return None
    
    with open(filepath, 'r') as f:
        return json.load(f)


def compute_mae(forecast_df, actual_values):
    """
    Mean Absolute Error between forecast and actual values.
    forecast_df: list of dicts with 'ds' and 'yhat' keys
    actual_values: dict {date -> actual_risk}
    """
    errors = []
    for row in forecast_df:
        ds = datetime.fromisoformat(row['ds']).date()
        predicted = row['yhat']
        actual = actual_values.get(ds, 0.0)
        errors.append(abs(predicted - actual))
    
    return sum(errors) / len(errors) if errors else float('inf')


def compute_rmse(forecast_df, actual_values):
    """Root Mean Square Error."""
    errors = []
    for row in forecast_df:
        ds = datetime.fromisoformat(row['ds']).date()
        predicted = row['yhat']
        actual = actual_values.get(ds, 0.0)
        errors.append((predicted - actual) ** 2)
    
    return (sum(errors) / len(errors)) ** 0.5 if errors else float('inf')


def compute_coverage(forecast_df):
    """Percentage of forecast dates with non-zero predicted risk."""
    non_zero = sum(1 for row in forecast_df if row['yhat'] > 0)
    return (non_zero / len(forecast_df) * 100) if forecast_df else 0.0


def compute_ranking_stability(forecast_df):
    """
    Measure how stable the forecast rankings are across dates.
    High stability = consistent ranking of high-risk vs low-risk dates.
    Low stability = volatile day-to-day changes.
    
    Computed as: 1 - (mean day-to-day change in ranking / max possible change)
    """
    if len(forecast_df) < 2:
        return 1.0
    
    yhats = [row['yhat'] for row in forecast_df]
    diffs = [abs(yhats[i] - yhats[i-1]) for i in range(1, len(yhats))]
    mean_diff = sum(diffs) / len(diffs)
    
    max_yhat = max(yhats) if yhats else 1.0
    min_yhat = min(yhats) if yhats else 0.0
    max_possible_change = max_yhat - min_yhat
    
    if max_possible_change == 0:
        return 1.0
    
    stability = 1.0 - (mean_diff / max_possible_change)
    return max(0.0, min(1.0, stability))  # Clip to [0, 1]


def validate_forecasts(nodes=None, output_dir="data/validation"):
    """
    Validate all forecasts and save results to a validation report.
    """
    if nodes is None:
        nodes = ['CATL_Ningde', 'Port_of_Long_Beach', 'TSMC_Hsinchu', 
                 'Foxconn_Zhengzhou', 'Tesla_Berlin', 'Albemarle_Chile']
    
    # Load actual observed risk
    events = load_temporal_enriched_events()
    actual_risk = compute_actual_risk_by_date_and_node(events)
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Validate each node
    validation_results = {
        'timestamp': datetime.now().isoformat(),
        'nodes': {}
    }
    
    print("\n📊 Forecast Validation Report")
    print("=" * 80)
    print(f"{'Node':25} | {'MAE':>8} | {'RMSE':>8} | {'Coverage':>8} | {'Stability':>9}")
    print("-" * 80)
    
    for node in nodes:
        forecast_data = load_forecast(node)
        if not forecast_data:
            print(f"{node:25} | NO FORECAST")
            continue
        
        # Get actual risk for this node across all dates in history
        node_actual_risk = {}
        for date_dict in actual_risk.values():
            if node in date_dict:
                # Find the date key
                for d, node_dict in actual_risk.items():
                    if node in node_dict and node_dict[node] > 0:
                        # Use dates from forecast for consistency
                        pass
        
        # Simpler approach: use the dates from the forecast
        node_actual_values = {}
        for row in forecast_data:
            ds = datetime.fromisoformat(row['ds']).date()
            node_actual_values[ds] = actual_risk.get(ds, {}).get(node, 0.0)
        
        # Compute metrics
        mae = compute_mae(forecast_data, node_actual_values)
        rmse = compute_rmse(forecast_data, node_actual_values)
        coverage = compute_coverage(forecast_data)
        stability = compute_ranking_stability(forecast_data)
        
        validation_results['nodes'][node] = {
            'mae': round(mae, 2),
            'rmse': round(rmse, 2),
            'coverage': round(coverage, 1),
            'ranking_stability': round(stability, 3),
            'num_events': len([e for e in events if e.get('matched_node') == node]),
            'forecast_days': len(forecast_data)
        }
        
        print(f"{node:25} | {mae:8.2f} | {rmse:8.2f} | {coverage:7.1f}% | {stability:9.3f}")
    
    print("=" * 80)
    
    # Save validation report
    report_path = f"{output_dir}/validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, 'w') as f:
        json.dump(validation_results, f, indent=2)
    
    print(f"\n✅ Validation report saved to {report_path}")
    return validation_results


def compare_component_contribution(nodes=None):
    """
    Analyze how much each forecast component (news vs historical) contributes.
    Returns summary of weights in effect.
    """
    if nodes is None:
        nodes = ['CATL_Ningde', 'Port_of_Long_Beach', 'TSMC_Hsinchu', 
                 'Foxconn_Zhengzhou', 'Tesla_Berlin', 'Albemarle_Chile']
    
    print("\n📈 Forecast Component Contribution Analysis")
    print("=" * 80)
    print(f"{'Node':25} | {'News %':>8} | {'Historical %':>13} | {'Avg Forecast':>13}")
    print("-" * 80)
    
    for node in nodes:
        forecast_data = load_forecast(node)
        if not forecast_data:
            continue
        
        news_vals = [row['news_contribution'] for row in forecast_data]
        hist_vals = [row['historical_contribution'] for row in forecast_data]
        yhat_vals = [row['yhat'] for row in forecast_data]
        
        total_news = sum(news_vals)
        total_hist = sum(hist_vals)
        total = total_news + total_hist
        
        news_pct = (total_news / total * 100) if total > 0 else 0
        hist_pct = (total_hist / total * 100) if total > 0 else 0
        avg_forecast = sum(yhat_vals) / len(yhat_vals) if yhat_vals else 0
        
        print(f"{node:25} | {news_pct:7.1f}% | {hist_pct:12.1f}% | {avg_forecast:13.2f}")
    
    print("=" * 80)


if __name__ == '__main__':
    # Run full validation
    results = validate_forecasts()
    
    # Show component contributions
    compare_component_contribution()
