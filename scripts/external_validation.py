"""External validation (T9 IMPROVEMENT_PLAN.md Phase 3.1): does the shipping_chokepoints
predictor's smoothed P lead real-world Brent crude volatility? Retrospective, offline-only —
no live pipeline integration, this does not touch the ingest path or the model. Downloads
Brent crude daily prices from FRED (public CSV, no API key needed), computes a lagged
cross-correlation against the sector's daily calibrated P, and writes an honest result
(whatever its sign) to data/external_validation.json.

Rationale for the sector/index pairing: shipping_chokepoints tracks Strait of Hormuz / Red
Sea disruption risk, which is the most directly oil-price-relevant of the five sectors. Brent
crude is freely available with full daily history via FRED, unlike container freight indices
(Freightos Baltic, Drewry WCI) which are subscription-gated for historical data.

Usage:
  venv311/bin/python -m scripts.external_validation
"""

from __future__ import annotations

import json
import os
import pickle
import sys

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv

load_dotenv(".env")

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from src.db_config import get_read_db_url
from scripts.train_predictor import (
    TARGETS, TARGET_KEYWORDS, LOOKBACK_START,
    daily_news, clean_event_days, build_target_frame,
)

MODEL = "model_training/predictor.pkl"
OUT = "data/external_validation.json"
TARGET_KEY = "shipping_chokepoints"
FRED_SERIES = "DCOILBRENTEU"
MAX_LAG = 14


def fetch_brent(start: str, end: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={FRED_SERIES}&cosd={start}&coed={end}"
    df = pd.read_csv(url, parse_dates=["observation_date"])
    df = df.rename(columns={FRED_SERIES: "brent"}).set_index("observation_date")
    df["brent"] = pd.to_numeric(df["brent"], errors="coerce")
    return df["brent"].dropna()


def smoothed_p_series(model, cal, cal_kind, feats, frame: pd.DataFrame) -> pd.Series:
    raw_ps = []
    for _, r in frame.iterrows():
        raw_i = model.predict_proba(r[feats].values.reshape(1, -1))[:, 1]
        p_i = float(np.clip(cal.predict(raw_i) if cal_kind == "isotonic"
                            else cal.predict_proba(raw_i.reshape(-1, 1))[:, 1], 0, 1)[0])
        raw_ps.append(p_i)
    raw = pd.Series(raw_ps, index=frame.index)
    return raw.rolling(3, min_periods=1).mean()


def main():
    with open(MODEL, "rb") as f:
        bundle = pickle.load(f)
    model, cal, cal_kind, feats = bundle["model"], bundle["calibrator"], bundle["cal_kind"], bundle["features"]

    engine = create_engine(get_read_db_url())
    with engine.connect() as conn:
        db_max = pd.Timestamp(conn.execute(text("SELECT MAX(article_timestamp)::date FROM events")).scalar())
        g = conn.execute(text("""
            SELECT article_date d, COUNT(*) c FROM disruption_candidates
            WHERE is_risk_event AND strict_is_risk AND article_date IS NOT NULL GROUP BY 1
        """)).fetchall()
        global_clean = pd.Series({pd.Timestamp(d): c for d, c in g}, dtype="float64")

        news = daily_news(conn, TARGET_KEYWORDS[TARGET_KEY])
        clean = clean_event_days(conn, TARGETS[TARGET_KEY])

    full_idx = pd.date_range(LOOKBACK_START, db_max, freq="D")
    frame = build_target_frame(news, clean, global_clean, full_idx)
    p_series = smoothed_p_series(model, cal, cal_kind, feats, frame)

    brent = fetch_brent(LOOKBACK_START, str(db_max.date()))
    brent_vol = brent.pct_change().rolling(3).std()  # 3-day realized volatility

    joined = pd.DataFrame({"p": p_series, "brent_vol": brent_vol}).dropna()

    corr_by_lag = {}
    for lag in range(-MAX_LAG, MAX_LAG + 1):
        # Positive lag: does P(t) correlate with brent_vol(t+lag)? i.e. P leads by `lag` days.
        pair = pd.DataFrame({"p": joined["p"], "v": joined["brent_vol"].shift(-lag)}).dropna()
        corr_by_lag[lag] = float(pair["p"].corr(pair["v"])) if len(pair) >= 10 else None

    valid = {k: v for k, v in corr_by_lag.items() if v is not None}
    best_lag = max(valid, key=lambda k: abs(valid[k])) if valid else None
    best_corr = valid.get(best_lag) if best_lag is not None else None

    if best_corr is None:
        interpretation = "Not enough overlapping data to compute a meaningful correlation."
    elif abs(best_corr) < 0.1:
        interpretation = ("No meaningful correlation found between the model's shipping P and "
                           "Brent crude volatility at any tested lag — an honest null result.")
    elif best_lag > 0:
        interpretation = (f"Weak-to-moderate evidence that the model's shipping P leads Brent "
                           f"volatility by about {best_lag} day(s) (r={best_corr:.2f}).")
    elif best_lag < 0:
        interpretation = (f"The strongest relationship found has Brent volatility leading the "
                           f"model's shipping P by about {-best_lag} day(s) (r={best_corr:.2f}) — "
                           f"i.e. the news signal may be reacting to price moves rather than "
                           f"anticipating them.")
    else:
        interpretation = f"The two series move together same-day (r={best_corr:.2f}), no clear lead-lag structure."

    result = {
        "target": TARGET_KEY,
        "index": "Brent crude oil (FRED series DCOILBRENTEU), 3-day realized volatility of daily returns",
        "date_range": [str(joined.index.min().date()), str(joined.index.max().date())],
        "n_obs": len(joined),
        "correlation_by_lag": corr_by_lag,
        "best_lag_days": best_lag,
        "best_correlation": best_corr,
        "same_day_correlation": corr_by_lag.get(0),
        "interpretation": interpretation,
        "method": ("Pearson correlation between the sector's 3-day-smoothed calibrated P and "
                   "Brent's 3-day realized return volatility, swept across lags of -14 to +14 "
                   "days. Positive lag = P leads (moves before) volatility."),
    }

    os.makedirs("data", exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)

    print(f"n_obs={len(joined)}  best_lag={best_lag}  best_corr={best_corr}")
    print(interpretation)
    print(f"Saved -> {OUT}")


if __name__ == "__main__":
    main()
