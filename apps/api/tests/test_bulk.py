"""M2-BE-03 — bulk action: approve / delete / retry / apply_preset / assign_channels.

Chạy trên SQLite trong RAM, gọi thẳng service (không qua HTTP).
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
from src.services import preset_service, video_service


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
        "status": VideoStatus.REVIEW,
        "process_config": {},
    }
    defaults.update(kwargs)
    video = Video(**defaults)
    db.add(video)
    db.flush()
    return video


def test_approve_10_video_review_thanh_ready(db) -> None:
    videos = [_tao_video(db) for _ in range(10)]
    db.commit()
    ids = [v.id for v in videos]

    result = video_service.bulk_action(db, ids, "approve")
    db.commit()

    assert result["affected"] == 10
    assert result["skipped"] == []
    for vid in ids:
        video = video_service.get_video(db, vid)
        assert video.status == VideoStatus.READY
        assert video.flags["approved"] is True


def test_apply_preset_tron_config_dung_khoa_moi_de_len_khoa_cu_con_nguyen(db) -> None:
    preset = preset_service.create_preset(
        db,
        kind="process",
        name="Preset xử lý",
        config={"voice": "vi-female-1", "burn_sub": True},
    )
    video = _tao_video(
        db,
        process_config={"burn_sub": False, "watermark_pos": "top_left"},
    )
    db.commit()

    result = video_service.bulk_action(
        db, [video.id], "apply_preset", {"preset_id": str(preset.id)}
    )
    db.commit()

    assert result["affected"] == 1
    refreshed = video_service.get_video(db, video.id)
    # Khoá mới từ preset ghi đè khoá cùng tên.
    assert refreshed.process_config["burn_sub"] is True
    assert refreshed.process_config["voice"] == "vi-female-1"
    # Khoá cũ không liên quan tới preset vẫn còn nguyên.
    assert refreshed.process_config["watermark_pos"] == "top_left"


def test_apply_preset_kind_filter_bi_tu_choi(db) -> None:
    preset = preset_service.create_preset(db, kind="filter", name="Lọc A")
    video = _tao_video(db)
    db.commit()

    with pytest.raises(ApiError):
        video_service.bulk_action(db, [video.id], "apply_preset", {"preset_id": str(preset.id)})


def test_apply_preset_khong_ton_tai_nem_notfound(db) -> None:
    video = _tao_video(db)
    db.commit()

    with pytest.raises(NotFound):
        video_service.bulk_action(db, [video.id], "apply_preset", {"preset_id": str(uuid.uuid4())})


def test_assign_channels_ghi_dung_target_channel_ids(db) -> None:
    video = _tao_video(db)
    db.commit()
    kenh_a = str(uuid.uuid4())
    kenh_b = str(uuid.uuid4())

    result = video_service.bulk_action(
        db, [video.id], "assign_channels", {"channel_ids": [kenh_a, kenh_b]}
    )
    db.commit()

    assert result["affected"] == 1
    refreshed = video_service.get_video(db, video.id)
    assert refreshed.process_config["target_channel_ids"] == [kenh_a, kenh_b]


def test_id_khong_ton_tai_va_video_da_xoa_mem_roi_vao_skipped(db) -> None:
    con_song = _tao_video(db)
    da_xoa = _tao_video(db)
    db.commit()
    video_service.soft_delete(db, da_xoa.id)
    db.commit()
    id_khong_ton_tai = uuid.uuid4()

    result = video_service.bulk_action(db, [con_song.id, da_xoa.id, id_khong_ton_tai], "approve")
    db.commit()

    assert result["affected"] == 1
    assert len(result["skipped"]) == 2
    lys_do = {item["id"]: item["reason"] for item in result["skipped"]}
    assert lys_do[str(da_xoa.id)] == "Video đã bị xoá mềm"
    assert lys_do[str(id_khong_ton_tai)] == "Không tìm thấy video"
    # video còn sống không bị ảnh hưởng bởi id lỗi trong cùng lệnh
    assert video_service.get_video(db, con_song.id).status == VideoStatus.READY


def test_approve_sai_trang_thai_roi_vao_skipped(db) -> None:
    video = _tao_video(db, status=VideoStatus.QUEUED)
    db.commit()

    result = video_service.bulk_action(db, [video.id], "approve")
    db.commit()

    assert result["affected"] == 0
    assert len(result["skipped"]) == 1
    assert "Sai trạng thái" in result["skipped"][0]["reason"]
