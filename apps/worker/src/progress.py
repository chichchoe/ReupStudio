"""Publish tiến trình lên Redis để API broadcast xuống WebSocket.

Không lưu % vào DB — chỉ lưu bước và trạng thái.
"""

from __future__ import annotations

import json
from typing import Any

import redis
from reup_core.logging import get_logger

from .config import get_settings

log = get_logger(__name__)
_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def _publish(channel: str, payload: dict[str, Any]) -> None:
    try:
        _redis().publish(channel, json.dumps(payload, ensure_ascii=False))
    except Exception as exc:  # mất Redis không được làm hỏng job
        log.warning("progress.publish_failed", error=str(exc))


def progress(video_id: str, step: str, percent: int, note: str | None = None) -> None:
    _publish(
        f"reup:progress:{video_id}",
        {
            "type": "progress",
            "video_id": video_id,
            "step": step,
            "percent": max(0, min(100, int(percent))),
            "note": note,
        },
    )


def status_changed(video_id: str, status: str, step: str | None = None, error: str | None = None) -> None:
    _publish(
        f"reup:status:{video_id}",
        {
            "type": "status",
            "video_id": video_id,
            "status": status,
            "step": step,
            "error": error,
        },
    )


def alert(level: str, title: str, detail: str = "") -> None:
    _publish("reup:alert", {"type": "alert", "level": level, "title": title, "detail": detail})
