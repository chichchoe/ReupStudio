"""M2-BE-05 — CRUD kênh nguồn và chốt an toàn pháp lý `can_auto_process`.

Chạy trên SQLite trong RAM, gọi thẳng service (không qua HTTP).
"""

from __future__ import annotations

import uuid

import pytest
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.errors import ApiError, Conflict, NotFound
from src.services import source_channel_service


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _tao_kenh(db, **overrides):
    defaults = {
        "platform": "douyin",
        "external_id": "abc123",
        "url": "https://www.douyin.com/user/abc123",
    }
    defaults.update(overrides)
    return source_channel_service.create_channel(db, **defaults)


def test_tao_kenh_moi_mac_dinh_license_status_la_unknown(db) -> None:
    channel = _tao_kenh(db)
    db.commit()

    assert channel.license_status == "unknown"
    assert channel.enabled is True
    assert channel.scan_interval_min == 60


def test_sua_kenh_cap_nhat_duoc_cac_truong(db) -> None:
    channel = _tao_kenh(db)
    db.commit()

    updated = source_channel_service.update_channel(
        db, channel.id, display_name="Kênh phim ngắn", license_status="permitted"
    )
    db.commit()

    assert updated.display_name == "Kênh phim ngắn"
    assert updated.license_status == "permitted"


def test_xoa_kenh(db) -> None:
    channel = _tao_kenh(db)
    db.commit()

    source_channel_service.delete_channel(db, channel.id)
    db.commit()

    with pytest.raises(NotFound):
        source_channel_service.get_channel(db, channel.id)


def test_sua_kenh_khong_ton_tai_thi_nem_notfound(db) -> None:
    with pytest.raises(NotFound):
        source_channel_service.update_channel(db, uuid.uuid4(), display_name="x")


def test_trung_platform_va_external_id_khong_tao_duoc_ban_ghi_thu_hai(db) -> None:
    _tao_kenh(db)
    db.commit()

    with pytest.raises(Conflict):
        _tao_kenh(db)


def test_scan_interval_min_sai_gia_tri_bi_tu_choi(db) -> None:
    with pytest.raises(ApiError):
        _tao_kenh(db, external_id="xyz789", scan_interval_min=45)


@pytest.mark.parametrize("scan_interval_min", [15, 60, 360, 1440])
def test_scan_interval_min_hop_le_duoc_chap_nhan(db, scan_interval_min) -> None:
    channel = _tao_kenh(
        db, external_id=f"ok-{scan_interval_min}", scan_interval_min=scan_interval_min
    )
    db.commit()

    assert channel.scan_interval_min == scan_interval_min


def test_can_auto_process_tra_ve_false_voi_license_unknown(db) -> None:
    channel = _tao_kenh(db, license_status="unknown", enabled=True)

    assert source_channel_service.can_auto_process(channel) is False


def test_can_auto_process_tra_ve_false_khi_kenh_bi_tat(db) -> None:
    channel = _tao_kenh(db, license_status="permitted", enabled=False)

    assert source_channel_service.can_auto_process(channel) is False


@pytest.mark.parametrize("license_status", ["permitted", "licensed", "open", "own"])
def test_can_auto_process_tra_ve_true_voi_license_duoc_phep(db, license_status) -> None:
    channel = _tao_kenh(
        db, external_id=f"lic-{license_status}", license_status=license_status, enabled=True
    )

    assert source_channel_service.can_auto_process(channel) is True
