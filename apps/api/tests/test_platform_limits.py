"""M4-BE-01 — bảng ``platform_limits``: seed, list, update, validate.

Chạy trên SQLite trong RAM, gọi thẳng service (không qua HTTP). Vì SQLite
không chạy migration Alembic, test tự seed 5 dòng giống migration ``0006``.

``max_duration_sec`` seed bằng ``0`` (KHÔNG giới hạn thời lượng — người dùng
tự xem lại video trước khi đăng), khác với các cột số khác luôn phải ``> 0``.
"""

from __future__ import annotations

import pytest
from reup_core.models import PlatformLimit
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.errors import ApiError, NotFound
from src.services import platform_limit_service

_SEED = [
    {
        "platform": "tiktok",
        "max_duration_sec": 0,
        "max_title_len": 150,
        "max_desc_len": 2200,
        "max_hashtags": 30,
        "safe_daily_posts": 3,
        "aspect_ratios": ["9:16"],
        "safe_area": {"top": 0.06, "bottom": 0.18, "left": 0.05, "right": 0.20},
    },
    {
        "platform": "youtube",
        "max_duration_sec": 0,
        "max_title_len": 100,
        "max_desc_len": 5000,
        "max_hashtags": 15,
        "safe_daily_posts": 5,
        "aspect_ratios": ["9:16"],
        "safe_area": {"top": 0.06, "bottom": 0.14, "left": 0.05, "right": 0.12},
    },
    {
        "platform": "facebook",
        "max_duration_sec": 0,
        "max_title_len": 255,
        "max_desc_len": 2200,
        "max_hashtags": 30,
        "safe_daily_posts": 3,
        "aspect_ratios": ["9:16"],
        "safe_area": {"top": 0.08, "bottom": 0.20, "left": 0.05, "right": 0.18},
    },
    {
        "platform": "instagram",
        "max_duration_sec": 0,
        "max_title_len": 125,
        "max_desc_len": 2200,
        "max_hashtags": 30,
        "safe_daily_posts": 3,
        "aspect_ratios": ["9:16"],
        "safe_area": {"top": 0.08, "bottom": 0.22, "left": 0.05, "right": 0.20},
    },
    {
        "platform": "zalo",
        "max_duration_sec": 0,
        "max_title_len": 120,
        "max_desc_len": 1500,
        "max_hashtags": 20,
        "safe_daily_posts": 3,
        "aspect_ratios": ["9:16"],
        "safe_area": {"top": 0.06, "bottom": 0.16, "left": 0.05, "right": 0.15},
    },
]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(PlatformLimit(**row) for row in _SEED)
        session.commit()
        yield session


def test_liet_ke_tra_du_5_nen_tang_sau_khi_seed(db) -> None:
    limits = platform_limit_service.list_limits(db)

    assert len(limits) == 5
    assert {limit.platform for limit in limits} == {
        "tiktok",
        "youtube",
        "facebook",
        "instagram",
        "zalo",
    }


def test_seed_max_duration_sec_bang_0_nghia_la_khong_gioi_han(db) -> None:
    limits = platform_limit_service.list_limits(db)

    assert all(limit.max_duration_sec == 0 for limit in limits)


def test_update_limit_doi_duoc_max_duration_sec_va_safe_area(db) -> None:
    limit = platform_limit_service.update_limit(
        db,
        "tiktok",
        {
            "max_duration_sec": 180,
            "safe_area": {"top": 0.10, "bottom": 0.10, "left": 0.05, "right": 0.05},
        },
    )
    db.commit()
    db.refresh(limit)

    assert limit.max_duration_sec == 180
    assert limit.safe_area == {"top": 0.10, "bottom": 0.10, "left": 0.05, "right": 0.05}


def test_update_limit_dat_max_duration_sec_bang_0_duoc_chap_nhan(db) -> None:
    """0 = không giới hạn — người dùng có thể tắt giới hạn bất kỳ lúc nào."""
    platform_limit_service.update_limit(db, "tiktok", {"max_duration_sec": 180})
    db.commit()

    limit = platform_limit_service.update_limit(db, "tiktok", {"max_duration_sec": 0})
    db.commit()
    db.refresh(limit)

    assert limit.max_duration_sec == 0


def test_safe_area_thieu_khoa_bi_tu_choi(db) -> None:
    with pytest.raises(ApiError):
        platform_limit_service.update_limit(
            db, "tiktok", {"safe_area": {"top": 0.06, "bottom": 0.18, "left": 0.05}}
        )


def test_safe_area_gia_tri_am_bi_tu_choi(db) -> None:
    with pytest.raises(ApiError):
        platform_limit_service.update_limit(
            db,
            "tiktok",
            {"safe_area": {"top": -0.01, "bottom": 0.18, "left": 0.05, "right": 0.20}},
        )


def test_safe_area_gia_tri_lon_hon_bang_0_5_bi_tu_choi(db) -> None:
    with pytest.raises(ApiError):
        platform_limit_service.update_limit(
            db,
            "tiktok",
            {"safe_area": {"top": 0.5, "bottom": 0.18, "left": 0.05, "right": 0.20}},
        )


def test_safe_area_top_cong_bottom_qua_1_bi_tu_choi(db) -> None:
    # Vì mỗi giá trị đã bị chặn < 0.5, muốn top + bottom >= 1 thì ít nhất một
    # giá trị phải >= 0.5 — trường hợp này cũng vi phạm khoảng riêng của nó,
    # nhưng vẫn phải bị từ chối vì bất biến "còn chỗ đặt phụ đề" là điều
    # service phải đảm bảo, dù bị chặn ở bước nào.
    with pytest.raises(ApiError):
        platform_limit_service.update_limit(
            db,
            "tiktok",
            {"safe_area": {"top": 0.5, "bottom": 0.6, "left": 0.05, "right": 0.05}},
        )


def test_max_duration_sec_am_bi_tu_choi(db) -> None:
    with pytest.raises(ApiError):
        platform_limit_service.update_limit(db, "tiktok", {"max_duration_sec": -10})


@pytest.mark.parametrize(
    "field", ["max_title_len", "max_desc_len", "max_hashtags", "safe_daily_posts"]
)
def test_cac_cot_so_khac_dat_0_bi_tu_choi(db, field: str) -> None:
    """Khác ``max_duration_sec``, các cột số còn lại KHÔNG được là 0."""
    with pytest.raises(ApiError):
        platform_limit_service.update_limit(db, "tiktok", {field: 0})


def test_nen_tang_khong_ton_tai_thi_nem_notfound(db) -> None:
    with pytest.raises(NotFound):
        platform_limit_service.get_limit(db, "twitter")

    with pytest.raises(NotFound):
        platform_limit_service.update_limit(db, "twitter", {"max_duration_sec": 30})
