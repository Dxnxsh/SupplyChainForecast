"""Gemini API client (google-genai SDK).

Used by the disruption cascade. Forces JSON output (response_mime_type) so we don't
fight truncated/garbled JSON like the earlier gateway. Retries on transient/rate-limit
errors. Key: GEMINI_API_KEY in env / .env. Default model: gemini-2.5-flash.
"""

from __future__ import annotations

import os
import random
import time

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-3.1-flash-lite"
CALL_SPACING_S = 0.5  # paid Agent Platform; minimal cushion

# Agent Platform (aiplatform.googleapis.com) via Application Default Credentials.
# Requires: gcloud auth application-default login  (OAuth), not an API key.
GEMINI_PROJECT = os.getenv("GEMINI_PROJECT", "gen-lang-client-0142700148")
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION", "global")

_client = None


def _get_client():
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if key:
            # Agent Platform express mode (API key).
            _client = genai.Client(enterprise=True, api_key=key)
        else:
            # Agent Platform via Application Default Credentials.
            _client = genai.Client(
                enterprise=True, project=GEMINI_PROJECT, location=GEMINI_LOCATION
            )
    return _client


def generate(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_output_tokens: int = 700,
    retries: int = 8,
) -> str:
    """Return the model's text response (JSON string). Raises on repeated failure.

    Long, jittered backoff so a per-minute 429 (RESOURCE_EXHAUSTED) rides out the rate
    window within the call instead of failing the row.
    """
    client = _get_client()
    model_id = (model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)).strip()
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type="application/json",
    )
    last = None
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(model=model_id, contents=user, config=config)
            return resp.text or ""
        except Exception as exc:  # transient / rate-limit / server errors
            last = exc
            time.sleep(min(60, 8 * (attempt + 1)) + random.uniform(0, 3))
    raise RuntimeError(f"Gemini call failed after {retries} retries: {last}")
