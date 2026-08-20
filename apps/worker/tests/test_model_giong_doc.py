"""Bảng ``giong_doc`` — một dòng một giọng, dựng sẵn lẫn clone.

Test này khoá hai thứ dễ hỏng âm thầm:

1. Chỉ số duy nhất trên ``mac_dinh`` phải là chỉ số MỘT PHẦN (chỉ ràng buộc
   những dòng ``mac_dinh = true``). Khai thiếu ``sqlite_where`` bên cạnh
   ``postgresql_where`` thì trên SQLite nó thành chỉ số duy nhất TOÀN PHẦN, và
   giọng thứ hai có ``mac_dinh = false`` sẽ bị từ chối — hỏng chỉ trong test,
   không hỏng khi chạy thật, tức loại hỏng khó tìm nhất.
2. Có đúng những cột spec C2 chốt, cộng năm cột trạng thái mà luồng chạy nền
   cần (``trang_thai``, ``loi``, ``canh_bao``, ``do_dai_giay``, ``nghe_thu_bang``).
"""

from __future__ import annotations

import pytest
from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.models import GiongDoc
from reup_core.models.base import Base
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _giong(**kw) -> GiongDoc:
    mac = {
        "ten": "Giọng thử",
        "nha_cung_cap": "edge",
        "ma_giong": "vi-VN-HoaiMyNeural",
        "ngon_ngu": "vi",
        "nguon": NguonGiong.DUNG_SAN.value,
        "trang_thai": TrangThaiGiong.SAN_SANG.value,
    }
    mac.update(kw)
    return GiongDoc(**mac)


def test_ten_bang_va_du_cot_spec_C2(db) -> None:
    cot = set(GiongDoc.__table__.columns.keys())
    assert GiongDoc.__tablename__ == "giong_doc"
    assert {
        "id",
        "ten",
        "nha_cung_cap",
        "ma_giong",
        "model",
        "ngon_ngu",
        "nguon",
        "mau_text",
        "co_ma_hoa",
        "mac_dinh",
        "ghi_chu",
        "created_at",
    } <= cot
    #: Năm cột cho luồng chạy nền — thiếu chúng thì giao diện không phân biệt
    #: được "đang xử lý" với "hỏng", và cảnh báo chất lượng không có chỗ nằm.
    assert {"trang_thai", "loi", "canh_bao", "do_dai_giay", "nghe_thu_bang"} <= cot
    #: Mốc cắt của nguồn `cat_tu_file`. Thiếu thì `tao()` nhận tham số rồi
    #: đánh rơi im lặng, và bước chuẩn hoá cắt nhầm 15 giây đầu file.
    assert {"cat_tu_giay", "cat_den_giay"} <= cot


def test_nhieu_giong_KHONG_mac_dinh_cung_ton_tai_duoc(db) -> None:
    db.add_all([_giong(ten=f"Giọng {i}", mac_dinh=False) for i in range(3)])
    db.commit()
    assert len(db.scalars(select(GiongDoc)).all()) == 3


def test_chi_MOT_giong_duoc_lam_mac_dinh(db) -> None:
    db.add(_giong(ten="Một", mac_dinh=True))
    db.commit()
    db.add(_giong(ten="Hai", mac_dinh=True))
    with pytest.raises(IntegrityError):
        db.commit()


def test_mac_dinh_cua_cac_cot(db) -> None:
    db.add(_giong())
    db.commit()
    row = db.scalars(select(GiongDoc)).one()
    assert row.mac_dinh is False
    assert row.co_ma_hoa is False
    assert row.canh_bao == []
    assert row.trang_thai == TrangThaiGiong.SAN_SANG.value


def test_giong_clone_khong_can_ma_giong(db) -> None:
    #: Fish không có trường ``voice`` — giọng đến từ đoạn mẫu, nên ``ma_giong``
    #: PHẢI cho phép rỗng, nếu không mọi giọng clone đều không lưu được.
    db.add(
        _giong(
            ten="Giọng tôi",
            nha_cung_cap="fish_mlx",
            ma_giong=None,
            nguon=NguonGiong.TU_THU.value,
            mau_text="Xin chào, đây là giọng của tôi.",
        )
    )
    db.commit()
    assert db.scalars(select(GiongDoc)).one().ma_giong is None
