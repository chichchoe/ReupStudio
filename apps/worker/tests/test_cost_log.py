"""Ghi ``cost_logs`` và đếm hạn mức.

Điểm dễ sai nhất: ``translate_cues`` báo usage CỘNG DỒN sau mỗi lô, nên ghi
thẳng số đó vào mỗi dòng sẽ đếm gấp bội. Phải ghi phần CHÊNH giữa hai lần chụp.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from reup_core.models import CostLog
from reup_core.models.base import Base
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.tasks import cost
from src.translator.base import LlmUsage


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def gia_bang_khong(monkeypatch):
    from src.config import Settings

    monkeypatch.setattr(cost, "get_settings", lambda: Settings(_env_file=None))


def _usage(requests: int, prompt: int, completion: int, total: int) -> LlmUsage:
    u = LlmUsage(model="gemini-3.6-flash")
    u.requests = requests
    u.prompt_tokens = prompt
    u.completion_tokens = completion
    u.total_tokens = total
    return u


def test_ghi_phan_chenh_khong_ghi_so_cong_don(session, gia_bang_khong) -> None:
    """Ba lô, mỗi lô 20 token -> ba dòng 20, KHÔNG phải 20/40/60."""
    truoc = None
    for lan in range(1, 4):
        u = _usage(lan, 10 * lan, 5 * lan, 20 * lan)
        cost.ghi_usage(session, None, u, truoc)
        truoc = u
    session.flush()

    so_luong = [r.quantity for r in session.scalars(select(CostLog)).all()]
    assert so_luong == [20.0, 20.0, 20.0]


def test_dong_dau_tien_khong_co_lan_truoc(session, gia_bang_khong) -> None:
    cost.ghi_usage(session, None, _usage(1, 9, 0, 26), None)
    session.flush()

    row = session.scalar(select(CostLog))
    assert row.quantity == 26.0
    assert row.model == "gemini-3.6-flash"
    assert row.unit == "token"
    assert row.service == "llm_translate"


def test_bac_mien_phi_thi_tien_bang_khong(session, gia_bang_khong) -> None:
    cost.ghi_usage(session, None, _usage(1, 100000, 50000, 160000), None)
    session.flush()

    assert session.scalar(select(CostLog)).cost_usd == 0.0


def test_co_bang_gia_thi_tinh_ra_tien(session, monkeypatch) -> None:
    """Khi chuyển sang trả phí, đơn giá tính theo MỘT TRIỆU token."""
    from src.config import Settings

    monkeypatch.setattr(
        cost,
        "get_settings",
        lambda: Settings(_env_file=None, llm_price_input_per_1m=0.30, llm_price_output_per_1m=2.50),
    )

    cost.ghi_usage(session, None, _usage(1, 1_000_000, 1_000_000, 2_000_000), None)
    session.flush()

    assert session.scalar(select(CostLog)).cost_usd == pytest.approx(2.80)


def test_dem_luot_chi_tinh_trong_cua_so_thoi_gian(session, gia_bang_khong) -> None:
    cu = datetime.now(UTC) - timedelta(seconds=3600)
    session.add(CostLog(service="llm_translate", unit="token", quantity=1, created_at=cu))
    cost.ghi_usage(session, None, _usage(1, 1, 1, 2), None)
    session.flush()

    assert cost.dem_luot(session, trong_giay=60) == 1
    assert cost.dem_luot(session, trong_giay=86400) == 2


def test_tom_tat_tra_ve_ca_so_dung_va_tran(session, gia_bang_khong) -> None:
    cost.ghi_usage(session, None, _usage(1, 1, 1, 2), None)
    session.flush()

    t = cost.tom_tat(session)

    assert t["luot_phut"] == 1
    assert t["luot_ngay"] == 1
    assert "tran_luot_phut" in t and "tran_tien_thang_usd" in t
