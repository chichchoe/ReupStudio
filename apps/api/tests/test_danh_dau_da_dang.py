"""Đánh dấu bằng tay những video đã tự đăng lên nền tảng.

Chặng đăng tự động (M5) chưa có: người dùng tải bản đã dựng về rồi đăng tay
lên TikTok/YouTube. Không có chỗ ghi lại việc đó thì video đã xong vẫn nằm mãi
trong danh sách việc đang tồn, và không ai trả lời được "cái này đăng YouTube
chưa".

Lưu vào ``flags["da_dang"]`` (nền tảng -> ngày đánh dấu) chứ KHÔNG dựng bảng
mới: M5 sẽ mang ``publish_channels``/``scheduled_posts`` thật, dựng bảng bây
giờ là dựng thứ M5 sẽ thay. Cùng lối với ``assign_channels`` — xem docstring
``bulk_action``.
"""

from __future__ import annotations

import uuid

import pytest
from reup_core.enums import VideoStatus
from reup_core.models import Video
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.errors import ApiError
from src.services import video_service


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _tao_video(db: Session, **kwargs) -> Video:
    defaults = {
        "source_platform": "douyin",
        "source_video_id": str(uuid.uuid4()),
        "source_url": "https://www.douyin.com/video/123",
        "status": VideoStatus.READY,
        "process_config": {},
    }
    defaults.update(kwargs)
    video = Video(**defaults)
    db.add(video)
    db.flush()
    return video


def test_danh_dau_xong_thi_chuyen_sang_posted(db) -> None:
    video = _tao_video(db)
    db.commit()

    ket_qua = video_service.bulk_action(
        db, [video.id], "mark_posted", {"platforms": ["tiktok", "youtube"]}
    )
    db.commit()

    assert ket_qua["affected"] == 1
    assert ket_qua["skipped"] == []
    sau = video_service.get_video(db, video.id)
    assert sau.status == VideoStatus.POSTED
    assert sorted(sau.flags["da_dang"]) == ["tiktok", "youtube"]


def test_danh_dau_lan_hai_thi_GOP_them_nen_tang(db) -> None:
    """Đăng TikTok hôm nay, YouTube mai — lần hai không được xoá lần đầu.

    Ghi đè là mất dấu nền tảng đã đăng, và người dùng đăng lại lần nữa lên
    đúng chỗ đã có bài.
    """
    video = _tao_video(db)
    db.commit()

    video_service.bulk_action(db, [video.id], "mark_posted", {"platforms": ["tiktok"]})
    db.commit()
    video_service.bulk_action(db, [video.id], "mark_posted", {"platforms": ["youtube"]})
    db.commit()

    sau = video_service.get_video(db, video.id)
    assert sorted(sau.flags["da_dang"]) == ["tiktok", "youtube"]


def test_moi_nen_tang_ghi_kem_ngay_danh_dau(db) -> None:
    """Không có ngày thì "đã đăng" là một dấu tích trống, không truy được."""
    video = _tao_video(db)
    db.commit()

    video_service.bulk_action(db, [video.id], "mark_posted", {"platforms": ["tiktok"]})
    db.commit()

    ngay = video_service.get_video(db, video.id).flags["da_dang"]["tiktok"]
    assert isinstance(ngay, str) and len(ngay) >= 10  # YYYY-MM-DD trở lên


def test_nen_tang_la_thi_TU_CHOI_ca_lo(db) -> None:
    """Gõ sai tên nền tảng mà vẫn ghi thì sổ ghi thành rác, không ai soát ra."""
    video = _tao_video(db)
    db.commit()

    with pytest.raises(ApiError, match="threads"):
        video_service.bulk_action(db, [video.id], "mark_posted", {"platforms": ["threads"]})

    assert video_service.get_video(db, video.id).status == VideoStatus.READY


def test_thieu_danh_sach_nen_tang_thi_tu_choi(db) -> None:
    video = _tao_video(db)
    db.commit()

    with pytest.raises(ApiError, match="platforms"):
        video_service.bulk_action(db, [video.id], "mark_posted", {})


def test_video_chua_render_xong_thi_bo_qua_KEM_LY_DO(db) -> None:
    """Chưa có bản dựng thì chưa thể đăng — bỏ qua âm thầm là người dùng tưởng
    đã đánh dấu cả lô."""
    xong = _tao_video(db, status=VideoStatus.READY)
    dang_chay = _tao_video(db, status=VideoStatus.RUNNING)
    db.commit()

    ket_qua = video_service.bulk_action(
        db, [xong.id, dang_chay.id], "mark_posted", {"platforms": ["tiktok"]}
    )
    db.commit()

    assert ket_qua["affected"] == 1
    assert len(ket_qua["skipped"]) == 1
    assert ket_qua["skipped"][0]["id"] == str(dang_chay.id)
    assert "running" in ket_qua["skipped"][0]["reason"]
    assert video_service.get_video(db, dang_chay.id).status == VideoStatus.RUNNING


def test_video_da_xep_lich_van_danh_dau_duoc(db) -> None:
    """`scheduled` là đã dựng xong và có lịch — đăng tay trước lịch là chuyện
    thường, không được chặn."""
    video = _tao_video(db, status=VideoStatus.SCHEDULED)
    db.commit()

    ket_qua = video_service.bulk_action(db, [video.id], "mark_posted", {"platforms": ["facebook"]})
    db.commit()

    assert ket_qua["affected"] == 1
    assert video_service.get_video(db, video.id).status == VideoStatus.POSTED
