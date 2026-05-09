import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db_config import get_read_db_url


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build regression training CSV for impact prediction from events + suppliers tables."
    )
    parser.add_argument(
        "--output-csv",
        default="model_training/training_impact_dataset.csv",
        help="Output CSV path for regression training",
    )
    parser.add_argument(
        "--min-date",
        default=None,
        help="Optional lower bound for article_timestamp (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--max-date",
        default=None,
        help="Optional upper bound for article_timestamp (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--max-text-len",
        type=int,
        default=2000,
        help="Max chars kept in event_text_segment",
    )
    return parser.parse_args()


def build_where_clause(args):
    filters = ["e.article_title IS NOT NULL", "e.event_text_segment IS NOT NULL"]
    params = {}

    if args.min_date:
        filters.append("e.article_timestamp >= :min_date")
        params["min_date"] = args.min_date
    if args.max_date:
        filters.append("e.article_timestamp < :max_date")
        params["max_date"] = args.max_date

    where_sql = " AND ".join(filters)
    return where_sql, params


def normalize_probability_map(prob_value):
    if isinstance(prob_value, dict):
        return prob_value
    return {}


def derive_split(df):
    if df.empty:
        df["split"] = []
        return df

    # Time-aware split to reduce leakage from future articles into training.
    df = df.sort_values("article_timestamp").reset_index(drop=True)
    n = len(df)
    train_end = int(n * 0.7)
    val_end = int(n * 0.85)

    splits = ["train"] * train_end + ["val"] * (val_end - train_end) + ["test"] * (n - val_end)
    df["split"] = splits
    return df


def main():
    args = parse_args()
    output_path = Path(args.output_csv)
    db_url = get_read_db_url()

    where_sql, params = build_where_clause(args)
    query = text(
        f"""
        SELECT
            e.id AS event_id,
            e.article_timestamp,
            e.article_source,
            e.article_title,
            e.event_text_segment,
            e.matched_node,
            COALESCE(s.criticality, 1) AS node_criticality,
            e.ml_risk_label,
            e.ml_risk_confidence,
            e.ml_risk_probabilities,
            e.risk_score,
            COALESCE(e.risk_score, 0.0) * COALESCE(s.criticality, 1) AS impact_score
        FROM events e
        LEFT JOIN suppliers s
          ON e.matched_node = s.node_name
        WHERE {where_sql}
        """
    )

    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params=params)
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Failed to query database: {exc}") from exc

    if df.empty:
        raise ValueError("No rows returned from DB for impact dataset.")

    df["article_timestamp"] = pd.to_datetime(df["article_timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["article_timestamp"]).copy()

    df["event_text_segment"] = (
        df["event_text_segment"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, args.max_text_len)
    )
    df["article_title"] = df["article_title"].astype(str).str.replace(r"\s+", " ", regex=True)

    probs = df["ml_risk_probabilities"].apply(normalize_probability_map)
    df["ml_prob_low"] = probs.apply(lambda p: float(p.get("LOW", 0.0)))
    df["ml_prob_medium"] = probs.apply(lambda p: float(p.get("MEDIUM", 0.0)))
    df["ml_prob_high"] = probs.apply(lambda p: float(p.get("HIGH", 0.0)))

    df["ml_risk_label"] = df["ml_risk_label"].fillna("UNKNOWN").astype(str).str.upper()
    df["ml_risk_confidence"] = pd.to_numeric(df["ml_risk_confidence"], errors="coerce").fillna(0.0)
    df["node_criticality"] = pd.to_numeric(df["node_criticality"], errors="coerce").fillna(1).astype(int)
    df["impact_score"] = pd.to_numeric(df["impact_score"], errors="coerce").fillna(0.0)

    df = derive_split(df)

    keep_cols = [
        "event_id",
        "article_timestamp",
        "article_source",
        "article_title",
        "event_text_segment",
        "matched_node",
        "node_criticality",
        "ml_risk_label",
        "ml_risk_confidence",
        "ml_prob_low",
        "ml_prob_medium",
        "ml_prob_high",
        "risk_score",
        "impact_score",
        "split",
    ]
    df = df[keep_cols]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    split_counts = df["split"].value_counts().to_dict()
    print(f"Saved dataset: {output_path}")
    print(f"Rows: {len(df)} | Splits: {split_counts}")
    print(
        "Impact stats: "
        f"min={df['impact_score'].min():.2f}, "
        f"mean={df['impact_score'].mean():.2f}, "
        f"p95={df['impact_score'].quantile(0.95):.2f}, "
        f"max={df['impact_score'].max():.2f}"
    )


if __name__ == "__main__":
    main()
