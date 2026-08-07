"""M4-BE-01 — bảng ``platform_limits``: seed, list, update, validate.

Chạy trên SQLite trong RAM, gọi thẳng service (không qua HTTP). Vì SQLite
không chạy migration Alembic, test tự seed 5 dòng giống migration ``0006``.

``max_duration_sec`` seed bằng ``0`` (KHÔNG giới hạn thời lượng — người dùng
tự xem lại video trước khi đăng), khác với các cột số khác luôn phải ``> 0``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from reup_core.models import PlatformLimit
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db import get_db
from src.errors import ApiError, NotFound, api_error_handler
from src.routers import platform_limits as platform_limits_router
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


@pytest.fixture
def http_client():
    """TestClient tối giản chỉ gắn router platform-limits, seed qua SQLite RAM.

    Dùng để kiểm hành vi Ở TẦNG HTTP thật: một ``TypeError``/``IntegrityError``
    không bắt được sẽ lộ ra thành 500 ở tầng này, khác với gọi thẳng service
    (nơi ``pytest.raises`` chỉ cần đúng loại exception, không kiểm status code).
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        session.add_all(PlatformLimit(**row) for row in _SEED)
        session.commit()

    def override_get_db():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(platform_limits_router.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client


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


def test_safe_area_tong_top_bottom_vuot_qua_nguong_bi_tu_choi(db) -> None:
    """Ca THẬT SỰ chạm nhánh tổng: mỗi khoá hợp lệ riêng lẻ (< 0.5) nhưng tổng
    dọc 0.7 > 0.6 — chỉ còn 30% khung hình để đặt phụ đề, không đủ dùng.
    """
    with pytest.raises(ApiError):
        platform_limit_service.update_limit(
            db,
            "tiktok",
            {"safe_area": {"top": 0.35, "bottom": 0.35, "left": 0.05, "right": 0.20}},
        )


def test_safe_area_tong_top_bottom_bang_dung_nguong_duoc_chap_nhan(db) -> None:
    """Sát ngưỡng: tổng dọc đúng 0.6 (chừa đúng 40%) vẫn được chấp nhận."""
    limit = platform_limit_service.update_limit(
        db,
        "tiktok",
        {"safe_area": {"top": 0.30, "bottom": 0.30, "left": 0.05, "right": 0.05}},
    )
    db.commit()
    db.refresh(limit)

    assert limit.safe_area == {"top": 0.30, "bottom": 0.30, "left": 0.05, "right": 0.05}


def test_safe_area_tong_left_right_vuot_qua_nguong_bi_tu_choi(db) -> None:
    with pytest.raises(ApiError):
        platform_limit_service.update_limit(
            db,
            "tiktok",
            {"safe_area": {"top": 0.05, "bottom": 0.20, "left": 0.35, "right": 0.35}},
        )


def test_safe_area_tong_left_right_bang_dung_nguong_duoc_chap_nhan(db) -> None:
    limit = platform_limit_service.update_limit(
        db,
        "tiktok",
        {"safe_area": {"top": 0.05, "bottom": 0.05, "left": 0.30, "right": 0.30}},
    )
    db.commit()
    db.refresh(limit)

    assert limit.safe_area == {"top": 0.05, "bottom": 0.05, "left": 0.30, "right": 0.30}


def test_safe_area_null_tuong_minh_bi_tu_choi_khong_phai_typeerror(db) -> None:
    """Client PATCH ``{"safe_area": null}`` phải ra lỗi nghiệp vụ rõ ràng,
    KHÔNG phải ``TypeError`` (``key not in None``) làm sập 500 ở tầng HTTP.
    """
    with pytest.raises(ApiError):
        platform_limit_service.update_limit(db, "tiktok", {"safe_area": None})


def test_aspect_ratios_null_tuong_minh_bi_tu_choi_khong_phai_integrityerror(db) -> None:
    """Client PATCH ``{"aspect_ratios": null}`` phải ra lỗi nghiệp vụ rõ ràng,
    KHÔNG phải ``IntegrityError`` (ghi NULL vào cột NOT NULL) làm sập 500.
    """
    with pytest.raises(ApiError):
        platform_limit_service.update_limit(db, "tiktok", {"aspect_ratios": None})


def test_http_patch_safe_area_null_tra_400_khong_phai_500(http_client) -> None:
    resp = http_client.patch("/api/v1/platform-limits/tiktok", json={"safe_area": None})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"


def test_http_patch_aspect_ratios_null_tra_400_khong_phai_500(http_client) -> None:
    resp = http_client.patch("/api/v1/platform-limits/tiktok", json={"aspect_ratios": None})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"


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
