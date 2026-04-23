"""
Upstream Data Quality Analysis

Examines the input to forecasting to identify noise sources:
1. Temporal extraction confidence distribution
2. Event type distribution
3. Node matching accuracy (how many events per node?)
4. Risk score distribution
"""

import json
from collections import defaultdict, Counter
from datetime import datetime
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


def analyze_temporal_extraction_quality():
    """Analyze temporal extraction confidence and predictive event rates."""
    events = load_temporal_enriched_events()
    
    confidence_dist = Counter()
    is_predictive_counts = Counter()
    total_with_temporal_info = 0
    
    for event in events:
        temporal_info = event.get('temporal_info', {})
        if temporal_info:
            total_with_temporal_info += 1
            confidence = temporal_info.get('predicted_date_confidence', 'unknown')
            confidence_dist[confidence] += 1
            
            is_predictive = temporal_info.get('is_predictive', False)
            is_predictive_counts[is_predictive] += 1
    
    print("\n📅 Temporal Extraction Quality Analysis")
    print("=" * 70)
    print(f"Total events: {len(events)}")
    print(f"Events with temporal_info: {total_with_temporal_info} ({100*total_with_temporal_info/len(events):.1f}%)")
    print()
    print("Predicted Date Confidence Distribution:")
    for conf in ['high', 'medium', 'low']:
        count = confidence_dist.get(conf, 0)
        pct = 100 * count / total_with_temporal_info if total_with_temporal_info > 0 else 0
        print(f"  {conf:10}: {count:5} events ({pct:5.1f}%)")
    
    print()
    print("Predictive vs Descriptive Events:")
    for is_pred in [True, False]:
        count = is_predictive_counts.get(is_pred, 0)
        pct = 100 * count / total_with_temporal_info if total_with_temporal_info > 0 else 0
        label = "Predictive" if is_pred else "Descriptive"
        print(f"  {label:15}: {count:5} events ({pct:5.1f}%)")
    
    print("=" * 70)
    return confidence_dist, is_predictive_counts


def analyze_event_type_distribution():
    """Check event type diversity and risk score alignment."""
    events = load_temporal_enriched_events()
    
    event_type_risk = defaultdict(list)
    
    for event in events:
        risk = event.get('risk_score', 0)
        for event_type in event.get('potential_event_types', []):
            event_type_risk[event_type].append(risk)
    
    print("\n🏷️  Event Type Distribution & Risk Scores")
    print("=" * 70)
    print(f"{'Event Type':30} | {'Count':>6} | {'Avg Risk':>8} | {'Min-Max Risk':>15}")
    print("-" * 70)
    
    for event_type in sorted(event_type_risk.keys()):
        risks = event_type_risk[event_type]
        count = len(risks)
        avg_risk = sum(risks) / count if risks else 0
        min_risk = min(risks) if risks else 0
        max_risk = max(risks) if risks else 0
        
        print(f"{event_type:30} | {count:6} | {avg_risk:8.2f} | {min_risk:6.1f}-{max_risk:6.1f}")
    
    print("=" * 70)


def analyze_node_matching():
    """Check event distribution across supplier nodes."""
    events = load_temporal_enriched_events()
    
    node_counts = Counter()
    node_avg_risk = defaultdict(list)
    node_with_pred_date = defaultdict(int)
    
    for event in events:
        node = event.get('matched_node')
        if node:
            node_counts[node] += 1
            risk = event.get('risk_score', 0)
            node_avg_risk[node].append(risk)
            
            temporal_info = event.get('temporal_info', {})
            if temporal_info.get('is_predictive'):
                node_with_pred_date[node] += 1
    
    print("\n🎯 Node Matching & Event Distribution")
    print("=" * 70)
    print(f"{'Node':30} | {'Events':>6} | {'Avg Risk':>8} | {'Predictive':>12}")
    print("-" * 70)
    
    for node in sorted(node_counts.keys()):
        count = node_counts[node]
        risks = node_avg_risk[node]
        avg_risk = sum(risks) / count if risks else 0
        pred_count = node_with_pred_date.get(node, 0)
        pred_pct = 100 * pred_count / count if count > 0 else 0
        
        print(f"{node:30} | {count:6} | {avg_risk:8.2f} | {pred_count:5} ({pred_pct:5.1f}%)")
    
    print("=" * 70)
    print(f"Total matched events: {sum(node_counts.values())}")
    unmatched = len(events) - sum(node_counts.values())
    print(f"Unmatched events: {unmatched} ({100*unmatched/len(events):.1f}%)")


def analyze_risk_score_distribution():
    """Examine risk score quality and potential outliers."""
    events = load_temporal_enriched_events()
    
    risk_scores = [e.get('risk_score', 0) for e in events if e.get('risk_score', 0) > 0]
    
    if not risk_scores:
        print("No risk scores found!")
        return
    
    sorted_risks = sorted(risk_scores)
    
    print("\n⚖️  Risk Score Distribution")
    print("=" * 70)
    print(f"Total events: {len(events)}")
    print(f"Events with risk > 0: {len(risk_scores)} ({100*len(risk_scores)/len(events):.1f}%)")
    print()
    print(f"Risk score statistics:")
    print(f"  Min:     {min(risk_scores):.2f}")
    print(f"  P25:     {sorted_risks[len(sorted_risks)//4]:.2f}")
    print(f"  Median:  {sorted_risks[len(sorted_risks)//2]:.2f}")
    print(f"  P75:     {sorted_risks[3*len(sorted_risks)//4]:.2f}")
    print(f"  Max:     {max(risk_scores):.2f}")
    print(f"  Mean:    {sum(risk_scores)/len(risk_scores):.2f}")
    
    # Count distribution by risk band
    bands = [(0, 10), (10, 20), (20, 50), (50, 100), (100, float('inf'))]
    print()
    print(f"Risk Score Bands:")
    for low, high in bands:
        count = sum(1 for r in risk_scores if low <= r < high)
        pct = 100 * count / len(risk_scores)
        print(f"  {low:5.0f}-{high:5.0f}: {count:5} events ({pct:5.1f}%)")
    
    print("=" * 70)


if __name__ == '__main__':
    analyze_temporal_extraction_quality()
    analyze_event_type_distribution()
    analyze_node_matching()
    analyze_risk_score_distribution()
