"""M2-WK-02 — tra cứu bản trùng trong DB.

Chạy trên SQLite trong RAM: chỉ kiểm logic chọn ứng viên và điều kiện lọc, không
kiểm gì đặc thù Postgres.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from reup_core.enums import VideoStatus
from reup_core.models import Video
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.tasks.video import _find_duplicate, _mark_duplicate

#: pHash 4 khung, mỗi khung 16 hex.
PHASH_A = "a1b2c3d4e5f60718" * 4
PHASH_B = "0f1e2d3c4b5a6978" * 4
MD5_A = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture(autouse=True)
def _khong_goi_redis(monkeypatch):
    monkeypatch.setattr("src.tasks.video.prog.status_changed", lambda *a, **k: None)


def add_video(
    session,
    *,
    md5: str | None = None,
    phash: str | None = None,
    status: VideoStatus = VideoStatus.READY,
    deleted_at: dt.datetime | None = None,
) -> Video:
    video = Video(
        source_platform="douyin",
        source_video_id=uuid.uuid4().hex[:12],
        source_url="https://www.douyin.com/video/1",
        status=status,
        md5=md5,
        phash=phash,
        flags={},
        process_config={},
        deleted_at=deleted_at,
    )
    session.add(video)
    session.flush()
    return video


def _flip_bits(phash: str, count: int) -> str:
    """Đổi ``count`` bit đầu của pHash — giả lập bản mã hoá lại."""
    value = int(phash, 16) ^ ((1 << count) - 1)
    return f"{value:0{len(phash)}x}"


def test_md5_giong_het_thi_bat_duoc(session) -> None:
    goc = add_video(session, md5=MD5_A, phash=PHASH_A)
    moi = add_video(session, md5=MD5_A, phash=PHASH_A, status=VideoStatus.RUNNING)

    found = _find_duplicate(session, moi)
    assert found is not None
    assert found[0].id == goc.id
    assert found[1] == "md5"


def test_khac_md5_nhung_phash_gan_thi_van_bat_duoc(session) -> None:
    """Bản mã hoá lại: từng byte khác nhau nên md5 vô dụng, pHash phải cứu."""
    goc = add_video(session, md5=MD5_A, phash=PHASH_A)
    moi = add_video(
        session, md5="f" * 32, phash=_flip_bits(PHASH_A, 3), status=VideoStatus.RUNNING
    )

    found = _find_duplicate(session, moi)
    assert found is not None
    assert found[0].id == goc.id
    assert found[1] == "phash"


def test_phash_khac_han_thi_khong_coi_la_trung(session) -> None:
    add_video(session, md5=MD5_A, phash=PHASH_A)
    moi = add_video(session, md5="f" * 32, phash=PHASH_B, status=VideoStatus.RUNNING)

    assert _find_duplicate(session, moi) is None


def test_khong_co_hash_thi_khong_bao_gio_trung(session) -> None:
    add_video(session, md5=MD5_A, phash=PHASH_A)
    moi = add_video(session, md5=None, phash=None, status=VideoStatus.RUNNING)

    assert _find_duplicate(session, moi) is None


def test_bo_qua_video_da_xoa_mem(session) -> None:
    add_video(session, md5=MD5_A, phash=PHASH_A, deleted_at=dt.datetime(2026, 1, 1))
    moi = add_video(session, md5=MD5_A, phash=PHASH_A, status=VideoStatus.RUNNING)

    assert _find_duplicate(session, moi) is None


def test_ban_trung_luon_tro_ve_ban_goc_khong_tro_vao_ban_da_skip(session) -> None:
    goc = add_video(session, md5=MD5_A, phash=PHASH_A)
    truoc = add_video(session, md5=MD5_A, phash=PHASH_A, status=VideoStatus.RUNNING)
    _mark_duplicate(truoc, goc, "md5")
    session.flush()

    sau = add_video(session, md5=MD5_A, phash=PHASH_A, status=VideoStatus.RUNNING)
    found = _find_duplicate(session, sau)

    assert found is not None
    assert found[0].id == goc.id  # không phải `truoc`


def test_danh_dau_trung_thi_dung_pipeline_va_ghi_lai_ban_goc(session) -> None:
    goc = add_video(session, md5=MD5_A, phash=PHASH_A)
    moi = add_video(session, md5=MD5_A, phash=PHASH_A, status=VideoStatus.RUNNING)
    moi.current_step = "download"

    _mark_duplicate(moi, goc, "md5")
    session.flush()

    assert moi.status == VideoStatus.SKIPPED
    assert moi.current_step is None
    assert moi.flags["duplicate_of"] == str(goc.id)
    assert moi.flags["duplicate_reason"] == "md5"


def test_khong_tu_coi_minh_la_ban_trung_cua_chinh_minh(session) -> None:
    """Chạy lại bước download (idempotent) không được tự đánh dấu trùng."""
    video = add_video(session, md5=MD5_A, phash=PHASH_A, status=VideoStatus.RUNNING)

    assert _find_duplicate(session, video) is None
