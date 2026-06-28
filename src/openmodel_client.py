"""OpenModel API client — Messages protocol (Anthropic-style /v1/messages).

Captures the gateway quirks discovered the hard way so callers don't rediscover them:
  - deepseek-v4-flash is served at /v1/messages, NOT /v1/responses (which 404s for it).
    /v1/responses is only for OpenAI + DashScope models; /v1/chat/completions is removed.
  - There is a per-user requests-per-minute limit. Pace calls (see CALL_SPACING_S) and
    retry on transient 404/429/5xx (the gateway returns intermittent 404s under load).
  - Auth: OPENMODEL_API_KEY (om-... key) in the environment / .env.
  - Response shape is Anthropic-style: {"content": [{"type": "text", "text": "..."}], ...}.

Model list (GET https://api.openmodel.ai/v1/models) includes deepseek-v4-flash,
qwen3-max, gpt-5.x, claude-*, gemini-*, glm-*.
"""

from __future__ import annotations

import os
import time

import httpx

OPENMODEL_MESSAGES_URL = "https://api.openmodel.ai/v1/messages"
DEFAULT_MODEL = "deepseek-v4-flash"
CALL_SPACING_S = 8.0  # respect the per-user RPM limit
_RETRYABLE = {404, 408, 409, 425, 429, 500, 502, 503, 504}


def messages(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 700,
    temperature: float = 0.0,
    retries: int = 6,
    timeout_seconds: float = 120.0,
) -> str:
    """Call the OpenModel Messages API and return the assistant text.

    Raises RuntimeError if the key is missing or all retries fail.
    """
    api_key = os.getenv("OPENMODEL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENMODEL_API_KEY is not set")

    payload = {
        "model": (model or os.getenv("OPENMODEL_MODEL", DEFAULT_MODEL)).strip(),
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_status = None
    for attempt in range(retries):
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(OPENMODEL_MESSAGES_URL, headers=headers, json=payload)
        if resp.status_code in _RETRYABLE:
            last_status = resp.status_code
            time.sleep(6 + 6 * attempt)
            continue
        resp.raise_for_status()
        data = resp.json()
        return "".join(
            part.get("text", "")
            for part in data.get("content", [])
            if part.get("type") == "text"
        )
    raise RuntimeError(f"OpenModel call failed after {retries} retries (last status {last_status})")
