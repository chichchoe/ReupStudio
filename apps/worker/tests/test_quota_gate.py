"""Chạm trần hạn mức thì DỪNG HẲN, chờ người dùng cho phép.

Chốt ngày 2026-08-14 theo yêu cầu chủ dự án, đúng tinh thần M8-BE-04 "hạn mức
chi tiêu cứng, dừng luồng khi vượt".

Khác với giãn nhịp (``test_translate_pacing.py``): giãn nhịp lo trần theo PHÚT
— chờ một chút rồi chạy tiếp. Chốt chặn này lo trần theo NGÀY và trần TIỀN —
chờ cũng vô ích, phải dừng và báo người dùng.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from reup_core.models import CostLog
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.errors import LlmQuotaExceededError
from src.tasks import cost


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _cau_hinh(monkeypatch, **kw):
    from src.config import Settings

    monkeypatch.setattr(cost, "get_settings", lambda: Settings(_env_file=None, **kw))


def _them_luot(session, so_luot: int, *, tien: float = 0.0, gio_truoc: float = 0) -> None:
    khi = datetime.now(UTC) - timedelta(hours=gio_truoc)
    for _ in range(so_luot):
        session.add(
            CostLog(
                service="llm_translate", unit="token", quantity=1, cost_usd=tien, created_at=khi
            )
        )
    session.flush()


def test_duoi_tran_thi_cho_chay(session, monkeypatch) -> None:
    _cau_hinh(monkeypatch, llm_max_requests_per_day=500)
    _them_luot(session, 10)

    cost.kiem_han_muc(session)  # không được ném


def test_khong_khai_tran_thi_khong_chan(session, monkeypatch) -> None:
    """0 = không giới hạn. Gemini không công bố hạn mức qua API và mỗi dự án
    một khác — đoán hộ rồi chặn nhầm còn tệ hơn không chặn."""
    _cau_hinh(monkeypatch, llm_max_requests_per_day=0, monthly_budget_usd=0)
    _them_luot(session, 10_000, tien=999.0)

    cost.kiem_han_muc(session)


def test_vuot_tran_ngay_thi_dung_han(session, monkeypatch) -> None:
    _cau_hinh(monkeypatch, llm_max_requests_per_day=20)
    _them_luot(session, 20)

    with pytest.raises(LlmQuotaExceededError) as loi:
        cost.kiem_han_muc(session)

    #: Thông báo phải có SỐ để người dùng biết chờ tới bao giờ, không phải một
    #: câu chung chung.
    assert "20" in str(loi.value)


def test_luot_cua_hom_qua_khong_tinh_vao_tran_ngay(session, monkeypatch) -> None:
    """Cửa sổ 24 giờ trượt — hôm qua dùng hết không được chặn hôm nay."""
    _cau_hinh(monkeypatch, llm_max_requests_per_day=20)
    _them_luot(session, 30, gio_truoc=30)

    cost.kiem_han_muc(session)


def test_vuot_tran_tien_thang_thi_dung_han(session, monkeypatch) -> None:
    _cau_hinh(monkeypatch, monthly_budget_usd=10.0, llm_max_requests_per_day=0)
    _them_luot(session, 5, tien=2.5)  # 12,5 USD > 10

    with pytest.raises(LlmQuotaExceededError) as loi:
        cost.kiem_han_muc(session)

    assert "12.5" in str(loi.value) or "12,5" in str(loi.value)


def test_thong_bao_noi_ro_tran_nao_bi_vuot(session, monkeypatch) -> None:
    """Vượt trần ngày và vượt trần tiền là hai chuyện khác nhau — cách xử lý
    cũng khác (chờ sang ngày mai / nâng hạn mức chi tiêu)."""
    _cau_hinh(monkeypatch, llm_max_requests_per_day=5, monthly_budget_usd=0)
    _them_luot(session, 5)

    with pytest.raises(LlmQuotaExceededError) as loi:
        cost.kiem_han_muc(session)

    assert "ngày" in str(loi.value).lower()
