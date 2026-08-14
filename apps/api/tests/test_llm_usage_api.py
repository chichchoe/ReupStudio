"""Endpoint ``GET /api/v1/llm/usage`` — "hôm nay: 143 lượt · 2,1M token".

Số liệu cộng từ bảng ``cost_logs``. Gemini KHÔNG trả header hạn mức nào (đo
ngày 2026-08-14), nên đây là NGUỒN DUY NHẤT để người dùng biết mình còn bao
nhiêu lượt trước khi bị chặn — sai số ở đây là người dùng chạy một lô dịch dài
rồi hỏng giữa chừng.

Worker có bộ đếm tương tự (``apps/worker/src/tasks/cost.py``) nhưng hai app độc
lập, không import chéo được: truy vấn viết lại ở tầng service của API. Bộ test
này vì thế phải khoá cả những chi tiết tưởng vụn — mốc thời gian và bộ lọc
``service`` — vì không có bài test chung nào bắt được lệch giữa hai bên.

Chạy trên SQLite trong RAM, không cần Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from reup_core.models import CostLog
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db import get_db
from src.errors import ApiError, api_error_handler
from src.routers import llm as llm_router
from src.services import llm_usage_service


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _cau_hinh(monkeypatch, **kw):
    """Cấu hình cô lập khỏi ``.env`` thật của máy đang chạy."""
    from src.config import Settings

    monkeypatch.setattr(llm_usage_service, "get_settings", lambda: Settings(_env_file=None, **kw))


def _them(
    session,
    *,
    so_dong: int = 1,
    token: float = 0.0,
    tien: float = 0.0,
    truoc_bao_lau: timedelta = timedelta(0),
    service: str = "llm_translate",
    unit: str = "token",
) -> None:
    khi = datetime.now(UTC) - truoc_bao_lau
    for _ in range(so_dong):
        session.add(
            CostLog(
                service=service,
                model="gemini-3.5-flash-lite",
                unit=unit,
                quantity=token,
                cost_usd=tien,
                created_at=khi,
            )
        )
    session.flush()


# --- Đếm lượt ----------------------------------------------------------


def test_dem_luot_trong_60_giay_gan_nhat(db, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    _them(db, so_dong=3)
    _them(db, so_dong=2, truoc_bao_lau=timedelta(seconds=30))
    _them(db, so_dong=5, truoc_bao_lau=timedelta(minutes=5))

    assert llm_usage_service.tom_tat(db).requests_last_min == 5


def test_dem_luot_trong_24_gio_gan_nhat(db, monkeypatch) -> None:
    """Trần của Gemini tính theo NGÀY TRƯỢT tính từ lúc gọi, không reset lúc
    nửa đêm — đếm theo ngày lịch sẽ báo còn hạn mức trong khi thật ra hết."""
    _cau_hinh(monkeypatch)
    _them(db, so_dong=4, truoc_bao_lau=timedelta(hours=23))
    _them(db, so_dong=7, truoc_bao_lau=timedelta(hours=25))

    assert llm_usage_service.tom_tat(db).requests_last_day == 4


def test_bo_qua_dich_vu_khac_khi_dem(db, monkeypatch) -> None:
    """``cost_logs`` dùng chung cho TTS, GPU, băng thông. Trần hạn mức LLM chỉ
    tính lượt gọi LLM — cộng lẫn sẽ báo hết hạn mức trong khi vẫn còn."""
    _cau_hinh(monkeypatch)
    _them(db, so_dong=2)
    _them(db, so_dong=9, service="tts", unit="giây")

    tom_tat = llm_usage_service.tom_tat(db)

    assert tom_tat.requests_last_min == 2
    assert tom_tat.requests_last_day == 2


def test_chua_co_du_lieu_thi_tra_ve_khong(db, monkeypatch) -> None:
    _cau_hinh(monkeypatch)

    tom_tat = llm_usage_service.tom_tat(db)

    assert tom_tat.requests_last_min == 0
    assert tom_tat.requests_last_day == 0
    assert tom_tat.tokens_last_day == 0
    assert tom_tat.cost_usd_this_month == 0.0


# --- Token -------------------------------------------------------------


def test_tong_token_trong_24_gio(db, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    _them(db, so_dong=2, token=1000)
    _them(db, so_dong=1, token=500, truoc_bao_lau=timedelta(hours=10))
    _them(db, so_dong=1, token=9999, truoc_bao_lau=timedelta(hours=30))

    assert llm_usage_service.tom_tat(db).tokens_last_day == 2500


def test_token_tra_ve_kieu_so_nguyen(db, monkeypatch) -> None:
    """Cột ``quantity`` là Float cho dùng chung với TTS (đơn vị giây), nhưng
    token thì luôn nguyên — giao diện hiện "2,1M token", không phải "2100000.0"."""
    _cau_hinh(monkeypatch)
    _them(db, token=1234)

    tokens = llm_usage_service.tom_tat(db).tokens_last_day

    assert isinstance(tokens, int)
    assert tokens == 1234


def test_khong_cong_don_vi_khac_vao_tong_token(db, monkeypatch) -> None:
    """Dòng TTS đo bằng GIÂY; cộng thẳng ``quantity`` vào ô token là sai đơn vị."""
    _cau_hinh(monkeypatch)
    _them(db, token=100)
    _them(db, token=3600, service="tts", unit="giây")

    assert llm_usage_service.tom_tat(db).tokens_last_day == 100


# --- Tiền --------------------------------------------------------------


def test_tien_tinh_tu_dau_thang_utc(db, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    dau_thang = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _them(db, so_dong=2, tien=0.5)
    _them(db, tien=99.0, truoc_bao_lau=datetime.now(UTC) - dau_thang + timedelta(days=1))

    assert llm_usage_service.tom_tat(db).cost_usd_this_month == pytest.approx(1.0)


def test_tien_gom_ca_luot_cu_hon_24_gio_trong_thang(db, monkeypatch) -> None:
    """Trần TIỀN tính theo tháng, không theo ngày — bỏ sót lượt cũ trong tháng
    thì con số hiện ra luôn thấp hơn số thật và người dùng vượt trần lúc nào
    không hay."""
    _cau_hinh(monkeypatch)
    # Lùi 3 ngày nhưng vẫn trong tháng: chỉ chạy được khi hôm nay >= mùng 4,
    # nên tính mốc từ đầu tháng để bài test đúng vào mọi ngày trong tháng.
    dau_thang = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    trong_thang = min(timedelta(days=3), datetime.now(UTC) - dau_thang)
    _them(db, tien=2.0, truoc_bao_lau=trong_thang)

    tom_tat = llm_usage_service.tom_tat(db)

    assert tom_tat.cost_usd_this_month == pytest.approx(2.0)


# --- Trần đọc từ cấu hình ----------------------------------------------


def test_tran_lay_tu_cau_hinh(db, monkeypatch) -> None:
    _cau_hinh(
        monkeypatch,
        llm_max_requests_per_min=15,
        llm_max_requests_per_day=500,
        monthly_budget_usd=42.5,
    )

    tom_tat = llm_usage_service.tom_tat(db)

    assert tom_tat.max_requests_per_min == 15
    assert tom_tat.max_requests_per_day == 500
    assert tom_tat.monthly_budget_usd == 42.5


def test_tran_bang_0_nghia_la_khong_gioi_han(db, monkeypatch) -> None:
    """0 = KHÔNG giới hạn (khớp ``kiem_han_muc`` của worker). Giao diện phải
    phân biệt được "chưa khai trần" với "trần bằng không lượt"."""
    _cau_hinh(monkeypatch, llm_max_requests_per_min=0, llm_max_requests_per_day=0)

    tom_tat = llm_usage_service.tom_tat(db)

    assert tom_tat.max_requests_per_min == 0
    assert tom_tat.max_requests_per_day == 0


# --- Tầng HTTP ---------------------------------------------------------


@pytest.fixture
def http_client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        _them(session, so_dong=3, token=700, tien=0.25)
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

    _cau_hinh(monkeypatch, llm_max_requests_per_min=15, llm_max_requests_per_day=500)

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(llm_router.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client


def test_http_tra_du_cac_o_giao_dien_can(http_client) -> None:
    resp = http_client.get("/api/v1/llm/usage")

    assert resp.status_code == 200
    assert resp.json() == {
        "requests_last_min": 3,
        "requests_last_day": 3,
        "tokens_last_day": 2100,
        "cost_usd_this_month": 0.75,
        "max_requests_per_min": 15,
        "max_requests_per_day": 500,
        "monthly_budget_usd": 200.0,
    }


def test_tien_thang_cong_moi_dich_vu_khong_chi_rieng_dich(db) -> None:
    """Trần TIỀN là của toàn bộ dịch vụ ngoài, nên số hiển thị phải cộng hết.

    Worker chặn ngân sách bằng tổng MỌI service (xem
    apps/worker/src/tasks/cost.py::kiem_han_muc). Nếu chỗ hiển thị lọc riêng
    llm_translate thì tới khi M8 ghi dòng TTS, người dùng bị chặn giữa chừng mà
    nhìn màn hình vẫn thấy còn dư ngân sách.

    Ngược lại số LƯỢT vẫn chỉ đếm llm_translate — trần lượt/phút là của riêng
    model dịch, không dùng chung với TTS.
    """
    db.add(CostLog(service="llm_translate", unit="token", quantity=10, cost_usd=1.0))
    db.add(CostLog(service="tts", unit="giây", quantity=30, cost_usd=2.0))
    db.commit()

    tom_tat = llm_usage_service.tom_tat(db)

    assert tom_tat.cost_usd_this_month == 3.0
    assert tom_tat.requests_last_day == 1
