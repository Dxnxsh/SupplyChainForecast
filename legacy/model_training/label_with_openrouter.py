import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd


SYSTEM_PROMPT = """You are labeling supply-chain disruption data for model retraining.
Return ONLY strict JSON with keys:
- manual_is_disruption: integer 0 or 1
- manual_impact_score: integer 0..300
- manual_notes: short string <= 20 words

Rules:
1) manual_is_disruption=1 only for real/imminent operational supply-chain disruption.
2) manual_is_disruption=0 for macro/market/political/general stories without direct operational disruption.
3) If disruption=0, manual_impact_score should usually be 0..20.
4) If disruption=1, use:
   - 21..60 low
   - 61..120 moderate
   - 121..200 high
   - 201..300 severe
5) Ignore model outputs as truth. Use article semantics only.
"""


USER_PROMPT_TEMPLATE = """Label this single row.

Fields:
- article_title: {article_title}
- article_source: {article_source}
- event_text_segment: {event_text_segment}
- matched_node: {matched_node}
- sample_bucket: {sample_bucket}

Output strict JSON only.
"""


REQUIRED_COLUMNS = [
    "manual_is_disruption",
    "manual_impact_score",
    "manual_notes",
]


def has_value(value) -> bool:
    if pd.isna(value):
        return False
    return str(value).strip() != ""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Label CSV rows using OpenRouter chat completions."
    )
    parser.add_argument(
        "--input-csv",
        default="model_training/impact_label_pack_balanced.csv",
        help="CSV to label",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Output CSV path (defaults to in-place overwrite input)",
    )
    parser.add_argument(
        "--model",
        default="deepseek/deepseek-v4-flash",
        help="OpenRouter model slug",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=0,
        help="Max rows to process this run (0 = all pending rows)",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.6,
        help="Delay between successful requests",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="HTTP timeout per request",
    )
    parser.add_argument(
        "--overwrite-filled",
        action="store_true",
        help="Relabel rows that already have manual labels",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=10,
        help="Save CSV every N processed rows",
    )
    return parser.parse_args()


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    for col in REQUIRED_COLUMNS:
        df[col] = df[col].fillna("")
    return df


def is_labeled(row: pd.Series) -> bool:
    return has_value(row.get("manual_is_disruption", "")) and has_value(
        row.get("manual_impact_score", "")
    )


def build_user_prompt(row: pd.Series) -> str:
    title = str(row.get("article_title", "") or "").strip()
    source = str(row.get("article_source", "") or "").strip()
    text = str(row.get("event_text_segment", "") or "").strip()
    node = str(row.get("matched_node", "") or "").strip()
    bucket = str(row.get("sample_bucket", "") or "").strip()
    text = text[:1800]
    return USER_PROMPT_TEMPLATE.format(
        article_title=title,
        article_source=source,
        event_text_segment=text,
        matched_node=node,
        sample_bucket=bucket,
    )


def call_openrouter(api_key: str, model: str, user_prompt: str, timeout_seconds: int) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://local-labeling-pipeline",
            "X-Title": "SupplyChainForecast Label Pipeline",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        body = resp.read().decode("utf-8")
    parsed = json.loads(body)
    return parsed["choices"][0]["message"]["content"]


def parse_label_json(text_out: str) -> dict:
    parsed = json.loads(text_out)
    disruption = int(parsed["manual_is_disruption"])
    impact = int(parsed["manual_impact_score"])
    notes = str(parsed.get("manual_notes", "")).strip()

    if disruption not in (0, 1):
        raise ValueError(f"manual_is_disruption must be 0/1, got {disruption}")
    if impact < 0 or impact > 300:
        raise ValueError(f"manual_impact_score out of range 0..300: {impact}")
    if disruption == 0 and impact > 40:
        # Hard guard for obvious formatting/model slips.
        raise ValueError(f"non-disruption impact unexpectedly high: {impact}")
    if not notes:
        notes = "Auto-labeled via OpenRouter."

    return {
        "manual_is_disruption": disruption,
        "manual_impact_score": impact,
        "manual_notes": notes[:200],
    }


def save_df(df: pd.DataFrame, out_path: Path):
    df.to_csv(out_path, index=False)


def main():
    args = parse_args()
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")

    input_path = Path(args.input_csv)
    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    output_path = Path(args.output_csv) if args.output_csv else input_path

    df = pd.read_csv(input_path)
    df = ensure_columns(df)

    candidates = []
    for i, row in df.iterrows():
        if args.overwrite_filled or not is_labeled(row):
            candidates.append(i)

    if args.max_rows > 0:
        candidates = candidates[: args.max_rows]

    print(f"Rows total: {len(df)}")
    print(f"Rows to process: {len(candidates)}")
    print(f"Model: {args.model}")
    print(f"Output: {output_path}")

    if not candidates:
        print("Nothing to process.")
        save_df(df, output_path)
        return

    processed = 0
    failures = 0
    total = len(candidates)

    for seq, idx in enumerate(candidates, start=1):
        row = df.loc[idx]
        prompt = build_user_prompt(row)
        pct = (seq / total) * 100 if total else 100.0
        print(
            f"[{seq}/{total} | {pct:5.1f}%] row_index={idx} "
            f"processed={processed} failures={failures}",
            flush=True,
        )

        try:
            content = call_openrouter(
                api_key=api_key,
                model=args.model,
                user_prompt=prompt,
                timeout_seconds=args.timeout_seconds,
            )
            labels = parse_label_json(content)
            df.at[idx, "manual_is_disruption"] = labels["manual_is_disruption"]
            df.at[idx, "manual_impact_score"] = labels["manual_impact_score"]
            df.at[idx, "manual_notes"] = labels["manual_notes"]
            processed += 1
            print(
                f"  -> labeled: disruption={labels['manual_is_disruption']} "
                f"impact={labels['manual_impact_score']}",
                flush=True,
            )

            if processed % args.checkpoint_every == 0:
                save_df(df, output_path)
                print(f"Checkpoint saved after {processed} rows.")

            time.sleep(args.sleep_seconds)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            failures += 1
            df.at[idx, "manual_notes"] = f"ERROR: network/API failure: {exc}"
            print(f"[row={idx}] API/network error: {exc}", file=sys.stderr)
            time.sleep(max(1.0, args.sleep_seconds))
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            failures += 1
            df.at[idx, "manual_notes"] = f"ERROR: parse/validation failure: {exc}"
            print(f"[row={idx}] parse/validation error: {exc}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            df.at[idx, "manual_notes"] = f"ERROR: unexpected: {exc}"
            print(f"[row={idx}] unexpected error: {exc}", file=sys.stderr)

    save_df(df, output_path)
    print(
        f"Done. processed={processed}, failures={failures}, output={output_path}"
    )


if __name__ == "__main__":
    main()
