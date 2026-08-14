"""Pipeline dừng lại sau bước nhận dạng, chờ người dùng chọn AI rồi mới dịch.

Chốt ngày 2026-08-14 theo yêu cầu chủ dự án. Dừng ở ĐÚNG chỗ này chứ không sớm
hơn vì lúc đó đã biết video có bao nhiêu câu thoại — thông tin quyết định việc
chọn model: 672 câu thì chọn model hạn mức cao (gemini-3.5-flash-lite: 500
lượt/ngày), 50 câu thì chọn model chất lượng cao.

Hai nửa:
    tự động   tải → probe → nhận dạng  →  DỪNG (status = review)
    người bấm dịch → chuẩn hoá phụ đề → render

Chặng M7 (luồng tự động) sau này cần bỏ qua chỗ dừng, nên có cờ
``auto_translate`` trong ``process_config``: bật thì chạy thẳng như trước.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from reup_core.enums import (
    M1_STEPS_SAU_DICH,
    M1_STEPS_TRUOC_DICH,
    PipelineStep,
    VideoStatus,
)
from reup_core.models import Video
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tasks import video as mod


def test_hai_nua_gop_lai_dung_bang_pipeline_cu() -> None:
    """Không được đánh rơi hay lặp bước nào khi tách."""
    from reup_core.enums import M1_STEPS

    assert M1_STEPS_TRUOC_DICH + M1_STEPS_SAU_DICH == M1_STEPS


def test_nua_dau_dung_ngay_sau_nhan_dang() -> None:
    assert M1_STEPS_TRUOC_DICH[-1] is PipelineStep.TRANSCRIBE
    assert PipelineStep.TRANSLATE not in M1_STEPS_TRUOC_DICH


def test_nua_sau_bat_dau_tu_buoc_dich() -> None:
    assert M1_STEPS_SAU_DICH[0] is PipelineStep.TRANSLATE


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return scope


def _video(scope, **kw) -> Video:
    with scope() as session:
        v = Video(
            source_platform="douyin",
            source_video_id=uuid.uuid4().hex[:12],
            source_url="https://www.douyin.com/video/1",
            status=VideoStatus.RUNNING.value,
            flags={},
            process_config=kw.get("process_config", {}),
        )
        session.add(v)
        session.commit()
        session.refresh(v)
        return v


def test_nhan_dang_xong_thi_chuyen_sang_cho_duyet(db, monkeypatch) -> None:
    """Đây là chỗ người dùng nhìn thấy video trong tab "Chờ dịch"."""
    v = _video(db)
    with db() as session:
        video = session.get(Video, v.id)
        mod._dung_cho_chon_ai(session, video)
        session.commit()

    with db() as session:
        assert session.get(Video, v.id).status == VideoStatus.REVIEW.value


def test_bat_auto_translate_thi_khong_dung(db) -> None:
    """M7 (luồng tự động) cần chạy một mạch, không có ai ngồi bấm nút."""
    v = _video(db, process_config={"auto_translate": True})
    with db() as session:
        video = session.get(Video, v.id)
        da_dung = mod._dung_cho_chon_ai(session, video)
        session.commit()

    assert da_dung is False
    with db() as session:
        assert session.get(Video, v.id).status != VideoStatus.REVIEW.value


def test_khong_bat_co_thi_mac_dinh_la_dung(db) -> None:
    """Mặc định phải DỪNG — người dùng chọn AI là đường chính, chạy thẳng là
    ngoại lệ phải khai báo."""
    v = _video(db)
    with db() as session:
        video = session.get(Video, v.id)
        assert mod._dung_cho_chon_ai(session, video) is True


def test_model_lay_tu_process_config_truoc_roi_moi_den_mac_dinh(db) -> None:
    v = _video(db, process_config={"llm_model": "gemini-3.5-flash-lite"})
    with db() as session:
        assert mod._llm_model(session.get(Video, v.id)) == "gemini-3.5-flash-lite"


def test_khong_chon_model_thi_dung_mac_dinh_trong_cau_hinh(db) -> None:
    v = _video(db)
    with db() as session:
        assert mod._llm_model(session.get(Video, v.id)) is None
