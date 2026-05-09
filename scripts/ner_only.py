#!/usr/bin/env python3
"""
Standalone location NER only (same HF model family as src/preprocessing.py).

Use on Google Colab with a GPU runtime:
  !pip install -q transformers accelerate
  import os; os.environ["TORCH_DEVICE"] = "cuda"
  !python scripts/ner_only.py -t "Flooding near the Port of Long Beach."

From repo root locally:
  python scripts/ner_only.py -i data/sample.txt
  python scripts/ner_only.py -i articles.jsonl --text-field text -o locations.jsonl

Env:
  NER_MODEL        default: dbmdz/bert-large-cased-finetuned-conll03-english
  NER_BATCH_SIZE   default: 32
  TORCH_DEVICE     cuda | mps | cpu (optional override)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _select_device():
    import torch

    forced = (os.getenv("TORCH_DEVICE") or "").strip().lower()
    if forced == "cpu":
        return -1
    if forced == "cuda":
        if torch.cuda.is_available():
            return 0
        print("⚠️ TORCH_DEVICE=cuda but CUDA unavailable; using auto.", file=sys.stderr)
    if forced == "mps":
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        print("⚠️ TORCH_DEVICE=mps but MPS unavailable; using auto.", file=sys.stderr)
    if torch.cuda.is_available():
        return 0
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return -1


def _load_texts_from_input(path: Path, text_field: str) -> list[str]:
    texts: list[str] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    t = obj.get(text_field)
                    if t is not None:
                        texts.append(str(t))
                except json.JSONDecodeError:
                    texts.append(line)
            else:
                texts.append(line)
    return texts


def _truncate(s: str, max_chars: int | None) -> str:
    if max_chars is None or max_chars <= 0:
        return s
    return s if len(s) <= max_chars else s[:max_chars]


def main() -> int:
    parser = argparse.ArgumentParser(description="HF NER: LOC entities only (Colab/local).")
    parser.add_argument(
        "--model",
        default=os.getenv("NER_MODEL", "dbmdz/bert-large-cased-finetuned-conll03-english"),
        help="Hugging Face model id for token-classification NER",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("NER_BATCH_SIZE", "32")),
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        help="UTF-8 file: one JSON object per line (--text-field) or one plain text paragraph per line",
    )
    parser.add_argument(
        "--text-field",
        default="text",
        help="JSON field name when each line is a JSON object",
    )
    parser.add_argument("--text", "-t", help="Single document; prints one JSON object to stdout")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Write JSONL results here (default: stdout)",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=12_000,
        help="Truncate each document to this many characters before NER (0 = no truncation)",
    )
    args = parser.parse_args()

    max_chars = None if args.max_chars == 0 else args.max_chars

    device = _select_device()
    dev_name = "cpu" if device == -1 else ("cuda" if device == 0 else str(device))
    print(f"Loading NER model {args.model!r} on {dev_name}...", file=sys.stderr)

    from transformers import pipeline

    ner = pipeline(
        "ner",
        model=args.model,
        aggregation_strategy="simple",
        device=device,
    )

    def extract_batch(texts: list[str]) -> list[list[str]]:
        if not texts:
            return []
        trimmed = [_truncate(t, max_chars) for t in texts]
        predictions = ner(trimmed, batch_size=args.batch_size)
        out: list[list[str]] = []
        for entities in predictions:
            locs = [e["word"] for e in entities if e.get("entity_group") == "LOC"]
            out.append(list(dict.fromkeys(locs)))
        return out

    out_f = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        if args.text:
            locs = extract_batch([args.text])[0]
            rec = {"locations": locs, "text_preview": args.text[:500]}
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return 0

        if not args.input:
            print("Provide --text or --input", file=sys.stderr)
            return 2

        texts = _load_texts_from_input(args.input, args.text_field)
        if not texts:
            print("No texts loaded.", file=sys.stderr)
            return 1

        bs = max(1, args.batch_size)
        for start in range(0, len(texts), bs):
            chunk = texts[start : start + bs]
            for text, locs in zip(chunk, extract_batch(chunk)):
                rec = {"locations": locs, "text_preview": text[:500]}
                out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"Processed {len(texts)} document(s).", file=sys.stderr)
        return 0
    finally:
        if args.output:
            out_f.close()


if __name__ == "__main__":
    raise SystemExit(main())
