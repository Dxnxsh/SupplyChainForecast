#!/usr/bin/env python3
"""Build a manual evaluation set for risk scoring calibration."""

import argparse
import csv
import json
import random
from pathlib import Path


RISK_BANDS = [
    ("IRRELEVANT", lambda score: score == 0),
    ("LOW", lambda score: 0 < score < 5),
    ("MEDIUM", lambda score: 5 <= score < 10),
    ("HIGH", lambda score: score >= 10),
]


def load_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def band_name(score):
    for label, predicate in RISK_BANDS:
        if predicate(score):
            return label
    return "UNKNOWN"


def build_sample(rows, size_per_band, seed):
    random.seed(seed)
    buckets = {label: [] for label, _ in RISK_BANDS}
    for row in rows:
        score = float(row.get("risk_score") or 0)
        label = band_name(score)
        if label in buckets:
            buckets[label].append(row)

    sample = []
    for label in ["IRRELEVANT", "LOW", "MEDIUM", "HIGH"]:
        candidates = buckets.get(label, [])
        if not candidates:
            continue
        take = min(size_per_band, len(candidates))
        sample.extend(random.sample(candidates, take))

    random.shuffle(sample)
    return sample


def main():
    parser = argparse.ArgumentParser(description="Create a manual risk scoring evaluation set.")
    parser.add_argument("--source", default="data/processed/scored_events.jsonl", help="Scored JSONL source")
    parser.add_argument("--output", default="model_training/risk_scoring_eval_set.csv", help="Output CSV path")
    parser.add_argument("--size-per-band", type=int, default=50, help="Samples per risk band")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    rows = load_jsonl(source_path)
    if not rows:
        raise ValueError(f"No valid JSON rows found in {source_path}")

    sample = build_sample(rows, args.size_per_band, args.seed)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "article_url",
                "article_source",
                "article_title",
                "event_text_segment",
                "potential_event_types",
                "risk_score",
                "risk_relevance_score",
                "risk_severity_score",
                "sample_band",
                "manual_label",
                "notes",
            ],
        )
        writer.writeheader()

        for idx, row in enumerate(sample, start=1):
            writer.writerow(
                {
                    "id": idx,
                    "article_url": row.get("article_url", ""),
                    "article_source": row.get("article_source", ""),
                    "article_title": row.get("article_title", ""),
                    "event_text_segment": row.get("event_text_segment", ""),
                    "potential_event_types": json.dumps(row.get("potential_event_types") or []),
                    "risk_score": row.get("risk_score", 0),
                    "risk_relevance_score": row.get("risk_relevance_score", 0),
                    "risk_severity_score": row.get("risk_severity_score", 0),
                    "sample_band": band_name(float(row.get("risk_score") or 0)),
                    "manual_label": "",
                    "notes": "",
                }
            )

    print(f"Saved risk scoring eval set: {output_path} ({len(sample)} rows)")
    print("Manual labels: DIRECT, INDIRECT, IRRELEVANT")


if __name__ == "__main__":
    main()