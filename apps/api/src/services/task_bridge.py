"""Cầu nối tới Celery.

API không import code worker — chỉ gửi task theo TÊN. Nhờ vậy API chạy được
kể cả khi worker chưa cài đủ thư viện nặng (whisper, torch...).
"""

from __future__ import annotations

import uuid

from celery import Celery

from ..config import get_settings

_app: Celery | None = None

PROCESS_VIDEO = "reup.process_video"
RETRY_FROM_STEP = "reup.retry_from_step"


def celery() -> Celery:
    global _app
    if _app is None:
        s = get_settings()
        _app = Celery("reup-api", broker=s.redis_url, backend=s.redis_url)
    return _app


def start_processing(video_id: uuid.UUID) -> str:
    result = celery().send_task(PROCESS_VIDEO, args=[str(video_id)], queue="download")
    return result.id


def retry_from(video_id: uuid.UUID, step: str | None) -> str:
    result = celery().send_task(
        RETRY_FROM_STEP, args=[str(video_id), step], queue="download"
    )
    return result.id
