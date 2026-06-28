"""Call OpenRouter chat completions (server-side only; keep API key in env)."""

from __future__ import annotations

import os
from typing import Any

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.35,
    timeout_seconds: float = 120.0,
) -> tuple[str, str]:
    """
    Returns (assistant_text, model_used).
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    model_used = (model or os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")).strip()

    payload: dict[str, Any] = {
        "model": model_used,
        "messages": messages,
        "temperature": temperature,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "http://127.0.0.1:8080"),
        "X-Title": "SupplyChainForecast",
    }

    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(OPENROUTER_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected OpenRouter response shape: {data!r}") from exc

    return (str(text).strip(), model_used)
