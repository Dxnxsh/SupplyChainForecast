# src/forecast_snapshots.py
"""Daily Prophet forecast snapshots per supplier node (persisted + on-demand fill)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional, Sequence, Tuple

import pandas as pd
from prophet import Prophet
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

METHOD_PROPHET = "prophet"
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


def generate_prophet_horizon_14(session: Session, node_name: str, forecast_date: date) -> List[dict]:
    """
    Train Prophet on daily SUM(risk_score) through forecast_date (inclusive), predict horizon_days=14
    starting forecast_date + 1. Matches get_risk_forecast hyperparameters.
    """
    q = text(
        """
        SELECT article_timestamp::date AS ds, SUM(risk_score) AS y
        FROM events
        WHERE matched_node = :node_name
          AND article_timestamp IS NOT NULL
          AND risk_score IS NOT NULL
          AND article_timestamp::date <= :forecast_date
        GROUP BY ds
        ORDER BY ds;
        """
    )
    result = session.execute(
        q, {"node_name": node_name, "forecast_date": forecast_date}
    ).fetchall()
    if len(result) < 2:
        raise ValueError(
            f"Not enough historical data for '{node_name}' as of {forecast_date} "
            f"(need at least 2 days with risk_score)."
        )

    raw_df = pd.DataFrame(result, columns=["ds", "y"])
    raw_df["ds"] = pd.to_datetime(raw_df["ds"])
    raw_df["y"] = pd.to_numeric(raw_df["y"])

    start = raw_df["ds"].min()
    end = pd.Timestamp(forecast_date)
    full_range = pd.date_range(start=start, end=end, freq="D")
    df = pd.DataFrame({"ds": full_range, "y": 0.0})
    df = df.merge(raw_df.rename(columns={"y": "y_actual"}), on="ds", how="left")
    df["y"] = df["y_actual"].fillna(df["y"])
    df = df[["ds", "y"]]

    model = Prophet(
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,
        changepoint_prior_scale=0.05,
    )
    model.fit(df)

    future = model.make_future_dataframe(periods=14)
    forecast = model.predict(future)
    mask = forecast["ds"].dt.date > forecast_date
    pred = forecast.loc[mask, ["ds", "yhat", "yhat_lower", "yhat_upper"]].head(14).copy()
    if len(pred) < 14:
        raise ValueError(f"Prophet returned fewer than 14 future rows for '{node_name}'.")

    pred["yhat"] = pred["yhat"].clip(lower=0)
    pred["yhat_lower"] = pred["yhat_lower"].clip(lower=0)
    pred["yhat_upper"] = pred["yhat_upper"].clip(lower=0)
    pred["ds"] = pred["ds"].dt.date

    return pred.to_dict("records")


def persist_snapshot_rows(
    session: Session,
    node_name: str,
    forecast_date: date,
    rows: Sequence[dict],
    source: str,
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
                "method": METHOD_PROPHET,
                "source": source,
            },
        )


def snapshot_exists(session: Session, node_name: str, forecast_date: date) -> bool:
    n = session.execute(
        text(
            """
            SELECT COUNT(*)::int FROM forecast_snapshots
            WHERE node_name = :n AND forecast_date = :fd AND method = :m
            """
        ),
        {"n": node_name, "fd": forecast_date, "m": METHOD_PROPHET},
    ).scalar()
    return (n or 0) >= 14


def load_snapshot_rows(session: Session, node_name: str, forecast_date: date) -> List[dict]:
    rows = session.execute(
        text(
            """
            SELECT horizon_day AS ds, yhat, yhat_lower, yhat_upper, source
            FROM forecast_snapshots
            WHERE node_name = :n AND forecast_date = :fd AND method = :m
            ORDER BY horizon_day
            """
        ),
        {"n": node_name, "fd": forecast_date, "m": METHOD_PROPHET},
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


def list_snapshot_dates(session: Session, node_name: Optional[str] = None) -> List[date]:
    if node_name:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT forecast_date FROM forecast_snapshots
                WHERE node_name = :n AND method = :m
                ORDER BY forecast_date DESC
                """
            ),
            {"n": node_name, "m": METHOD_PROPHET},
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
            {"m": METHOD_PROPHET},
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
        SELECT article_timestamp::date AS ds, COALESCE(SUM(risk_score), 0)::double precision AS y
        FROM events
        WHERE matched_node = :node_name
          AND article_timestamp IS NOT NULL
          AND risk_score IS NOT NULL
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
    session: Session, node_name: str, forecast_date: date, source: str
) -> Tuple[List[dict], bool]:
    """
    Return snapshot rows and whether they were generated on this call (persist attempted).
    """
    if snapshot_exists(session, node_name, forecast_date):
        rows = load_snapshot_rows(session, node_name, forecast_date)
        return rows, False
    rows = generate_prophet_horizon_14(session, node_name, forecast_date)
    persist_snapshot_rows(session, node_name, forecast_date, rows, source=source)
    session.commit()
    rows = load_snapshot_rows(session, node_name, forecast_date)
    return rows, True


def snapshot_all_nodes_for_date(session: Session, forecast_date: date, source: str = SOURCE_SCHEDULED) -> dict:
    nodes = session.execute(text("SELECT node_name FROM suppliers ORDER BY node_name")).fetchall()
    ok, failed = 0, []
    for (node_name,) in nodes:
        try:
            if snapshot_exists(session, node_name, forecast_date):
                ok += 1
                continue
            rows = generate_prophet_horizon_14(session, node_name, forecast_date)
            persist_snapshot_rows(session, node_name, forecast_date, rows, source=source)
            ok += 1
        except Exception as e:
            logger.warning("Snapshot skip %s @ %s: %s", node_name, forecast_date, e)
            failed.append({"node_name": node_name, "error": str(e)})
    session.commit()
    return {"forecast_date": str(forecast_date), "saved": ok, "failed": failed}
