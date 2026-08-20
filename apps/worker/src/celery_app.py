"""Celery app. Mỗi loại việc một hàng đợi riêng để GPU không bị nghẽn vì tải file."""

from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_init
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
        #: M3 chạy model nặng (RapidOCR rồi LaMa trên Metal) nên đi hàng "gpu",
        #: nơi worker chạy concurrency 1. Thiếu hai dòng này thì task rơi vào
        #: hàng mặc định mà không worker nào nghe: chain được gửi đi, không có
        #: lỗi nào, và video đứng im mãi mãi.
        "reup.detect_masks": {"queue": "gpu"},
        "reup.inpaint_video": {"queue": "gpu"},
        #: TTS là lời gọi MẠNG chứ không phải model chạy máy, nên đi hàng
        #: "media" cùng các bước ffmpeg — chiếm chỗ hàng "gpu" (concurrency 1)
        #: sẽ chặn mất bước vá vốn mới là chỗ nghẽn thật.
        "reup.tts_video": {"queue": "media"},
        "reup.tts_video_chain_sau_duyet": {"queue": "download"},
        "reup.translate_video_chain": {"queue": "download"},
        "reup.doc_lai_sau_khi_sua": {"queue": "download"},
        "reup.dich_lai": {"queue": "media"},
        #: ffmpeg + Whisper, đều là việc CPU — không chiếm hàng "gpu".
        "reup.chuan_bi_giong": {"queue": "media"},
        "reup.render_video": {"queue": "media"},
        "reup.process_video": {"queue": "download"},
        "reup.retry_from_step": {"queue": "download"},
    },
)


@worker_process_init.connect
def _bo_ket_noi_db_thua_ke(**_: object) -> None:
    """Tiến trình con vừa fork phải BỎ kết nối DB thừa kế của tiến trình cha.

    ``get_settings()`` ở đầu file này đọc cấu hình từ database, nên engine đã
    được dựng và pool đã giữ sẵn một kết nối NGAY TRONG TIẾN TRÌNH CHA. Celery
    prefork nhân bản tiến trình đó: mọi con cùng thừa kế một socket, tức cùng
    một phiên PostgreSQL.

    Hậu quả đã gặp ngày 16.08.2026: psycopg3 tự chuyển câu lệnh sang dạng
    prepared sau vài lần chạy và đặt tên ``_pg3_0``, ``_pg3_1``… Hai tiến trình
    con đếm riêng nên cùng đòi tạo ``_pg3_0`` trên cùng một phiên, và bước
    ``format_sub`` chết với ``DuplicatePreparedStatement``.

    ``close=False`` là bắt buộc: con chỉ ĐƯỢC BUÔNG socket, không được đóng —
    đóng là giật mất kết nối mà cha và các con khác vẫn đang trỏ vào.
    """
    from reup_core.db import get_engine

    get_engine().dispose(close=False)


# Đăng ký task
app.autodiscover_tasks(["src.tasks"], force=True)
from .tasks import video as _video_tasks  # noqa: E402,F401
from .tasks import dich_lai as _dich_lai_tasks  # noqa: E402,F401
from .tasks import giong as _giong_tasks  # noqa: E402,F401
