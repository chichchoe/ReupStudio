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
RENDER_VARIANTS = "reup.render_variants"
TTS_CHAIN_SAU_DUYET = "reup.tts_video_chain_sau_duyet"
TRANSLATE_VIDEO_CHAIN = "reup.translate_video_chain"
DOC_LAI_SAU_KHI_SUA = "reup.doc_lai_sau_khi_sua"


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
    result = celery().send_task(RETRY_FROM_STEP, args=[str(video_id), step], queue="download")
    return result.id


def render_variants(video_id: uuid.UUID) -> str:
    """Đẩy task ``render_variants_task`` (M4-WK-05) — render nhiều bản, một
    bản mỗi nền tảng đích. Dùng queue ``media`` giống ``reup.render_video``
    (FFmpeg là việc CPU, không cần GPU).
    """
    result = celery().send_task(RENDER_VARIANTS, args=[str(video_id)], queue="media")
    return result.id


def translate_video(video_id: uuid.UUID) -> str:
    """Đẩy NỬA SAU pipeline: dịch, chuẩn hoá phụ đề, render.

    Gọi khi người dùng đã chọn model AI và bấm Dịch ở tab "Chờ dịch". Model
    nằm sẵn trong ``process_config``, task tự đọc từ DB — không truyền qua tham
    số, đúng nguyên tắc ``si()`` của chuỗi task.

    Queue ``media`` giống ``render_variants``: bước dịch gọi mạng, hai bước sau
    là FFmpeg — đều là việc CPU, không cần GPU.
    """
    result = celery().send_task(TRANSLATE_VIDEO_CHAIN, args=[str(video_id)], queue="media")
    return result.id


def doc_lai_sau_khi_sua(video_id: uuid.UUID) -> str:
    """Đọc lại giọng cho những câu người dùng vừa sửa.

    Queue ``download`` giống các task điều phối khác — nó chỉ xếp việc rồi
    thoát, phần nặng nằm ở ``reup.tts_video``.

    ``queue=`` BẮT BUỘC phải truyền: app Celery của API không mang
    ``task_routes`` của worker, thiếu nó là task rơi vào hàng mặc định
    ``celery`` mà không worker nào nghe. Người dùng bấm "Lưu và đọc lại", API
    trả 200, và giọng không bao giờ được đọc lại — không lỗi, không log.
    """
    result = celery().send_task(DOC_LAI_SAU_KHI_SUA, args=[str(video_id)], queue="download")
    return result.id


def tiep_tuc_sau_duyet(video_id: uuid.UUID) -> str:
    """Đẩy CHẶNG CUỐI: xoá chữ cứng rồi render, sau khi người dùng đã duyệt.

    Queue ``download`` giống các task điều phối khác — nó chỉ xếp chain rồi
    thoát, phần nặng nằm ở các task con.
    """
    result = celery().send_task(TTS_CHAIN_SAU_DUYET, args=[str(video_id)], queue="download")
    return result.id
