#!/usr/bin/env python3
"""
Standalone location NER only (same HF model family as src/preprocessing.py).

Use on Google Colab with a GPU runtime:
  !pip install -q transformers accelerate datasets
  import os; os.environ["TORCH_DEVICE"] = "cuda"
  !python scripts/ner_only.py -t "Flooding near the Port of Long Beach."

From repo root locally:
  python scripts/ner_only.py -i data/sample.txt
  python scripts/ner_only.py --raw-dir data/raw/web_scrape -o data/ner/locations.jsonl
  python scripts/ner_only.py -i data/raw/web_scrape/all_news_q4_2025.json -o out.jsonl
  python scripts/ner_only.py -i articles.jsonl --text-field text -o locations.jsonl

Your raw scrape files are a JSON *array* at the root ([ {...}, {...} ]), not JSONL.
Use --raw-dir or point -i at one of those .json files.

Env:
  NER_MODEL        default: dbmdz/bert-large-cased-finetuned-conll03-english
  NER_BATCH_SIZE   default: 48 on CUDA (~15GB VRAM), 16 on MPS/CPU unless set
  TORCH_DEVICE     cuda | mps | cpu (optional override)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

# (article_url or None, full text) — matches web_scrape `label` + `text` rows
Document = Tuple[Optional[str], str]


def _default_ner_batch_size() -> int:
    """CUDA: 48 fits ~15GB VRAM for bert-large NER; lower default on MPS/CPU."""
    env = os.getenv("NER_BATCH_SIZE")
    if env:
        return int(env)
    try:
        import torch

        if torch.cuda.is_available():
            return 48
    except ImportError:
        pass
    return 16


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


def _clean_control_chars(content: str) -> str:
    """Same idea as preprocessing.load_raw_data — strips ASCII controls that break json.loads."""
    return re.sub(r"[\x00-\x1f]", "", content)


def _entry_to_url_and_text(entry: dict, text_field: str) -> Optional[Document]:
    if not isinstance(entry, dict):
        return None
    raw = entry.get(text_field)
    if raw is None or not str(raw).strip():
        return None
    label = entry.get("label") or ""
    parts = str(label).split(";")
    url = parts[2].strip() if len(parts) > 2 else ""
    return (url if url else None, str(raw))


def load_web_scrape_json_array(path: Path, text_field: str) -> list[Document]:
    """One file whose root is a JSON array of objects with label + text (your raw exports)."""
    with path.open(encoding="utf-8") as f:
        content = _clean_control_chars(f.read())
    data = json.loads(content)
    if not isinstance(data, list):
        print(f"⚠️ Expected JSON array in {path}; got {type(data).__name__}.", file=sys.stderr)
        return []
    out: list[Document] = []
    for entry in data:
        doc = _entry_to_url_and_text(entry, text_field)
        if doc:
            out.append(doc)
    return out


def load_web_scrape_directory(dir_path: Path, text_field: str) -> list[Document]:
    """All *.json in folder (same format as data/raw/web_scrape/)."""
    paths = sorted(dir_path.glob("*.json"))
    if not paths:
        print(f"No .json files in {dir_path}", file=sys.stderr)
        return []
    out: list[Document] = []
    for p in paths:
        out.extend(load_web_scrape_json_array(p, text_field))
        print(f"  Loaded {p.name}: cumulative {len(out)} article(s)", file=sys.stderr)
    return out


def load_line_or_jsonl_input(path: Path, text_field: str) -> list[Document]:
    """JSONL (one object per line) or plain text lines — no URL metadata."""
    docs: list[Document] = []
    with path.open(encoding="utf-8") as f:
        full = f.read()
    stripped = full.strip()
    if stripped.startswith("["):
        return load_web_scrape_json_array(path, text_field)

    for line in full.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                t = obj.get(text_field)
                if t is not None:
                    url = None
                    lab = obj.get("label")
                    if lab:
                        parts = str(lab).split(";")
                        if len(parts) > 2:
                            u = parts[2].strip()
                            url = u if u else None
                    docs.append((url, str(t)))
            except json.JSONDecodeError:
                docs.append((None, line))
        else:
            docs.append((None, line))
    return docs


def _truncate(s: str, max_chars: Optional[int]) -> str:
    if max_chars is None or max_chars <= 0:
        return s
    return s if len(s) <= max_chars else s[:max_chars]


def ner_loc_predictions(
    ner_pipe,
    texts: list[str],
    *,
    batch_size: int,
    max_chars: Optional[int],
):
    """
    Run token-classification NER and return raw entity lists per row.
    Uses Hugging Face Dataset + KeyDataset on GPU so the pipeline batches efficiently
    (avoids the 'sequentially on GPU' warning).
    """
    if not texts:
        return []
    trimmed = [_truncate(t, max_chars) for t in texts]
    bs = max(1, min(batch_size, len(trimmed)))

    try:
        from datasets import Dataset
        from transformers.pipelines.pt_utils import KeyDataset

        ds = Dataset.from_dict({"text": trimmed})
        predictions = ner_pipe(KeyDataset(ds, "text"), batch_size=bs)
    except ImportError:
        predictions = ner_pipe(trimmed, batch_size=bs)

    if not isinstance(predictions, list):
        predictions = list(predictions)

    out: list[list[str]] = []
    for entities in predictions:
        locs = [e["word"] for e in entities if e.get("entity_group") == "LOC"]
        out.append(list(dict.fromkeys(locs)))
    return out


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
        default=_default_ner_batch_size(),
        help="Micro-batch for inference; default 48 on CUDA (~15GB VRAM), 16 on MPS/CPU "
        "(override with NER_BATCH_SIZE). Lower if CUDA OOM.",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        metavar="DIR",
        help="Folder of web_scrape *.json files (root JSON array per file)",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        help="Line-based JSONL/plain text, OR one web_scrape-style JSON array file",
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
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process only the first N articles (after loading)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the tqdm progress bar (for logs / piping)",
    )
    args = parser.parse_args()

    max_chars = None if args.max_chars == 0 else args.max_chars

    device = _select_device()
    dev_name = "cpu" if device == -1 else ("cuda" if device == 0 else str(device))
    print(f"Loading NER model {args.model!r} on {dev_name}...", file=sys.stderr)
    print(
        f"NER batch size {args.batch_size} (env NER_BATCH_SIZE; reduce if OOM)",
        file=sys.stderr,
    )

    from transformers import pipeline

    ner = pipeline(
        "ner",
        model=args.model,
        aggregation_strategy="simple",
        device=device,
    )

    out_f = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        if args.text:
            if args.input or args.raw_dir:
                print("Use either --text or (--input / --raw-dir), not both.", file=sys.stderr)
                return 2
            locs = ner_loc_predictions(
                ner, [args.text], batch_size=args.batch_size, max_chars=max_chars
            )[0]
            rec = {"locations": locs, "text_preview": args.text[:500]}
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return 0

        if bool(args.raw_dir) == bool(args.input):
            print("Provide exactly one of: --text | --input | --raw-dir", file=sys.stderr)
            return 2

        if args.raw_dir:
            if not args.raw_dir.is_dir():
                print(f"Not a directory: {args.raw_dir}", file=sys.stderr)
                return 2
            print(f"Loading raw JSON arrays from {args.raw_dir}...", file=sys.stderr)
            documents = load_web_scrape_directory(args.raw_dir, args.text_field)
        else:
            assert args.input is not None
            if not args.input.is_file():
                print(f"Not a file: {args.input}", file=sys.stderr)
                return 2
            documents = load_line_or_jsonl_input(args.input, args.text_field)

        if args.limit is not None:
            documents = documents[: max(0, args.limit)]

        if not documents:
            print("No texts loaded.", file=sys.stderr)
            return 1

        texts = [t for _, t in documents]
        bs = max(1, args.batch_size)

        try:
            from tqdm import tqdm
        except ImportError:
            tqdm = None  # type: ignore

        use_bar = tqdm is not None and not args.no_progress
        pbar = (
            tqdm(
                total=len(documents),
                desc="NER",
                unit="article",
                file=sys.stderr,
                mininterval=0.5,
            )
            if use_bar
            else None
        )
        try:
            for start in range(0, len(texts), bs):
                chunk_docs = documents[start : start + bs]
                chunk_texts = [t for _, t in chunk_docs]
                for (url, text), locs in zip(
                    chunk_docs,
                    ner_loc_predictions(
                        ner,
                        chunk_texts,
                        batch_size=args.batch_size,
                        max_chars=max_chars,
                    ),
                ):
                    rec = {"locations": locs, "text_preview": text[:500]}
                    if url:
                        rec["article_url"] = url
                    out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    if pbar is not None:
                        pbar.update(1)
        finally:
            if pbar is not None:
                pbar.close()

        print(f"Processed {len(documents)} document(s).", file=sys.stderr)
        return 0
    finally:
        if args.output:
            out_f.close()


if __name__ == "__main__":
    raise SystemExit(main())
