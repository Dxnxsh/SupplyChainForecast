"""Financial sentiment via ProsusAI/finbert (default on). Set USE_FINBERT_RISK=0 to disable."""

from __future__ import annotations

import os
import warnings
import gc
from typing import Any

_pipeline: Any = None
# Set when CUDA/HIP inference fails (e.g. ROCm wheel missing kernels for RDNA2 — "invalid device function").
_FINBERT_CPU_LOCKED = False


def _is_gpu_exec_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if "hip error" in msg or "invalid device function" in msg:
        return True
    if "cuda error" in msg and "invalid" in msg:
        return True
    name = type(exc).__name__.lower()
    return "accelerator" in name


def _force_finbert_cpu(reason: str) -> None:
    global _pipeline, _FINBERT_CPU_LOCKED
    _pipeline = None
    _FINBERT_CPU_LOCKED = True
    warnings.warn(
        f"FinBERT: GPU inference failed ({reason}); using CPU for this process. "
        "For AMD RX 6000 series this often means the PyTorch ROCm build lacks your GPU arch; "
        "try FINBERT_DEVICE=cpu, a different ROCm/PyTorch combo, or HSA_OVERRIDE_GFX_VERSION per distro docs.",
        UserWarning,
        stacklevel=3,
    )


def _pipeline_device():
    forced = (os.getenv("FINBERT_DEVICE") or "").strip().lower()
    if _FINBERT_CPU_LOCKED or forced == "cpu":
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
        # Tiny forward to catch HIP "invalid device function" (gfx mismatch) before batch scoring.
        if isinstance(device, int) and device >= 0:
            try:
                _pipeline("ok")
            except Exception as e:
                if _is_gpu_exec_error(e):
                    _force_finbert_cpu(str(e).split("\n")[0][:120])
                    device = -1
                    _pipeline = pipeline(
                        "sentiment-analysis",
                        model=model_name,
                        tokenizer=model_name,
                        device=device,
                        truncation=True,
                        max_length=512,
                    )
                else:
                    raise
    return _pipeline


def unload_finbert():
    """Clear the FinBERT pipeline from RAM and trigger garbage collection."""
    global _pipeline
    if _pipeline is not None:
        print("📉 Unloading FinBERT model from RAM...")
        # Explicitly clear internal references to help GC
        try:
            if hasattr(_pipeline, "model"):
                _pipeline.model.to("cpu")
                del _pipeline.model
            if hasattr(_pipeline, "tokenizer"):
                del _pipeline.tokenizer
        except Exception:
            pass
            
        _pipeline = None
        
        # Multiple GC passes to catch circular references
        gc.collect()
        gc.collect()
        
        # If using CUDA or MPS, try to clear cache
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                # On modern torch, mps.empty_cache() exists
                try:
                    torch.mps.empty_cache()
                except Exception:
                    pass
        except Exception:
            pass


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
    try:
        out = pipe(text[:8000])[0]
    except Exception as e:
        if not _FINBERT_CPU_LOCKED and _is_gpu_exec_error(e):
            _force_finbert_cpu(str(e).split("\n")[0][:120])
            out = get_finbert_pipeline()(text[:8000])[0]
        else:
            raise
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
    try:
        raw = pipe(trimmed)
    except Exception as e:
        if not _FINBERT_CPU_LOCKED and _is_gpu_exec_error(e):
            _force_finbert_cpu(str(e).split("\n")[0][:120])
            raw = get_finbert_pipeline()(trimmed)
        else:
            raise
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
