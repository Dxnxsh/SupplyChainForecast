"""Financial sentiment via ProsusAI/finbert (default on). Set USE_FINBERT_RISK=0 to disable."""

from __future__ import annotations

import os
from typing import Any

_pipeline: Any = None


def _pipeline_device():
    forced = (os.getenv("FINBERT_DEVICE") or "").strip().lower()
    if forced == "cpu":
        return -1
    try:
        import torch

        if forced == "cuda" and torch.cuda.is_available():
            return 0
        if forced == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return 0
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return -1


def get_finbert_pipeline():
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline

        model_name = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")
        device = _pipeline_device()
        _pipeline = pipeline(
            "sentiment-analysis",
            model=model_name,
            tokenizer=model_name,
            device=device,
            truncation=True,
            max_length=512,
        )
    return _pipeline


def finbert_enabled() -> bool:
    """FinBERT is default; set USE_FINBERT_RISK to 0/false/no/off to fall back to VADER in risk_scoring."""
    v = (os.getenv("USE_FINBERT_RISK") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def analyze_finbert(text: str) -> dict:
    """
    Returns label in {positive, negative, neutral}, score in [-1, 1], raw confidence 0..1.
    """
    text = (text or "").strip()
    if len(text) < 3:
        return {"label": "neutral", "sentiment_score": 0.0, "confidence": 0.0}

    pipe = get_finbert_pipeline()
    # pipeline returns list of dicts for batch; single string -> one dict
    out = pipe(text[:8000])[0]
    raw_label = str(out.get("label", "")).lower()
    conf = float(out.get("score", 0.0))

    if "positive" in raw_label:
        sentiment_score = conf
        label = "positive"
    elif "negative" in raw_label:
        sentiment_score = -conf
        label = "negative"
    else:
        sentiment_score = 0.0
        label = "neutral"

    return {
        "sentiment_label": label,
        "sentiment_score": round(max(-1.0, min(1.0, sentiment_score)), 4),
        "confidence": round(conf, 4),
    }


def batch_analyze_finbert(texts: list[str]) -> list[dict]:
    """Batch inference for RSS / enrichment."""
    if not texts:
        return []
    pipe = get_finbert_pipeline()
    trimmed = [t[:8000] if t else "" for t in texts]
    raw = pipe(trimmed)
    results = []
    for out in raw:
        raw_label = str(out.get("label", "")).lower()
        conf = float(out.get("score", 0.0))
        if "positive" in raw_label:
            sentiment_score = conf
            label = "positive"
        elif "negative" in raw_label:
            sentiment_score = -conf
            label = "negative"
        else:
            sentiment_score = 0.0
            label = "neutral"
        results.append(
            {
                "sentiment_label": label,
                "sentiment_score": round(max(-1.0, min(1.0, sentiment_score)), 4),
                "confidence": round(conf, 4),
            }
        )
    return results
