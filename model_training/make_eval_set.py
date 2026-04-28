import argparse
import csv
import json
import random
from pathlib import Path


def load_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def build_input_text(row):
    headline = (row.get("article_title") or "").strip()
    text = (row.get("event_text_segment") or row.get("text") or "").strip()
    return headline, text, f"{headline} {text[:300]}".strip()


def main():
    parser = argparse.ArgumentParser(description="Create manual eval labeling set from pipeline events.")
    parser.add_argument("--source", default="data/processed/filtered_events.jsonl", help="JSONL source path")
    parser.add_argument("--size", type=int, default=300, help="Number of samples to export")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output", default="model_training/eval_set.csv", help="Output CSV path")
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    rows = load_jsonl(source_path)
    if not rows:
        raise ValueError(f"No valid JSON rows found in {source_path}")

    random.seed(args.seed)
    if len(rows) > args.size:
        rows = random.sample(rows, args.size)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "article_url",
                "headline",
                "text",
                "model_input",
                "manual_label",      # fill with LOW/MEDIUM/HIGH
                "notes",             # optional rationale
            ],
        )
        writer.writeheader()

        for i, row in enumerate(rows, start=1):
            headline, text, model_input = build_input_text(row)
            writer.writerow(
                {
                    "id": i,
                    "article_url": row.get("article_url", ""),
                    "headline": headline,
                    "text": text,
                    "model_input": model_input,
                    "manual_label": "",
                    "notes": "",
                }
            )

    print(f"Saved eval labeling set: {output_path} ({len(rows)} rows)")
    print("Next: manually fill manual_label with LOW/MEDIUM/HIGH.")


if __name__ == "__main__":
    main()
