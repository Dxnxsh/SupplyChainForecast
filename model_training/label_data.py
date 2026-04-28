import csv
import json
from pathlib import Path

HIGH_RISK = [
    "bankruptcy", "shutdown", "strike", "sanctions", "embargo",
    "recall", "flood", "earthquake", "typhoon", "fire", "explosion",
    "war", "invasion", "collapse", "shortage", "disruption", "halt",
    "blockade", "coup", "attack", "crisis"
]

MEDIUM_RISK = [
    "delay", "tariff", "dispute", "warning", "protest", "investigation",
    "slowdown", "concern", "risk", "threat", "tension", "inflation",
    "price increase", "shortage", "downgrade"
]


def classify(text):
    t = text.lower()
    if any(w in t for w in HIGH_RISK):
        return "HIGH"
    if any(w in t for w in MEDIUM_RISK):
        return "MEDIUM"
    return "LOW"


def load_records(project_root):
    """
    Load raw article records.
    Supports:
    1) data/raw/web_scrape/*.json (repo-native format: list per file)
    2) raw_data.json in project root or current folder (JSONL fallback)
    """
    records = []

    raw_dir = project_root / "data" / "raw" / "web_scrape"
    if raw_dir.exists():
        for json_file in sorted(raw_dir.glob("*.json")):
            try:
                with json_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    records.extend(data)
            except Exception:
                continue

    if records:
        return records

    fallback_candidates = [
        project_root / "raw_data.json",
        Path("raw_data.json"),
    ]
    for fallback in fallback_candidates:
        if not fallback.exists():
            continue
        with fallback.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        break

    return records


def main():
    project_root = Path(__file__).resolve().parent.parent
    records = load_records(project_root)

    labeled = []
    for r in records:
        label_str = r.get("label", "")
        label_parts = label_str.split(";")
        if len(label_parts) < 2:
            continue

        headline = label_parts[1].strip()
        text = r.get("text", "") or ""
        risk = classify(f"{headline} {text[:200]}")
        labeled.append({"headline": headline, "text": text, "risk": risk})

    output_path = Path(__file__).resolve().parent / "labeled_data.csv"
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["headline", "text", "risk"])
        writer.writeheader()
        writer.writerows(labeled)

    print(f"Labeled {len(labeled)} articles")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
