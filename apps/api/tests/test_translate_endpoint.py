"""``POST /videos/{id}/translate`` — người dùng chọn AI rồi bấm Dịch.

Pipeline dừng sau bước nhận dạng (trạng thái ``review``); endpoint này là chỗ
khởi động nửa sau. Model được ghi vào ``process_config["llm_model"]`` TRƯỚC khi
gửi task, để worker đọc từ DB — đúng nguyên tắc ``si()`` của chuỗi task Celery
(mỗi bước tự đọc trạng thái, không truyền tham số qua lại).
"""

from __future__ import annotations

import uuid

import pytest
from reup_core.enums import VideoStatus
from reup_core.models import Video
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.errors import ApiError, NotFound
from src.services import video_service


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _video(db, *, status=VideoStatus.REVIEW, process_config=None) -> Video:
    video = Video(
        source_platform="douyin",
        source_video_id=uuid.uuid4().hex[:12],
        source_url="https://www.douyin.com/video/1",
        status=status,
        flags={},
        process_config=process_config or {},
    )
    db.add(video)
    db.commit()
    return video


def test_luu_model_da_chon_vao_process_config(db) -> None:
    video = _video(db)

    video_service.request_translate(db, video.id, "gemini-3.5-flash-lite")
    db.commit()

    assert db.get(Video, video.id).process_config["llm_model"] == "gemini-3.5-flash-lite"


def test_giu_nguyen_cac_khoa_khac_trong_process_config(db) -> None:
    """``process_config`` còn chứa tone, reframe_mode, hook_text — chọn model
    không được xoá mất chúng."""
    video = _video(db, process_config={"tone": "ngon_tinh", "hook_text": "Xem hết nhé"})

    video_service.request_translate(db, video.id, "gemini-3.5-flash-lite")
    db.commit()

    config = db.get(Video, video.id).process_config
    assert config["tone"] == "ngon_tinh"
    assert config["hook_text"] == "Xem hết nhé"


def test_dua_video_ve_hang_doi_de_khong_ket_o_review(db) -> None:
    """Còn ở ``review`` thì giao diện vẫn hiện nó trong tab Chờ dịch dù đã bấm."""
    video = _video(db)

    video_service.request_translate(db, video.id, "gemini-3.5-flash-lite")
    db.commit()

    assert db.get(Video, video.id).status == VideoStatus.QUEUED


def test_khong_chon_model_thi_dung_mac_dinh(db) -> None:
    """Bỏ trống là hợp lệ — worker tự dùng ``LLM_MODEL`` trong cấu hình."""
    video = _video(db)

    video_service.request_translate(db, video.id, None)
    db.commit()

    assert "llm_model" not in db.get(Video, video.id).process_config


def test_tu_choi_model_khong_phai_de_dich(db) -> None:
    """Chặn ngay ở API, không để tới worker mới hỏng.

    Danh sách model của Gemini gồm cả sinh ảnh, sinh video, TTS. Chọn nhầm
    ``gemini-2.5-flash-tts`` (3 lượt/phút, 10 lượt/ngày) thì dịch chắc chắn
    hỏng — và hỏng sau khi đã đốt hạn mức.
    """
    video = _video(db)

    with pytest.raises(ApiError) as loi:
        video_service.request_translate(db, video.id, "gemini-2.5-flash-tts")

    assert "tts" in str(loi.value).lower() or "dịch" in str(loi.value).lower()


def test_tu_choi_model_sinh_anh(db) -> None:
    video = _video(db)

    with pytest.raises(ApiError):
        video_service.request_translate(db, video.id, "imagen-4.0-generate-001")


def test_video_khong_ton_tai_thi_404(db) -> None:
    with pytest.raises(NotFound):
        video_service.request_translate(db, uuid.uuid4(), "gemini-3.5-flash-lite")


def test_video_da_xoa_thi_404(db) -> None:
    import sqlalchemy as sa

    video = _video(db)
    video.deleted_at = sa.func.now()
    db.commit()

    with pytest.raises(NotFound):
        video_service.request_translate(db, video.id, "gemini-3.5-flash-lite")
