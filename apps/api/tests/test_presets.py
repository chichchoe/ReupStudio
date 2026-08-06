"""M2-BE-04 — CRUD preset và quy tắc mỗi kind chỉ có một is_default=True.

Chạy trên SQLite trong RAM, gọi thẳng service (không qua HTTP).
"""

from __future__ import annotations

import uuid

import pytest
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.errors import NotFound
from src.services import preset_service


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_tao_preset_moi_va_loc_theo_kind(db) -> None:
    preset_service.create_preset(db, kind="filter", name="Lọc A", config={"min_views": 1000})
    preset_service.create_preset(db, kind="process", name="Xử lý A")
    db.commit()

    filters = preset_service.list_presets(db, kind="filter")

    assert len(filters) == 1
    assert filters[0].name == "Lọc A"
    assert filters[0].config == {"min_views": 1000}


def test_khong_truyen_kind_thi_tra_ve_tat_ca(db) -> None:
    preset_service.create_preset(db, kind="filter", name="Lọc A")
    preset_service.create_preset(db, kind="process", name="Xử lý A")
    db.commit()

    assert len(preset_service.list_presets(db)) == 2


def test_tao_preset_mac_dinh_thi_go_co_preset_cu_cung_kind(db) -> None:
    preset_a = preset_service.create_preset(db, kind="filter", name="A", is_default=True)
    db.commit()

    preset_b = preset_service.create_preset(db, kind="filter", name="B", is_default=True)
    db.commit()

    db.refresh(preset_a)
    assert preset_a.is_default is False
    assert preset_b.is_default is True

    defaults = [p for p in preset_service.list_presets(db, kind="filter") if p.is_default]
    assert len(defaults) == 1
    assert defaults[0].id == preset_b.id


def test_update_preset_dat_mac_dinh_thi_go_co_preset_cu_cung_kind(db) -> None:
    preset_a = preset_service.create_preset(db, kind="subtitle", name="A", is_default=True)
    preset_b = preset_service.create_preset(db, kind="subtitle", name="B")
    db.commit()

    preset_service.update_preset(db, preset_b.id, is_default=True)
    db.commit()

    db.refresh(preset_a)
    db.refresh(preset_b)
    assert preset_a.is_default is False
    assert preset_b.is_default is True


def test_dat_mac_dinh_kind_khac_khong_anh_huong_kind_nay(db) -> None:
    preset_filter = preset_service.create_preset(db, kind="filter", name="A", is_default=True)
    db.commit()

    preset_service.create_preset(db, kind="process", name="B", is_default=True)
    db.commit()

    db.refresh(preset_filter)
    assert preset_filter.is_default is True


def test_update_preset_id_khong_ton_tai_thi_nem_notfound(db) -> None:
    with pytest.raises(NotFound):
        preset_service.update_preset(db, uuid.uuid4(), name="tên mới")
