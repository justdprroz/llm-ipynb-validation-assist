"""Robust extraction of a JSON object/array from a noisy LLM response."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> str:
    if not text or not text.strip():
        return text or ""

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.DOTALL)

    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)

    cleaned = cleaned.strip()

    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = cleaned.find(open_ch)
        end = cleaned.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            return cleaned[start : end + 1]

    return cleaned


def loads(text: str | None) -> Any | None:
    """Parse a model response into JSON; return None on any failure."""
    if text is None:
        return None
    try:
        return json.loads(extract_json(text))
    except (json.JSONDecodeError, ValueError):
        return None
