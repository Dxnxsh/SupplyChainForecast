"""
Two-Stage XGBoost Forecast Training Script
Stage 1: P(event) — XGBClassifier
Stage 2: E[risk | event] — XGBRegressor (positive samples only)
Freeze-window architecture: no recursive predictions.
"""

import os
import sys
import json
import logging

import numpy as np
import pandas as pd
import xgboost as xgb
from sqlalchemy import text
from datetime import timedelta

sys.path.append(os.getcwd())
from src.load_to_db import get_db_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "day_offset",
    "day_of_week",
    "is_weekend",
    "days_since_last_event",
    "news_signal",
    "event_count_3d",
    "event_count_7d",
    "event_freq_7d",
    "avg_risk_last_7d_events",
    "max_risk_last_7d",
    "event_any_last_7d",
    "event_count_14d",
    "article_count_14d_total",
    "article_spike_days_14d",
    "sentiment_14d_mean",
    "sentiment_14d_std",
    "sentiment_14d_min",
    "sentiment_delta_14d",
    "negative_ratio_14d",
    "sentiment_lag_7d",
    "sentiment_lag_14d",
    "event_geopolitical_count",
    "event_labor_count",
    "event_logistics_count",
    "event_weather_count",
    "unique_event_types",
    "global_event_count_3d",
    "node_event_rate",
    "risk_trend_7d",
    "event_freq_acceleration",
]


def fetch_event_data(engine):
    query = text("""
        SELECT
            matched_node_element AS node_name,
            article_timestamp::date AS ds,
            risk_score,
            sentiment_score,
            sentiment_label,
            potential_event_types
        FROM events,
             jsonb_array_elements_text(matched_node) AS matched_node_element
        WHERE article_timestamp IS NOT NULL
          AND risk_score IS NOT NULL
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    df["ds"] = pd.to_datetime(df["ds"])
    return df


def fetch_temporal_news_signal(engine):
    query = text("""
        SELECT
            matched_node_element AS node_name,
            (temporal_info->>'predicted_date')::date AS predicted_date,
            risk_score * COALESCE((temporal_info->>'confidence')::float, 0.5) AS weighted_risk
        FROM events,
             jsonb_array_elements_text(matched_node) AS matched_node_element
        WHERE temporal_info IS NOT NULL
          AND temporal_info->>'predicted_date' IS NOT NULL
          AND risk_score IS NOT NULL
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    if df.empty:
        return {}
    df["predicted_date"] = pd.to_datetime(df["predicted_date"])
    grouped = df.groupby(["node_name", "predicted_date"])["weighted_risk"].sum().reset_index()
    signal_map = {}
    for _, row in grouped.iterrows():
        signal_map[(row["node_name"], row["predicted_date"])] = float(row["weighted_risk"])
    return signal_map


def build_daily_aggregates(event_df):
    """Aggregate per (node, date): event count, avg risk, max risk, sentiment stats, event types."""
    daily = event_df.groupby(["node_name", "ds"]).agg(
        event_count=("risk_score", "count"),
        avg_risk=("risk_score", "mean"),
        max_risk=("risk_score", "max"),
        sentiment_mean=("sentiment_score", "mean"),
        sentiment_std=("sentiment_score", "std"),
        sentiment_min=("sentiment_score", "min"),
    ).reset_index()
    daily["sentiment_std"] = daily["sentiment_std"].fillna(0)
    daily["sentiment_min"] = daily["sentiment_min"].fillna(0)

    neg_counts = event_df[event_df["sentiment_label"] == "negative"].groupby(
        ["node_name", "ds"]
    ).size().reset_index(name="negative_count")
    daily = daily.merge(neg_counts, on=["node_name", "ds"], how="left")
    daily["negative_count"] = daily["negative_count"].fillna(0)

    def extract_types(group):
        types = set()
        for val in group["potential_event_types"]:
            if isinstance(val, list):
                types.update(val)
            elif isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        types.update(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass
        return types

    type_agg = event_df.groupby(["node_name", "ds"]).apply(extract_types, include_groups=False).reset_index(name="event_types_set")
    daily = daily.merge(type_agg, on=["node_name", "ds"], how="left")

    return daily


def compute_features_for_grid(daily_df, full_grid, news_signal_map, global_daily):
    """Compute all features for every (node, date) in the full grid. day_offset=0 for training base."""
    records = []
    nodes = full_grid["node_name"].unique()

    node_event_rates = {}
    for node in nodes:
        node_data = daily_df[daily_df["node_name"] == node]
        if len(node_data) > 0:
            date_range = (node_data["ds"].max() - node_data["ds"].min()).days + 1
            node_event_rates[node] = len(node_data) / max(date_range, 1)
        else:
            node_event_rates[node] = 0.0

    for node in nodes:
        node_daily = daily_df[daily_df["node_name"] == node].set_index("ds").sort_index()
        node_grid = full_grid[full_grid["node_name"] == node]["ds"].sort_values()

        for target_date in node_grid:
            feat = _compute_single(
                node, target_date, node_daily, news_signal_map,
                global_daily, node_event_rates[node], day_offset=0
            )
            feat["node_name"] = node
            feat["target_date"] = target_date
            records.append(feat)

    return pd.DataFrame(records)


def _compute_single(node, target_date, node_daily, news_signal_map, global_daily, node_event_rate, day_offset):
    """Compute features for a single (node, target_date) with given day_offset."""
    # The "observation date" — what we know at forecast time
    obs_date = target_date - pd.Timedelta(days=day_offset)

    feat = {}
    feat["day_offset"] = day_offset
    feat["day_of_week"] = target_date.weekday()
    feat["is_weekend"] = 1 if target_date.weekday() >= 5 else 0

    # Window boundaries (relative to obs_date)
    window_3d_start = obs_date - pd.Timedelta(days=3)
    window_7d_start = obs_date - pd.Timedelta(days=7)
    window_14d_start = obs_date - pd.Timedelta(days=14)

    # Slice historical data up to obs_date (exclusive of obs_date for strict backward-looking)
    hist = node_daily[node_daily.index < obs_date]
    hist_7d = hist[hist.index >= window_7d_start]
    hist_3d = hist[hist.index >= window_3d_start]
    hist_14d = hist[hist.index >= window_14d_start]

    # days_since_last_event: deterministic
    if len(hist) > 0:
        last_event_date = hist.index.max()
        base_days_since = (obs_date - last_event_date).days
    else:
        base_days_since = 30
    feat["days_since_last_event"] = base_days_since + day_offset

    # news_signal
    feat["news_signal"] = news_signal_map.get((node, target_date), 0.0)

    # Short-term frozen features (3d and 7d windows)
    feat["event_count_3d"] = int(hist_3d["event_count"].sum()) if len(hist_3d) > 0 else 0
    feat["event_count_7d"] = int(hist_7d["event_count"].sum()) if len(hist_7d) > 0 else 0

    days_in_7d_window = min(7, len(pd.date_range(start=window_7d_start, end=obs_date - pd.Timedelta(days=1), freq="D")))
    event_days_7d = len(hist_7d[hist_7d["event_count"] > 0])
    feat["event_freq_7d"] = event_days_7d / max(days_in_7d_window, 1)

    event_days_in_7d = hist_7d[hist_7d["event_count"] > 0]
    feat["avg_risk_last_7d_events"] = float(event_days_in_7d["avg_risk"].mean()) if len(event_days_in_7d) > 0 else 0.0
    feat["max_risk_last_7d"] = float(hist_7d["max_risk"].max()) if len(hist_7d) > 0 else 0.0
    feat["event_any_last_7d"] = 1 if event_days_7d > 0 else 0

    # Medium-term (14d)
    feat["event_count_14d"] = int(hist_14d["event_count"].sum()) if len(hist_14d) > 0 else 0
    feat["article_count_14d_total"] = int(hist_14d["event_count"].sum()) if len(hist_14d) > 0 else 0
    days_14d = min(14, len(pd.date_range(start=window_14d_start, end=obs_date - pd.Timedelta(days=1), freq="D")))
    avg_daily_articles = feat["article_count_14d_total"] / max(days_14d, 1)
    feat["article_spike_days_14d"] = int((hist_14d["event_count"] > avg_daily_articles).sum()) if len(hist_14d) > 0 else 0

    # Sentiment (14d)
    if len(hist_14d) > 0 and hist_14d["sentiment_mean"].notna().any():
        feat["sentiment_14d_mean"] = float(hist_14d["sentiment_mean"].mean())
        feat["sentiment_14d_std"] = float(hist_14d["sentiment_mean"].std()) if len(hist_14d) > 1 else 0.0
        feat["sentiment_14d_min"] = float(hist_14d["sentiment_min"].min())
        last_3 = hist_14d.tail(3)["sentiment_mean"].mean()
        first_3 = hist_14d.head(3)["sentiment_mean"].mean()
        feat["sentiment_delta_14d"] = float(last_3 - first_3) if not (pd.isna(last_3) or pd.isna(first_3)) else 0.0
        total_events_14d = max(int(hist_14d["event_count"].sum()), 1)
        total_neg_14d = int(hist_14d["negative_count"].sum()) if "negative_count" in hist_14d.columns else 0
        feat["negative_ratio_14d"] = total_neg_14d / total_events_14d
        mid_window = hist_14d[(hist_14d.index >= obs_date - pd.Timedelta(days=10)) & (hist_14d.index < obs_date - pd.Timedelta(days=7))]
        feat["sentiment_lag_7d"] = float(mid_window["sentiment_mean"].mean()) if len(mid_window) > 0 else feat["sentiment_14d_mean"]
        far_window = hist_14d[hist_14d.index < obs_date - pd.Timedelta(days=11)]
        feat["sentiment_lag_14d"] = float(far_window["sentiment_mean"].mean()) if len(far_window) > 0 else feat["sentiment_14d_mean"]
    else:
        feat["sentiment_14d_mean"] = 0.0
        feat["sentiment_14d_std"] = 0.0
        feat["sentiment_14d_min"] = 0.0
        feat["sentiment_delta_14d"] = 0.0
        feat["negative_ratio_14d"] = 0.0
        feat["sentiment_lag_7d"] = 0.0
        feat["sentiment_lag_14d"] = 0.0

    # Event types (14d)
    type_counts = {"Political_Regulatory": 0, "Labor_Issue": 0, "Logistics_Issue": 0, "Natural_Disaster": 0}
    unique_types = set()
    if len(hist_14d) > 0 and "event_types_set" in hist_14d.columns:
        for _, row in hist_14d.iterrows():
            if isinstance(row.get("event_types_set"), set):
                for t in row["event_types_set"]:
                    unique_types.add(t)
                    if t in type_counts:
                        type_counts[t] += 1

    feat["event_geopolitical_count"] = type_counts["Political_Regulatory"]
    feat["event_labor_count"] = type_counts["Labor_Issue"]
    feat["event_logistics_count"] = type_counts["Logistics_Issue"]
    feat["event_weather_count"] = type_counts["Natural_Disaster"]
    feat["unique_event_types"] = len(unique_types)

    # Cross-node
    global_3d_start = obs_date - pd.Timedelta(days=3)
    global_3d = global_daily[(global_daily["ds"] >= global_3d_start) & (global_daily["ds"] < obs_date)]
    feat["global_event_count_3d"] = int(global_3d["event_count"].sum()) if len(global_3d) > 0 else 0
    feat["node_event_rate"] = node_event_rate

    # Trends
    if len(hist_7d) >= 2:
        y_vals = hist_7d["avg_risk"].fillna(0).values
        x_vals = np.arange(len(y_vals))
        if len(x_vals) > 1:
            slope = np.polyfit(x_vals, y_vals, 1)[0]
            feat["risk_trend_7d"] = float(slope)
        else:
            feat["risk_trend_7d"] = 0.0
    else:
        feat["risk_trend_7d"] = 0.0

    # event_freq_acceleration: freq last 7d minus freq of days 8-14
    hist_8_14 = hist[(hist.index >= obs_date - pd.Timedelta(days=14)) & (hist.index < obs_date - pd.Timedelta(days=7))]
    freq_8_14 = len(hist_8_14[hist_8_14["event_count"] > 0]) / 7.0 if len(hist_8_14) > 0 else 0.0
    feat["event_freq_acceleration"] = feat["event_freq_7d"] - freq_8_14

    return feat


def augment_with_day_offsets(features_df, daily_df, news_signal_map, global_daily, node_event_rates):
    """Create augmented samples with day_offset in {3, 7, 14} to teach model about stale features."""
    augmented = []
    offsets = [3, 7, 14]

    for node in features_df["node_name"].unique():
        node_daily = daily_df[daily_df["node_name"] == node].set_index("ds").sort_index()
        node_feats = features_df[features_df["node_name"] == node]

        for offset in offsets:
            for _, row in node_feats.iterrows():
                target_date = row["target_date"]
                obs_date = target_date - pd.Timedelta(days=offset)
                if obs_date < node_daily.index.min() + pd.Timedelta(days=14):
                    continue

                feat = _compute_single(
                    node, target_date, node_daily, news_signal_map,
                    global_daily, node_event_rates[node], day_offset=offset
                )
                feat["node_name"] = node
                feat["target_date"] = target_date
                augmented.append(feat)

    return pd.DataFrame(augmented)


def train():
    engine = get_db_engine()
    if not engine:
        logger.error("Could not connect to database.")
        return

    logger.info("Fetching event data from DB...")
    event_df = fetch_event_data(engine)
    if event_df.empty:
        logger.error("No event data found.")
        return
    logger.info(f"  {len(event_df)} event rows, {event_df['node_name'].nunique()} nodes, "
                f"date range {event_df['ds'].min().date()} to {event_df['ds'].max().date()}")

    logger.info("Fetching news signal data...")
    news_signal_map = fetch_temporal_news_signal(engine)
    logger.info(f"  {len(news_signal_map)} (node, date) news signal entries")

    logger.info("Building daily aggregates...")
    daily_df = build_daily_aggregates(event_df)
    logger.info(f"  {len(daily_df)} (node, date) daily rows")

    # Global daily counts (across all nodes)
    global_daily = event_df.groupby("ds").agg(event_count=("risk_score", "count")).reset_index()

    logger.info("Building full (node, date) grid...")
    nodes = event_df["node_name"].unique()
    date_min = event_df["ds"].min()
    date_max = event_df["ds"].max()
    all_dates = pd.date_range(start=date_min, end=date_max, freq="D")
    full_grid = pd.DataFrame([(n, d) for n in nodes for d in all_dates], columns=["node_name", "ds"])

    # Only keep grid entries where we have at least 14 days of history
    full_grid = full_grid[full_grid["ds"] >= date_min + pd.Timedelta(days=14)]
    logger.info(f"  Grid size: {len(full_grid)} (node, date) pairs")

    logger.info("Computing features (day_offset=0)...")
    features_df = compute_features_for_grid(daily_df, full_grid, news_signal_map, global_daily)

    # Labels
    daily_indexed = daily_df.set_index(["node_name", "ds"])
    features_df["has_event"] = features_df.apply(
        lambda r: 1 if (r["node_name"], r["target_date"]) in daily_indexed.index else 0, axis=1
    )
    features_df["avg_risk"] = features_df.apply(
        lambda r: float(daily_indexed.loc[(r["node_name"], r["target_date"]), "avg_risk"])
        if (r["node_name"], r["target_date"]) in daily_indexed.index else 0.0, axis=1
    )

    logger.info(f"  Positive samples (event days): {features_df['has_event'].sum()}")
    logger.info(f"  Negative samples (no-event days): {(features_df['has_event'] == 0).sum()}")

    # Augment with day_offsets
    logger.info("Augmenting with day_offset variants {3, 7, 14}...")
    node_event_rates = {}
    for node in nodes:
        node_data = daily_df[daily_df["node_name"] == node]
        if len(node_data) > 0:
            date_range_days = (node_data["ds"].max() - node_data["ds"].min()).days + 1
            node_event_rates[node] = len(node_data) / max(date_range_days, 1)
        else:
            node_event_rates[node] = 0.0

    aug_df = augment_with_day_offsets(features_df, daily_df, news_signal_map, global_daily, node_event_rates)
    if not aug_df.empty:
        aug_df["has_event"] = aug_df.apply(
            lambda r: 1 if (r["node_name"], r["target_date"]) in daily_indexed.index else 0, axis=1
        )
        aug_df["avg_risk"] = aug_df.apply(
            lambda r: float(daily_indexed.loc[(r["node_name"], r["target_date"]), "avg_risk"])
            if (r["node_name"], r["target_date"]) in daily_indexed.index else 0.0, axis=1
        )
        logger.info(f"  Augmented samples: {len(aug_df)}")
        all_data = pd.concat([features_df, aug_df], ignore_index=True)
    else:
        all_data = features_df

    logger.info(f"Total training samples: {len(all_data)}")

    # Prepare X, y
    X = all_data[FEATURE_COLUMNS].fillna(0).astype(float)
    y_binary = all_data["has_event"].values
    y_risk = all_data["avg_risk"].values

    # Stage 1: Event probability
    pos_count = y_binary.sum()
    neg_count = len(y_binary) - pos_count
    spw = neg_count / max(pos_count, 1)
    logger.info(f"Training Stage 1 (classifier)... scale_pos_weight={spw:.2f}")

    clf = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        scale_pos_weight=spw,
        random_state=42,
        eval_metric="logloss",
    )
    clf.fit(X, y_binary)

    # Stage 2: Severity (positive samples only)
    pos_mask = y_binary == 1
    X_pos = X[pos_mask]
    y_pos = y_risk[pos_mask]
    logger.info(f"Training Stage 2 (Mean regressor) on {pos_mask.sum()} positive samples...")

    reg = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.1,
        random_state=42,
    )
    reg.fit(X_pos, y_pos)

    logger.info(f"Training Stage 2 (Q75 quantile regressor) on {pos_mask.sum()} positive samples...")
    reg_q75 = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.1,
        random_state=42,
        objective="reg:quantileerror",
        quantile_alpha=0.75,
    )
    reg_q75.fit(X_pos, y_pos)

    # Compute confidence intervals (per-node error quantiles) for Mean model
    logger.info("Computing confidence intervals for Mean model...")
    base_data = all_data[all_data["day_offset"] == 0].copy()
    X_base = base_data[FEATURE_COLUMNS].fillna(0).astype(float)
    p_event = clf.predict_proba(X_base)[:, 1]
    severity = reg.predict(X_base)
    predicted = p_event * severity
    actual = base_data["avg_risk"].values * base_data["has_event"].values
    errors = np.abs(predicted - actual)

    base_data_mean = base_data.copy()
    base_data_mean["abs_error"] = errors
    intervals = {}
    for node in nodes:
        node_errors = base_data_mean[base_data_mean["node_name"] == node]["abs_error"]
        if len(node_errors) > 0:
            intervals[node] = float(np.percentile(node_errors, 80))
        else:
            intervals[node] = float(np.percentile(errors, 80))
    intervals["__global__"] = float(np.percentile(errors, 80))

    # Compute confidence intervals (per-node error quantiles) for Q75 model
    logger.info("Computing confidence intervals for Q75 model...")
    severity_q75 = reg_q75.predict(X_base)
    predicted_q75 = p_event * severity_q75
    errors_q75 = np.abs(predicted_q75 - actual)

    base_data_q75 = base_data.copy()
    base_data_q75["abs_error"] = errors_q75
    intervals_q75 = {}
    for node in nodes:
        node_errors = base_data_q75[base_data_q75["node_name"] == node]["abs_error"]
        if len(node_errors) > 0:
            intervals_q75[node] = float(np.percentile(node_errors, 80))
        else:
            intervals_q75[node] = float(np.percentile(errors_q75, 80))
    intervals_q75["__global__"] = float(np.percentile(errors_q75, 80))

    # Save models
    os.makedirs("models", exist_ok=True)
    clf.save_model("models/forecast_event_prob.json")
    
    # Save Mean models
    reg.save_model("models/forecast_severity.json")
    reg.save_model("models/forecast_severity_mean.json")
    with open("models/forecast_intervals.json", "w") as f:
        json.dump(intervals, f, indent=2)
    with open("models/forecast_intervals_mean.json", "w") as f:
        json.dump(intervals, f, indent=2)
        
    # Save Q75 models
    reg_q75.save_model("models/forecast_severity_q75.json")
    with open("models/forecast_intervals_q75.json", "w") as f:
        json.dump(intervals_q75, f, indent=2)
        
    logger.info("Models saved successfully (both Mean and Q75 variants).")

    # Backtest report
    logger.info("\n=== BACKTEST REPORT ===")
    base_predicted = predicted
    base_actual = actual

    mae = np.mean(np.abs(base_predicted - base_actual))
    logger.info(f"MAE (all samples, day_offset=0): {mae:.2f}")

    # Direction accuracy: did predicted go up/down in same direction as actual (day-over-day)?
    direction_correct = 0
    direction_total = 0
    for node in nodes:
        node_base = base_data[base_data["node_name"] == node].sort_values("target_date")
        if len(node_base) < 2:
            continue
        node_pred = p_event[node_base.index] * severity[node_base.index]
        node_act = node_base["avg_risk"].values * node_base["has_event"].values
        for i in range(1, len(node_pred)):
            pred_dir = node_pred[i] - node_pred[i - 1]
            act_dir = node_act[i] - node_act[i - 1]
            if (pred_dir > 0 and act_dir > 0) or (pred_dir < 0 and act_dir < 0) or (pred_dir == 0 and act_dir == 0):
                direction_correct += 1
            direction_total += 1

    if direction_total > 0:
        direction_acc = direction_correct / direction_total
        logger.info(f"Direction accuracy: {direction_acc:.1%} ({direction_correct}/{direction_total})")
    else:
        logger.info("Direction accuracy: N/A (not enough sequential data)")

    # Feature importance
    logger.info("\nStage 1 (P(event)) top features:")
    imp1 = clf.feature_importances_
    top1 = sorted(zip(FEATURE_COLUMNS, imp1), key=lambda x: -x[1])[:10]
    for name, score in top1:
        logger.info(f"  {name}: {score:.4f}")

    logger.info("\nStage 2 (severity) top features:")
    imp2 = reg.feature_importances_
    top2 = sorted(zip(FEATURE_COLUMNS, imp2), key=lambda x: -x[1])[:10]
    for name, score in top2:
        logger.info(f"  {name}: {score:.4f}")

    logger.info("\nTraining complete.")


if __name__ == "__main__":
    train()
