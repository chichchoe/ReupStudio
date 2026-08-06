"""Celery app. Mỗi loại việc một hàng đợi riêng để GPU không bị nghẽn vì tải file."""

from __future__ import annotations

from celery import Celery
from reup_core.logging import setup_logging

from .config import get_settings

settings = get_settings()
setup_logging(settings.log_level)

app = Celery("reup", broker=settings.redis_url, backend=settings.redis_url)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,  # job chạy lại nếu worker chết giữa chừng
    worker_prefetch_multiplier=1,
    result_expires=3600 * 24,
    broker_transport_options={"visibility_timeout": 3600 * 6},
    task_routes={
        "reup.download_video": {"queue": "download"},
        "reup.probe_video": {"queue": "media"},
        "reup.transcribe_video": {"queue": "gpu"},
        "reup.translate_video": {"queue": "media"},
        "reup.format_subtitles": {"queue": "media"},
        "reup.render_video": {"queue": "media"},
        "reup.process_video": {"queue": "download"},
        "reup.retry_from_step": {"queue": "download"},
    },
)

# Đăng ký task
app.autodiscover_tasks(["src.tasks"], force=True)
from .tasks import video as _video_tasks  # noqa: E402,F401
