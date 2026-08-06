"""M2-WK-02 — lớp chống trùng thứ nhất: dán lại link cũ thì trả về video cũ.

Chạy trên SQLite trong RAM, gọi thẳng service (không qua HTTP).
"""

from __future__ import annotations

import pytest
from reup_core.enums import VideoStatus
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.services import video_service

LINK = "https://www.douyin.com/video/7395012345678901234"
LINK_KHAC = "https://www.douyin.com/video/7000000000000000000"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_link_moi_thi_tao_ban_ghi(db) -> None:
    result = video_service.create_from_links(db, [LINK])

    assert result["created"] == 1
    assert result["skipped_duplicate"] == 0
    assert result["duplicate_ids"] == []


def test_dan_lai_link_cu_thi_tra_ve_video_cu_khong_tao_moi(db) -> None:
    first = video_service.create_from_links(db, [LINK])
    db.commit()

    second = video_service.create_from_links(db, [LINK])

    assert second["created"] == 0
    assert second["video_ids"] == []
    assert second["skipped_duplicate"] == 1
    assert second["duplicate_ids"] == first["video_ids"]


def test_dan_lan_lon_link_cu_va_link_moi(db) -> None:
    first = video_service.create_from_links(db, [LINK])
    db.commit()

    result = video_service.create_from_links(db, [LINK, LINK_KHAC, "không phải link"])

    assert result["created"] == 1
    assert result["duplicate_ids"] == first["video_ids"]
    assert result["invalid"] == ["không phải link"]


def test_video_cu_giu_nguyen_trang_thai_khi_dan_lai(db) -> None:
    created = video_service.create_from_links(db, [LINK])
    db.commit()
    video = video_service.get_video(db, created["video_ids"][0])
    video.status = VideoStatus.READY
    db.commit()

    video_service.create_from_links(db, [LINK])

    assert video_service.get_video(db, created["video_ids"][0]).status == VideoStatus.READY
