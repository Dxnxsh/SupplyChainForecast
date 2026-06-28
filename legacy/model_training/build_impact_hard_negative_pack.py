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

LIKELY_NON_DISRUPTION_REGEX = (
    r"(markets wrap|stocks? (rise|rally|fall|drop)|s&p|dow|nasdaq|"
    r"consumer sentiment|redistricting|elections?|supreme court|"
    r"earnings|etf|dividend|market(s)?|inflation|gdp|bond yields?)"
)

LIKELY_DISRUPTION_REGEX = (
    r"(strike|shutdown|outage|explosion|fire|earthquake|flood|hurricane|"
    r"blockade|sanction|embargo|missile|collision|port.*closed|supply disruption|"
    r"factory.*halt|transit.*halted|war|clash)"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a hard-negative/positive label pack for impact model retraining."
    )
    parser.add_argument(
        "--output-csv",
        default="model_training/impact_hard_negative_label_pack.csv",
        help="Output CSV path for manual labeling",
    )
    parser.add_argument(
        "--hard-negative-count",
        type=int,
        default=180,
        help="Rows sampled from likely false-high predictions",
    )
    parser.add_argument(
        "--positive-count",
        type=int,
        default=120,
        help="Rows sampled from likely true disruptions",
    )
    parser.add_argument(
        "--neutral-count",
        type=int,
        default=80,
        help="Rows sampled from low predicted impact controls",
    )
    return parser.parse_args()


def fetch_df(engine, query, params):
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params=params)


def add_label_columns(df, bucket_name):
    df = df.copy()
    df["sample_bucket"] = bucket_name
    df["manual_is_disruption"] = ""
    df["manual_impact_score"] = ""
    df["manual_notes"] = ""
    return df


def main():
    args = parse_args()
    db_url = get_read_db_url()
    output_path = Path(args.output_csv)

    engine = create_engine(db_url)

    hard_negative_query = """
        SELECT
            e.id AS event_id,
            e.article_timestamp,
            e.article_source,
            e.article_title,
            e.event_text_segment,
            e.article_url,
            e.matched_node,
            e.risk_score,
            e.predicted_impact_score,
            e.ml_risk_label,
            e.ml_risk_confidence
        FROM events e
        WHERE e.predicted_impact_score IS NOT NULL
          AND e.article_title IS NOT NULL
          AND e.predicted_impact_score >= 120
          AND e.article_title ~* :non_disruption_regex
        ORDER BY e.predicted_impact_score DESC
        LIMIT :limit;
    """

    positives_query = """
        SELECT
            e.id AS event_id,
            e.article_timestamp,
            e.article_source,
            e.article_title,
            e.event_text_segment,
            e.article_url,
            e.matched_node,
            e.risk_score,
            e.predicted_impact_score,
            e.ml_risk_label,
            e.ml_risk_confidence
        FROM events e
        WHERE e.predicted_impact_score IS NOT NULL
          AND e.article_title IS NOT NULL
          AND (
              e.article_title ~* :disruption_regex
              OR e.event_text_segment ~* :disruption_regex
          )
        ORDER BY e.predicted_impact_score DESC
        LIMIT :limit;
    """

    neutral_query = """
        SELECT
            e.id AS event_id,
            e.article_timestamp,
            e.article_source,
            e.article_title,
            e.event_text_segment,
            e.article_url,
            e.matched_node,
            e.risk_score,
            e.predicted_impact_score,
            e.ml_risk_label,
            e.ml_risk_confidence
        FROM events e
        WHERE e.predicted_impact_score IS NOT NULL
          AND e.article_title IS NOT NULL
          AND e.predicted_impact_score <= 20
        ORDER BY RANDOM()
        LIMIT :limit;
    """

    try:
        hard_neg = fetch_df(
            engine,
            hard_negative_query,
            {
                "non_disruption_regex": LIKELY_NON_DISRUPTION_REGEX,
                "limit": args.hard_negative_count,
            },
        )
        positives = fetch_df(
            engine,
            positives_query,
            {
                "disruption_regex": LIKELY_DISRUPTION_REGEX,
                "limit": args.positive_count,
            },
        )
        neutral = fetch_df(engine, neutral_query, {"limit": args.neutral_count})
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Failed to fetch label-pack rows: {exc}") from exc

    hard_neg = add_label_columns(hard_neg, "hard_negative")
    positives = add_label_columns(positives, "likely_positive")
    neutral = add_label_columns(neutral, "neutral_control")

    df = pd.concat([hard_neg, positives, neutral], ignore_index=True)
    df = df.drop_duplicates(subset=["event_id"]).reset_index(drop=True)
    df = df.sort_values(["sample_bucket", "predicted_impact_score"], ascending=[True, False])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    counts = df["sample_bucket"].value_counts().to_dict()
    print(f"Saved label pack: {output_path}")
    print(f"Rows: {len(df)} | Bucket counts: {counts}")
    print("Label columns added: manual_is_disruption, manual_impact_score, manual_notes")


if __name__ == "__main__":
    main()
