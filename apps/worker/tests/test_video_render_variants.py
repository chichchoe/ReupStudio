"""M4-WK-05 — hàm tầng ``tasks/`` chạm DB dùng cho ``render_variants_task``.

Theo review Task 6: cơ chế idempotent ở tầng DB (luật số 4 CLAUDE.md) không có
test nào khoá lại là rủi ro số 1 của task này. Đúng khuôn ``test_dedup_lookup.py``
và ``test_video_safe_area.py`` — SQLite trong RAM, không cần Postgres.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from reup_core.models import PlatformLimit, RenderVariant, Video
from reup_core.models.base import Base
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.pipeline.render import VariantPlan
from src.tasks.video import (
    _hook_text,
    _load_platform_limits,
    _reframe_mode,
    _target_platforms,
    _upsert_render_variant,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def add_video(session, *, process_config: dict | None = None) -> Video:
    video = Video(
        source_platform="douyin",
        source_video_id=uuid.uuid4().hex[:12],
        source_url="https://www.douyin.com/video/1",
        status="ready",
        duration_sec=200.0,
        flags={},
        process_config=process_config or {},
    )
    session.add(video)
    session.flush()
    return video


def add_platform_limit(session, platform: str, max_duration_sec: int) -> PlatformLimit:
    limit = PlatformLimit(
        platform=platform,
        max_duration_sec=max_duration_sec,
        max_title_len=100,
        max_desc_len=2000,
        max_hashtags=20,
        safe_daily_posts=10,
        aspect_ratios=["9:16"],
        safe_area={"top": 0.06, "bottom": 0.18, "left": 0.05, "right": 0.20},
    )
    session.add(limit)
    session.flush()
    return limit


def _plan(target: str = "tiktok", part_index: int = 1, part_total: int = 1) -> VariantPlan:
    return VariantPlan(
        target_platform=target,
        part_index=part_index,
        part_total=part_total,
        start=0.0,
        end=100.0,
    )


# --------------------------------------------------------------------------- #
# _target_platforms
# --------------------------------------------------------------------------- #


def _video(process_config: dict) -> SimpleNamespace:
    """Giả lập ``video``: ``_target_platforms`` chỉ đọc ``process_config``."""
    return SimpleNamespace(process_config=process_config)


def test_target_platforms_list_khong_rong_tra_ve_toan_bo_danh_sach() -> None:
    """Khác _target_platform (số ít, chỉ lấy phần tử đầu) — số nhiều lấy HẾT,
    vì một video sinh nhiều render_variants (luật số 8 CLAUDE.md)."""
    video = _video({"target_platforms": ["tiktok", "youtube", "facebook"]})
    assert _target_platforms(video) == ["tiktok", "youtube", "facebook"]


def test_target_platforms_chuoi_don_tra_ve_danh_sach_mot_phan_tu() -> None:
    video = _video({"target_platforms": "tiktok"})
    assert _target_platforms(video) == ["tiktok"]


def test_target_platforms_thieu_khoa_thi_mac_dinh_mot_nen_tang() -> None:
    assert _target_platforms(_video({})) == ["tiktok"]


def test_target_platforms_list_rong_thi_mac_dinh_mot_nen_tang() -> None:
    assert _target_platforms(_video({"target_platforms": []})) == ["tiktok"]


# --------------------------------------------------------------------------- #
# _reframe_mode / _hook_text (M4-WK-05b) — chỉ đọc process_config, không phán
# xét giá trị hợp lệ (render_variant ở tầng pipeline mới làm việc đó).
# --------------------------------------------------------------------------- #


def test_reframe_mode_thieu_khoa_mac_dinh_blur() -> None:
    assert _reframe_mode(_video({})) == "blur"


def test_reframe_mode_rong_mac_dinh_blur() -> None:
    assert _reframe_mode(_video({"reframe_mode": ""})) == "blur"


def test_reframe_mode_co_khoa_tra_nguyen_van_khong_chuan_hoa() -> None:
    """Giá trị lạ (VD gõ nhầm) vẫn được trả nguyên văn — không tự sửa/rơi về
    mặc định ở tầng tasks/, để render_variant ném lỗi rõ ràng (luật số 7)."""
    assert _reframe_mode(_video({"reframe_mode": "crop"})) == "crop"
    assert _reframe_mode(_video({"reframe_mode": "zoom"})) == "zoom"


def test_hook_text_thieu_khoa_tra_none() -> None:
    assert _hook_text(_video({})) is None


def test_hook_text_rong_tra_none() -> None:
    assert _hook_text(_video({"hook_text": ""})) is None


def test_hook_text_co_khoa_tra_dung_chuoi() -> None:
    assert _hook_text(_video({"hook_text": "Xem hết đừng bỏ lỡ!"})) == "Xem hết đừng bỏ lỡ!"


# --------------------------------------------------------------------------- #
# _load_platform_limits
# --------------------------------------------------------------------------- #


def test_load_platform_limits_tra_dung_max_duration_theo_tung_nen_tang(session) -> None:
    add_platform_limit(session, "tiktok", 180)
    add_platform_limit(session, "facebook", 90)
    add_platform_limit(session, "youtube", 0)  # nền tảng không nằm trong targets

    limits = _load_platform_limits(session, ["tiktok", "facebook"])

    assert limits == {"tiktok": 180, "facebook": 90}


def test_load_platform_limits_thieu_dong_thi_don_gian_vang_mat_trong_dict(session) -> None:
    """Không tự ném lỗi ở đây — plan_variants là nơi phát hiện thiếu và báo lỗi
    rõ ràng, tránh trùng lặp logic (xem docstring _load_platform_limits)."""
    add_platform_limit(session, "tiktok", 180)

    limits = _load_platform_limits(session, ["tiktok", "threads"])

    assert limits == {"tiktok": 180}
    assert "threads" not in limits


def test_load_platform_limits_danh_sach_rong_tra_dict_rong(session) -> None:
    add_platform_limit(session, "tiktok", 180)

    assert _load_platform_limits(session, []) == {}


# --------------------------------------------------------------------------- #
# _upsert_render_variant — cơ chế idempotent (rủi ro số 1 của task này)
# --------------------------------------------------------------------------- #


def test_upsert_lan_dau_tao_dung_mot_dong_moi(session) -> None:
    video = add_video(session)
    plan = _plan()

    row = _upsert_render_variant(
        session,
        video,
        plan,
        Path("/tmp/tiktok.p1.mp4"),
        {"target_platform": "tiktok"},
        1080,
        1920,
    )
    session.flush()

    rows = session.scalars(select(RenderVariant)).all()
    assert len(rows) == 1
    assert row.video_id == video.id
    assert row.target_platform == "tiktok"
    assert row.part_index == 1
    assert row.width == 1080
    assert row.height == 1920


def test_upsert_lan_hai_cung_khoa_khong_tao_dong_trung_chi_cap_nhat(session) -> None:
    """Đúng ràng buộc duy nhất (video_id, target_platform, part_index) — gọi
    lại với CÙNG khoá phải cập nhật dòng cũ, không tạo dòng thứ hai. Khẳng
    định bằng cách ĐẾM số dòng thật trong DB, không chỉ kiểm giá trị trả về."""

    video = add_video(session)
    plan = _plan()

    _upsert_render_variant(
        session,
        video,
        plan,
        Path("/tmp/tiktok.p1.mp4"),
        {"target_platform": "tiktok", "attempt": 1},
        1080,
        1920,
    )
    session.flush()
    assert len(session.scalars(select(RenderVariant)).all()) == 1

    # Chạy lại (giả lập render_variants_task chạy lần 2, VD sau khi retry) —
    # cùng (video_id, target_platform, part_index), kích thước file đổi.
    row2 = _upsert_render_variant(
        session,
        video,
        plan,
        Path("/tmp/tiktok.p1.mp4"),
        {"target_platform": "tiktok", "attempt": 2},
        720,
        1280,
    )
    session.flush()

    rows = session.scalars(select(RenderVariant)).all()
    assert len(rows) == 1, "phải cập nhật dòng cũ, không tạo dòng trùng"
    assert rows[0].id == row2.id
    assert rows[0].width == 720
    assert rows[0].height == 1280
    assert rows[0].config_snapshot["attempt"] == 2


def test_upsert_hai_nen_tang_khac_nhau_tao_hai_dong_rieng(session) -> None:
    """Khoá duy nhất phân biệt theo target_platform — hai nền tảng của cùng
    video không được coi là trùng nhau."""

    video = add_video(session)

    _upsert_render_variant(
        session,
        video,
        _plan("tiktok"),
        Path("/tmp/tiktok.p1.mp4"),
        {},
        None,
        None,
    )
    _upsert_render_variant(
        session,
        video,
        _plan("youtube"),
        Path("/tmp/youtube.p1.mp4"),
        {},
        None,
        None,
    )
    session.flush()

    rows = session.scalars(select(RenderVariant)).all()
    assert len(rows) == 2
    assert {r.target_platform for r in rows} == {"tiktok", "youtube"}


def test_upsert_hai_tap_cung_nen_tang_tao_hai_dong_rieng(session) -> None:
    """Khoá duy nhất còn phân biệt theo part_index — hai tập của cùng nền
    tảng không được ghi đè lên nhau."""

    video = add_video(session)

    _upsert_render_variant(
        session,
        video,
        _plan("tiktok", part_index=1, part_total=2),
        Path("/tmp/tiktok.p1.mp4"),
        {},
        None,
        None,
    )
    _upsert_render_variant(
        session,
        video,
        _plan("tiktok", part_index=2, part_total=2),
        Path("/tmp/tiktok.p2.mp4"),
        {},
        None,
        None,
    )
    session.flush()

    rows = session.scalars(select(RenderVariant)).all()
    assert len(rows) == 2
    assert {r.part_index for r in rows} == {1, 2}
