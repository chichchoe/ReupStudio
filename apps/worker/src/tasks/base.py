"""Hạ tầng dùng chung cho task: ghi job_runs, cập nhật trạng thái, publish tiến trình.

Task Celery phải MỎNG — chỉ điều phối. Logic nằm trong ``pipeline/``.
"""

from __future__ import annotations

import functools
import time
import uuid
from collections.abc import Callable
from typing import Any

from reup_core.db import session_scope
from reup_core.enums import PipelineStep, VideoStatus
from reup_core.logging import get_logger
from reup_core.models import JobRun, Video

from .. import progress as prog

log = get_logger(__name__)


def load_video(session, video_id: str) -> Video:
    video = session.get(Video, uuid.UUID(str(video_id)))
    if video is None:
        raise ValueError(f"Không tìm thấy video {video_id}")
    return video


def pipeline_step(step: PipelineStep) -> Callable:
    """Decorator cho task pipeline.

    Tự động: tạo JobRun → cập nhật ``video.current_step`` → publish tiến trình →
    ghi lỗi vào DB khi thất bại. Hàm được bọc nhận ``(session, video)``.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., str]:
        @functools.wraps(func)
        def wrapper(video_id: str, *args, **kwargs) -> str:
            started = time.perf_counter()
            with session_scope() as session:
                video = load_video(session, video_id)
                run = JobRun(
                    video_id=video.id,
                    step=step.value,
                    status="running",
                    meta={},
                )
                session.add(run)
                video.current_step = step.value
                video.status = VideoStatus.RUNNING
                video.error_message = None
                session.flush()
                run_id = run.id

            prog.progress(str(video_id), step.value, 0)
            prog.status_changed(str(video_id), VideoStatus.RUNNING.value, step.value)

            try:
                with session_scope() as session:
                    video = load_video(session, video_id)
                    meta = func(session, video, *args, **kwargs) or {}
            except Exception as exc:
                elapsed = time.perf_counter() - started
                log.exception("step.failed", step=step.value, video_id=str(video_id))
                with session_scope() as session:
                    run = session.get(JobRun, run_id)
                    if run:
                        run.status = "failed"
                        run.duration_sec = elapsed
                        run.log = f"{type(exc).__name__}: {exc}"[:8000]
                    video = load_video(session, video_id)
                    video.status = VideoStatus.ERROR
                    video.error_message = f"{step.value}: {exc}"[:2000]
                prog.status_changed(
                    str(video_id), VideoStatus.ERROR.value, step.value, str(exc)
                )
                raise

            elapsed = time.perf_counter() - started
            with session_scope() as session:
                run = session.get(JobRun, run_id)
                if run:
                    run.status = "success"
                    run.duration_sec = elapsed
                    run.meta = meta
            prog.progress(str(video_id), step.value, 100)
            log.info("step.done", step=step.value, video_id=str(video_id), sec=round(elapsed, 1))
            return str(video_id)

        return wrapper

    return decorator
