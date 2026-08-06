"""Bóc mảng JSON khỏi câu trả lời của LLM (đôi khi bị bọc trong markdown)."""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


def extract_json_array(text: str) -> list[str] | None:
    text = text.strip()

    match = _FENCE.search(text)
    if match:
        text = match.group(1).strip()

    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None

    if not isinstance(data, list):
        return None
    return [str(item) for item in data]
