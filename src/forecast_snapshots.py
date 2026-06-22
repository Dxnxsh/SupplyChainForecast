# src/forecast_snapshots.py
"""Daily forecast snapshots per supplier node (persisted + on-demand fill)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional, Sequence, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

METHOD_PROPHET = "prophet"
METHOD_XGBOOST = "xgboost"
METHOD_XGBOOST_Q75 = "xgboost_q75"
METHOD_XGBOOST_MEAN = "xgboost_mean"
SOURCE_SCHEDULED = "scheduled"
SOURCE_ON_DEMAND = "on_demand"


def ensure_forecast_snapshots_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS forecast_snapshots (
                    node_name TEXT NOT NULL,
                    forecast_date DATE NOT NULL,
                    horizon_day DATE NOT NULL,
                    yhat DOUBLE PRECISION NOT NULL,
                    yhat_lower DOUBLE PRECISION NOT NULL,
                    yhat_upper DOUBLE PRECISION NOT NULL,
                    method TEXT NOT NULL DEFAULT 'prophet',
                    source TEXT NOT NULL DEFAULT 'scheduled',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (node_name, forecast_date, horizon_day, method)
                );
                """
            )
        )


def utc_today() -> date:
    return datetime.now(timezone.utc).date()




def generate_xgboost_horizon_14(session: Session, node_name: str, forecast_date: date, severity_variant: str = "q75") -> List[dict]:
    """
    Two-Stage XGBoost forecast (freeze-window architecture).
    Stage 1: P(event) via XGBClassifier
    Stage 2: E[risk | event] via XGBRegressor
    Final: yhat = P(event) * severity
    No recursive predictions — all features computed from actual data at forecast_date.

    severity_variant: "mean" (default, reg:squarederror) or "q75" (reg:quantileerror at 0.75)
    """
    import json
    import os
    import numpy as np
    import xgboost as xgb

    clf_path = "models/forecast_event_prob.json"
    if severity_variant == "q75":
        reg_path = "models/forecast_severity_q75.json"
        intervals_path = "models/forecast_intervals_q75.json"
    else:
        reg_path = "models/forecast_severity.json"
        intervals_path = "models/forecast_intervals.json"

    if not os.path.exists(clf_path) or not os.path.exists(reg_path):
        raise FileNotFoundError(
            f"Two-stage model files not found. Run scripts/train_two_stage_forecast.py first. "
            f"Missing: {[p for p in [clf_path, reg_path] if not os.path.exists(p)]}"
        )

    clf = xgb.XGBClassifier()
    clf.load_model(clf_path)
    reg = xgb.XGBRegressor()
    reg.load_model(reg_path)

    intervals = {}
    if os.path.exists(intervals_path):
        with open(intervals_path) as f:
            intervals = json.load(f)
    error_p80 = intervals.get(node_name, intervals.get("__global__", 15.0))

    # Fetch event history for this node up to forecast_date
    q_events = text("""
        SELECT
            article_timestamp::date AS ds,
            risk_score,
            sentiment_score,
            sentiment_label,
            potential_event_types
        FROM events
        WHERE matched_node @> jsonb_build_array(:node_name)
          AND article_timestamp IS NOT NULL
          AND risk_score IS NOT NULL
          AND article_timestamp::date <= :forecast_date
    """)
    rows = session.execute(q_events, {"node_name": node_name, "forecast_date": forecast_date}).fetchall()
    event_df = pd.DataFrame(rows, columns=["ds", "risk_score", "sentiment_score", "sentiment_label", "potential_event_types"])
    event_df["ds"] = pd.to_datetime(event_df["ds"])

    # Fetch news signal for horizon days
    q_news = text("""
        SELECT
            (temporal_info->>'predicted_date')::date AS predicted_date,
            risk_score * COALESCE((temporal_info->>'confidence')::float, 0.5) AS weighted_risk
        FROM events
        WHERE matched_node @> jsonb_build_array(:node_name)
          AND temporal_info IS NOT NULL
          AND temporal_info->>'predicted_date' IS NOT NULL
          AND risk_score IS NOT NULL
    """)
    news_rows = session.execute(q_news, {"node_name": node_name}).fetchall()
    news_df = pd.DataFrame(news_rows, columns=["predicted_date", "weighted_risk"])
    news_signal_map = {}
    if not news_df.empty:
        news_df["predicted_date"] = pd.to_datetime(news_df["predicted_date"])
        for dt, grp in news_df.groupby("predicted_date"):
            news_signal_map[dt] = float(grp["weighted_risk"].sum())

    # Global event count (all nodes)
    q_global = text("""
        SELECT article_timestamp::date AS ds, COUNT(*) AS event_count
        FROM events
        WHERE article_timestamp IS NOT NULL AND risk_score IS NOT NULL
          AND article_timestamp::date >= :start AND article_timestamp::date <= :end
        GROUP BY ds
    """)
    global_start = forecast_date - timedelta(days=3)
    global_rows = session.execute(q_global, {"start": global_start, "end": forecast_date}).fetchall()
    global_3d_count = sum(r[1] for r in global_rows)

    # Build daily aggregate for this node
    obs_date = pd.Timestamp(forecast_date)
    window_3d_start = obs_date - pd.Timedelta(days=3)
    window_7d_start = obs_date - pd.Timedelta(days=7)
    window_14d_start = obs_date - pd.Timedelta(days=14)

    hist = event_df[event_df["ds"] < obs_date]
    hist_3d = hist[hist["ds"] >= window_3d_start]
    hist_7d = hist[hist["ds"] >= window_7d_start]
    hist_14d = hist[hist["ds"] >= window_14d_start]

    # Compute frozen features
    frozen = {}

    # Short-term
    daily_7d = hist_7d.groupby("ds").agg(cnt=("risk_score", "count"), avg_r=("risk_score", "mean"), max_r=("risk_score", "max")).reset_index()
    daily_3d = hist_3d.groupby("ds").agg(cnt=("risk_score", "count")).reset_index()

    frozen["event_count_3d"] = int(daily_3d["cnt"].sum()) if len(daily_3d) > 0 else 0
    frozen["event_count_7d"] = int(daily_7d["cnt"].sum()) if len(daily_7d) > 0 else 0
    event_days_7d = len(daily_7d[daily_7d["cnt"] > 0])
    frozen["event_freq_7d"] = event_days_7d / 7.0
    frozen["avg_risk_last_7d_events"] = float(daily_7d[daily_7d["cnt"] > 0]["avg_r"].mean()) if event_days_7d > 0 else 0.0
    frozen["max_risk_last_7d"] = float(daily_7d["max_r"].max()) if len(daily_7d) > 0 else 0.0
    frozen["event_any_last_7d"] = 1 if event_days_7d > 0 else 0

    # Medium-term (14d)
    daily_14d = hist_14d.groupby("ds").agg(cnt=("risk_score", "count"), avg_r=("risk_score", "mean")).reset_index()
    frozen["event_count_14d"] = int(daily_14d["cnt"].sum()) if len(daily_14d) > 0 else 0
    frozen["article_count_14d_total"] = frozen["event_count_14d"]
    avg_daily = frozen["article_count_14d_total"] / 14.0
    frozen["article_spike_days_14d"] = int((daily_14d["cnt"] > avg_daily).sum()) if len(daily_14d) > 0 else 0

    # Sentiment (14d)
    sent_14d = hist_14d[hist_14d["sentiment_score"].notna()]
    if len(sent_14d) > 0:
        daily_sent = sent_14d.groupby("ds")["sentiment_score"].mean()
        frozen["sentiment_14d_mean"] = float(daily_sent.mean())
        frozen["sentiment_14d_std"] = float(daily_sent.std()) if len(daily_sent) > 1 else 0.0
        frozen["sentiment_14d_min"] = float(daily_sent.min())
        last3_dates = daily_sent.sort_index().tail(3)
        first3_dates = daily_sent.sort_index().head(3)
        frozen["sentiment_delta_14d"] = float(last3_dates.mean() - first3_dates.mean())
        neg_count = len(sent_14d[sent_14d["sentiment_label"] == "negative"])
        frozen["negative_ratio_14d"] = neg_count / max(len(sent_14d), 1)
        mid = daily_sent[(daily_sent.index >= obs_date - pd.Timedelta(days=10)) & (daily_sent.index < obs_date - pd.Timedelta(days=7))]
        frozen["sentiment_lag_7d"] = float(mid.mean()) if len(mid) > 0 else frozen["sentiment_14d_mean"]
        far = daily_sent[daily_sent.index < obs_date - pd.Timedelta(days=11)]
        frozen["sentiment_lag_14d"] = float(far.mean()) if len(far) > 0 else frozen["sentiment_14d_mean"]
    else:
        for k in ["sentiment_14d_mean", "sentiment_14d_std", "sentiment_14d_min",
                  "sentiment_delta_14d", "negative_ratio_14d", "sentiment_lag_7d", "sentiment_lag_14d"]:
            frozen[k] = 0.0

    # Event types (14d)
    type_counts = {"Political_Regulatory": 0, "Labor_Issue": 0, "Logistics_Issue": 0, "Natural_Disaster": 0}
    unique_types = set()
    for val in hist_14d["potential_event_types"]:
        types_list = []
        if isinstance(val, list):
            types_list = val
        elif isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    types_list = parsed
            except (json.JSONDecodeError, TypeError):
                pass
        for t in types_list:
            unique_types.add(t)
            if t in type_counts:
                type_counts[t] += 1
    frozen["event_geopolitical_count"] = type_counts["Political_Regulatory"]
    frozen["event_labor_count"] = type_counts["Labor_Issue"]
    frozen["event_logistics_count"] = type_counts["Logistics_Issue"]
    frozen["event_weather_count"] = type_counts["Natural_Disaster"]
    frozen["unique_event_types"] = len(unique_types)

    # Cross-node
    frozen["global_event_count_3d"] = global_3d_count
    total_days = max((event_df["ds"].max() - event_df["ds"].min()).days + 1, 1) if len(event_df) > 0 else 1
    event_days_total = event_df["ds"].nunique()
    frozen["node_event_rate"] = event_days_total / total_days

    # Trends
    if len(daily_7d) >= 2:
        y_vals = daily_7d["avg_r"].fillna(0).values
        x_vals = np.arange(len(y_vals))
        frozen["risk_trend_7d"] = float(np.polyfit(x_vals, y_vals, 1)[0])
    else:
        frozen["risk_trend_7d"] = 0.0

    daily_8_14 = hist_14d[hist_14d["ds"] < window_7d_start].groupby("ds").agg(cnt=("risk_score", "count")).reset_index()
    freq_8_14 = len(daily_8_14[daily_8_14["cnt"] > 0]) / 7.0 if len(daily_8_14) > 0 else 0.0
    frozen["event_freq_acceleration"] = frozen["event_freq_7d"] - freq_8_14

    # days_since_last_event base
    if len(hist) > 0:
        last_event_date = hist["ds"].max()
        base_days_since = (obs_date - last_event_date).days
    else:
        base_days_since = 30

    # Predict 14 horizon days
    from scripts.train_two_stage_forecast import FEATURE_COLUMNS

    forecast_points = []
    for i in range(1, 15):
        target = forecast_date + timedelta(days=i)
        target_ts = pd.Timestamp(target)

        features = dict(frozen)
        features["day_offset"] = i
        features["day_of_week"] = target_ts.weekday()
        features["is_weekend"] = 1 if target_ts.weekday() >= 5 else 0
        features["days_since_last_event"] = base_days_since + i
        features["news_signal"] = news_signal_map.get(target_ts, 0.0)

        X = pd.DataFrame([{col: features.get(col, 0.0) for col in FEATURE_COLUMNS}])
        p_event = float(clf.predict_proba(X)[:, 1][0])
        severity = max(0.0, float(reg.predict(X)[0]))
        yhat = p_event * severity

        yhat_lower = max(0.0, yhat - error_p80)
        yhat_upper = yhat + error_p80

        forecast_points.append({
            "ds": target,
            "yhat": round(yhat, 2),
            "yhat_lower": round(yhat_lower, 2),
            "yhat_upper": round(yhat_upper, 2),
        })

    return forecast_points


def persist_snapshot_rows(
    session: Session,
    node_name: str,
    forecast_date: date,
    rows: Sequence[dict],
    source: str,
    method: str = METHOD_PROPHET,
) -> None:
    stmt = text(
        """
        INSERT INTO forecast_snapshots (
            node_name, forecast_date, horizon_day, yhat, yhat_lower, yhat_upper, method, source, created_at
        ) VALUES (
            :node_name, :forecast_date, :horizon_day, :yhat, :yhat_lower, :yhat_upper, :method, :source, NOW()
        )
        ON CONFLICT (node_name, forecast_date, horizon_day, method) DO NOTHING
        """
    )
    for r in rows:
        session.execute(
            stmt,
            {
                "node_name": node_name,
                "forecast_date": forecast_date,
                "horizon_day": r["ds"],
                "yhat": float(r["yhat"]),
                "yhat_lower": float(r["yhat_lower"]),
                "yhat_upper": float(r["yhat_upper"]),
                "method": method,
                "source": source,
            },
        )


def snapshot_exists(session: Session, node_name: str, forecast_date: date, method: str = METHOD_PROPHET) -> bool:
    n = session.execute(
        text(
            """
            SELECT COUNT(*)::int FROM forecast_snapshots
            WHERE node_name = :n AND forecast_date = :fd AND method = :m
            """
        ),
        {"n": node_name, "fd": forecast_date, "m": method},
    ).scalar()
    return (n or 0) >= 14


def load_snapshot_rows(session: Session, node_name: str, forecast_date: date, method: str = METHOD_PROPHET) -> List[dict]:
    rows = session.execute(
        text(
            """
            SELECT horizon_day AS ds, yhat, yhat_lower, yhat_upper, source
            FROM forecast_snapshots
            WHERE node_name = :n AND forecast_date = :fd AND method = :m
            ORDER BY horizon_day
            """
        ),
        {"n": node_name, "fd": forecast_date, "m": method},
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r._mapping)
        out.append(
            {
                "ds": d["ds"],
                "yhat": float(d["yhat"]),
                "yhat_lower": float(d["yhat_lower"]),
                "yhat_upper": float(d["yhat_upper"]),
                "source": d.get("source"),
            }
        )
    return out


def list_snapshot_dates(session: Session, node_name: Optional[str] = None, method: str = METHOD_PROPHET) -> List[date]:
    if node_name:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT forecast_date FROM forecast_snapshots
                WHERE node_name = :n AND method = :m
                ORDER BY forecast_date DESC
                """
            ),
            {"n": node_name, "m": method},
        ).fetchall()
    else:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT forecast_date FROM forecast_snapshots
                WHERE method = :m
                ORDER BY forecast_date DESC
                """
            ),
            {"m": method},
        ).fetchall()
    return [r[0] for r in rows]


def fetch_actuals_for_horizon(
    session: Session, node_name: str, horizon_days: List[date]
) -> dict[date, Optional[float]]:
    if not horizon_days:
        return {}
    h_min = min(horizon_days)
    h_max = max(horizon_days)
    q = text(
        """
        SELECT article_timestamp::date AS ds,
               COALESCE(AVG(
                   LEAST(100.0, COALESCE(predicted_impact_score::double precision / 3.0, risk_score::double precision))
               ), 0)::double precision AS y
        FROM events
        WHERE matched_node @> jsonb_build_array(:node_name)
          AND article_timestamp IS NOT NULL
          AND (risk_score IS NOT NULL OR predicted_impact_score IS NOT NULL)
          AND article_timestamp::date >= :h_min
          AND article_timestamp::date <= :h_max
        GROUP BY ds
        """
    )
    rows = session.execute(
        q, {"node_name": node_name, "h_min": h_min, "h_max": h_max}
    ).fetchall()
    by_day = {dict(r._mapping)["ds"]: float(dict(r._mapping)["y"]) for r in rows}
    return {d: by_day.get(d, 0.0) for d in horizon_days}


def _row_ds_to_date(ds: Any) -> date:
    if isinstance(ds, date) and not isinstance(ds, datetime):
        return ds
    if isinstance(ds, datetime):
        return ds.date()
    if isinstance(ds, str):
        return date.fromisoformat(ds[:10])
    raise TypeError(f"Unsupported ds type: {type(ds)}")


def compute_accuracy_metrics(
    horizon: List[dict],
    today: date,
) -> Tuple[Optional[float], int, int]:
    """MAE over completed horizon days where y_actual is not None; also counts."""
    errs = []
    completed = 0
    for row in horizon:
        ds = _row_ds_to_date(row["ds"])
        y_a = row.get("y_actual")
        if y_a is None or ds > today:
            continue
        completed += 1
        errs.append(abs(float(row["yhat"]) - float(y_a)))
    if not errs:
        return None, completed, len(horizon)
    return sum(errs) / len(errs), completed, len(horizon)


def ensure_snapshot_for_node(
    session: Session, node_name: str, forecast_date: date, source: str, method: str = METHOD_XGBOOST
) -> Tuple[List[dict], bool]:
    """
    Return snapshot rows and whether they were generated on this call (persist attempted).
    """
    if snapshot_exists(session, node_name, forecast_date, method=method):
        rows = load_snapshot_rows(session, node_name, forecast_date, method=method)
        return rows, False
 
    if method == METHOD_XGBOOST_MEAN:
        rows = generate_xgboost_horizon_14(session, node_name, forecast_date, severity_variant="mean")
    else:
        rows = generate_xgboost_horizon_14(session, node_name, forecast_date, severity_variant="q75")

    persist_snapshot_rows(session, node_name, forecast_date, rows, source=source, method=method)
    session.commit()
    rows = load_snapshot_rows(session, node_name, forecast_date, method=method)
    return rows, True
 
 
def snapshot_all_nodes_for_date(
    session: Session, forecast_date: date, source: str = SOURCE_SCHEDULED, method: str = METHOD_XGBOOST
) -> dict:
    nodes = session.execute(text("SELECT node_name FROM suppliers ORDER BY node_name")).fetchall()
    ok, failed = 0, []
    for (node_name,) in nodes:
        try:
            if snapshot_exists(session, node_name, forecast_date, method=method):
                ok += 1
                continue
 
            if method == METHOD_XGBOOST_MEAN:
                rows = generate_xgboost_horizon_14(session, node_name, forecast_date, severity_variant="mean")
            else:
                rows = generate_xgboost_horizon_14(session, node_name, forecast_date, severity_variant="q75")
 
            persist_snapshot_rows(session, node_name, forecast_date, rows, source=source, method=method)
            ok += 1
        except Exception as e:
            logger.warning("Snapshot skip %s @ %s (%s): %s", node_name, forecast_date, method, e)
            failed.append({"node_name": node_name, "error": str(e)})
    session.commit()
    return {"forecast_date": str(forecast_date), "method": method, "saved": ok, "failed": failed}
