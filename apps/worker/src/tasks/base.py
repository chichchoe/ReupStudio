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
from ..errors import TaskArgumentError

log = get_logger(__name__)


def load_video(session, video_id: str) -> Video:
    video = session.get(Video, uuid.UUID(str(video_id)))
    if video is None:
        raise ValueError(f"Không tìm thấy video {video_id}")
    return video


def coerce_video_id(value: object, step: PipelineStep) -> str:
    """Chốt chặn ở cổng vào task: tham số đầu phải là ``video_id``.

    Kiểm ngay dòng đầu ``wrapper``, TRƯỚC khi mở session — để thứ truyền nhầm
    không đi sâu thêm rồi nổ bằng một thông báo không ai đọc hiểu.
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise TaskArgumentError(
                f"Bước {step.value}: chuỗi {value!r} ở vị trí video_id không phải UUID"
            ) from exc
    raise TaskArgumentError(
        f"Bước {step.value}: vị trí video_id nhận {type(value).__name__} ({value!r}) "
        "thay vì UUID. Kiểm tra xem task có khai báo bind=True không — bind=True "
        "chèn self vào đúng chỗ này. Cần retry thì dùng autoretry_for, nó không "
        "đụng tới danh sách tham số."
    )


def _mark_failed(
    video_id: str,
    step: PipelineStep,
    run_id: uuid.UUID | None,
    exc: BaseException,
    elapsed: float,
) -> None:
    """Ghi lại dấu vết thất bại — cố gắng hết sức, không che lỗi gốc.

    Nếu bản thân việc ghi cũng hỏng thì log ra rồi thôi: lỗi gốc quan trọng
    hơn và sẽ được ``raise`` tiếp ở chỗ gọi.
    """
    try:
        with session_scope() as session:
            if run_id is not None:
                run = session.get(JobRun, run_id)
                if run is not None:
                    run.status = "failed"
                    run.duration_sec = elapsed
                    run.log = f"{type(exc).__name__}: {exc}"[:8000]
            video = session.get(Video, uuid.UUID(video_id))
            if video is None:
                log.warning("step.failed_video_missing", video_id=video_id)
                return
            video.status = VideoStatus.ERROR.value
            video.current_step = step.value
            video.error_message = f"{step.value}: {exc}"[:2000]
    except Exception:
        log.exception("step.mark_failed_error", video_id=video_id, step=step.value)
        return

    prog.status_changed(video_id, VideoStatus.ERROR.value, step.value, str(exc))


def pipeline_step(step: PipelineStep) -> Callable:
    """Decorator cho task pipeline.

    Tự động: tạo JobRun → cập nhật ``video.current_step`` → publish tiến trình →
    ghi lỗi vào DB khi thất bại. Hàm được bọc nhận ``(session, video)``.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., str]:
        @functools.wraps(func)
        def wrapper(video_id: str, *args, **kwargs) -> str:
            #: Kiểm tham số TRƯỚC mọi thứ khác. Trước đây đoạn nạp video và tạo
            #: JobRun nằm ngoài ``try``, nên lỗi ở đó không ghi được trạng thái:
            #: video kẹt ``queued`` im lặng và người dùng ngồi chờ vô hạn. Giờ
            #: mọi đường thất bại đều đi qua ``_mark_failed``.
            video_id = coerce_video_id(video_id, step)
            started = time.perf_counter()
            run_id: uuid.UUID | None = None

            try:
                with session_scope() as session:
                    video = load_video(session, video_id)
                    #: Video bị loại (trùng, hoặc bộ lọc chặn) thì mọi bước còn lại
                    #: của chain thành no-op — rẻ hơn và sạch hơn là huỷ chain giữa
                    #: chừng bằng cách raise, vì raise sẽ bị ghi thành lỗi thật.
                    if video.status == VideoStatus.SKIPPED:
                        log.info("step.skipped", step=step.value, video_id=video_id)
                        return video_id
                    run = JobRun(
                        video_id=video.id,
                        step=step.value,
                        status="running",
                        meta={},
                    )
                    session.add(run)
                    video.current_step = step.value
                    video.status = VideoStatus.RUNNING.value
                    video.error_message = None
                    session.flush()
                    run_id = run.id

                prog.progress(video_id, step.value, 0)
                prog.status_changed(video_id, VideoStatus.RUNNING.value, step.value)

                with session_scope() as session:
                    video = load_video(session, video_id)
                    meta = func(session, video, *args, **kwargs) or {}
            except Exception as exc:
                elapsed = time.perf_counter() - started
                log.exception("step.failed", step=step.value, video_id=video_id)
                _mark_failed(video_id, step, run_id, exc, elapsed)
                raise

            elapsed = time.perf_counter() - started
            with session_scope() as session:
                run = session.get(JobRun, run_id)
                if run:
                    run.status = "success"
                    run.duration_sec = elapsed
                    run.meta = meta
            prog.progress(video_id, step.value, 100)
            log.info("step.done", step=step.value, video_id=video_id, sec=round(elapsed, 1))
            return video_id

        #: ``functools.wraps`` gán ``wrapper.__wrapped__ = func``, mà
        #: ``inspect.signature`` mặc định NHÌN XUYÊN qua thuộc tính đó. Celery
        #: dùng ``inspect.signature`` để kiểm tham số trong ``apply_async``, nên
        #: nó đọc phải chữ ký hàm bên trong — ``(session, video)`` — rồi từ chối
        #: lời gọi một tham số bằng ``TypeError: missing 1 required positional
        #: argument: 'video'``. Xoá ``__wrapped__`` để Celery thấy đúng chữ ký
        #: thật của task là ``(video_id, *args, **kwargs)``.
        #:
        #: Đây mới là gốc của việc ``download_video_task`` từng phải mang
        #: ``bind=True``: bind cắt bớt một tham số nên qua được vòng kiểm, đổi
        #: lại task chết ngay khi chạy. Vá triệu chứng, không vá nguyên nhân.
        del wrapper.__wrapped__

        return wrapper

    return decorator
