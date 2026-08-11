"""M4-WK-02 — chọn nền tảng đích và đọc vùng an toàn từ ``platform_limits``.

Bổ sung theo code review: ``_target_platform``/``_load_safe_area``
(``src/tasks/video.py``) quyết định phụ đề nằm ở đâu trên video thật — chọn
nhầm nhánh KHÔNG làm crash, chỉ đặt sai chỗ (lỗi thầm lặng). Theo đúng khuôn
``test_dedup_lookup.py``: SQLite trong RAM, không cần Postgres.

``_target_platform`` chỉ đọc ``video.process_config`` (không chạm DB) nên
test bằng object giả lập nhẹ thay vì dựng cả bản ghi ``Video``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from reup_core.models.base import Base
from reup_core.models.platform_limit import PlatformLimit
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.errors import PlatformLimitNotFoundError
from src.pipeline.shortform.safe_area import SafeArea
from src.tasks.video import _load_safe_area, _target_platform

TIKTOK_SAFE_AREA = {"top": 0.06, "bottom": 0.18, "left": 0.05, "right": 0.20}


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _video(process_config: dict) -> SimpleNamespace:
    """Giả lập ``video``: ``_target_platform`` chỉ đọc thuộc tính ``process_config``."""
    return SimpleNamespace(process_config=process_config)


def add_platform_limit(session, platform: str, safe_area: dict) -> PlatformLimit:
    limit = PlatformLimit(
        platform=platform,
        max_duration_sec=0,
        max_title_len=100,
        max_desc_len=2000,
        max_hashtags=20,
        safe_daily_posts=10,
        aspect_ratios=["9:16"],
        safe_area=safe_area,
    )
    session.add(limit)
    session.flush()
    return limit


# --------------------------------------------------------------------------- #
# _target_platform
# --------------------------------------------------------------------------- #


def test_target_platform_list_khong_rong_thi_lay_phan_tu_dau() -> None:
    """Quy tắc đã cài: M4 chưa tách render_variants theo từng nền tảng (luật số 8
    CLAUDE.md là việc của milestone sau) nên chỉ dùng MỘT nền tảng đại diện —
    phần tử ĐẦU của ``target_platforms``."""
    video = _video({"target_platforms": ["youtube", "tiktok"]})
    assert _target_platform(video) == "youtube"


def test_target_platform_chuoi_don_thi_dung_luon() -> None:
    """target_platforms có thể được cấu hình như chuỗi đơn (không phải list)."""
    video = _video({"target_platforms": "tiktok"})
    assert _target_platform(video) == "tiktok"


def test_target_platform_thieu_khoa_thi_mac_dinh_tiktok() -> None:
    video = _video({})
    assert _target_platform(video) == "tiktok"


def test_target_platform_list_rong_thi_mac_dinh_tiktok() -> None:
    video = _video({"target_platforms": []})
    assert _target_platform(video) == "tiktok"


# --------------------------------------------------------------------------- #
# _load_safe_area
# --------------------------------------------------------------------------- #


def test_load_safe_area_khong_co_dong_thi_bao_loi_ro_rang(session) -> None:
    """Thiếu dòng platform_limits phải ném lỗi rõ, KHÔNG âm thầm dùng mặc định."""
    with pytest.raises(PlatformLimitNotFoundError, match="threads"):
        _load_safe_area(session, "threads")


def test_load_safe_area_co_dong_thi_tra_dung_4_gia_tri_da_seed(session) -> None:
    add_platform_limit(session, "tiktok", TIKTOK_SAFE_AREA)

    assert _load_safe_area(session, "tiktok") == SafeArea(
        top=0.06, bottom=0.18, left=0.05, right=0.20
    )
