"""Luật nghiệp vụ của thư viện giọng.

Ba thứ hỏng âm thầm nếu không khoá lại:

- Xoá giọng đang là mặc định mà không chuyển mặc định đi đâu -> mọi video sau
  đó không biết đọc bằng gì, và lỗi chỉ nổ ra ở worker giữa chừng pipeline.
- Xoá được giọng dựng sẵn -> mất luôn danh sách seed, muốn lấy lại phải chạy
  lại migration.
- Sửa chữ của đoạn mẫu mà giữ nguyên ``codes.npz`` -> model clone đọc theo bản
  mã hoá CŨ, tức theo chữ sai mà người dùng vừa sửa xong.

Dùng SQLite trong RAM chứ không đối tượng giả: chỉ số duy nhất một phần trên
``mac_dinh`` là một phần của luật, mà đối tượng giả không kiểm được nó.
"""

from __future__ import annotations

import uuid

import pytest
from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.models import GiongDoc
from reup_core.models.base import Base
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.errors import ApiError, NotFound
from src.services import giong_doc_service as sv


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _dung_san(db, ten: str, ma: str, *, mac_dinh: bool = False) -> GiongDoc:
    row = GiongDoc(
        ten=ten,
        nha_cung_cap="edge",
        ma_giong=ma,
        ngon_ngu="vi",
        gioi_tinh="nữ",
        nguon=NguonGiong.DUNG_SAN.value,
        mac_dinh=mac_dinh,
        trang_thai=TrangThaiGiong.SAN_SANG.value,
    )
    db.add(row)
    db.commit()
    return row


class TestTao:
    def test_giong_moi_bat_dau_o_trang_thai_dang_xu_ly(self, db) -> None:
        #: Chưa chuẩn hoá, chưa gõ chữ, chưa có file nghe thử — hiện nó như
        #: sẵn sàng là mời người dùng chọn một giọng chưa dùng được.
        row = sv.tao(
            db,
            ten="Giọng tôi",
            nguon=NguonGiong.TU_THU.value,
            nha_cung_cap="fish_mlx",
            co_file=True,
        )
        db.commit()
        assert row.trang_thai == TrangThaiGiong.DANG_XU_LY.value
        assert row.co_ma_hoa is False
        assert row.mac_dinh is False

    def test_nguon_la_thi_bao_ro(self, db) -> None:
        with pytest.raises(ApiError, match="Nguồn giọng"):
            sv.tao(db, ten="X", nguon="tu_dau_ra", nha_cung_cap="fish_mlx", co_file=True)

    def test_khong_tu_tao_giong_DUNG_SAN(self, db) -> None:
        #: Giọng dựng sẵn chỉ đến từ seed. Cho tạo tay là mở đường cho một danh
        #: sách giọng dựng sẵn không khớp với thứ nhà cung cấp thật sự có.
        with pytest.raises(ApiError, match="dựng sẵn"):
            sv.tao(db, ten="X", nguon=NguonGiong.DUNG_SAN.value, nha_cung_cap="edge")

    def test_ba_nguon_tu_file_deu_BAT_BUOC_co_file(self, db) -> None:
        for nguon in (
            NguonGiong.TU_THU.value,
            NguonGiong.CAT_TU_FILE.value,
            NguonGiong.THUE_DOC.value,
        ):
            with pytest.raises(ApiError, match="chưa chọn file"):
                sv.tao(db, ten="X", nguon=nguon, nha_cung_cap="fish_mlx", co_file=False)

    def test_tam_tu_may_KHONG_can_file(self, db) -> None:
        row = sv.tao(
            db,
            ten="Giọng tạm",
            nguon=NguonGiong.TAM_TU_MAY.value,
            nha_cung_cap="fish_mlx",
            co_file=False,
        )
        db.commit()
        assert row.nguon == NguonGiong.TAM_TU_MAY.value

    def test_cat_tu_file_phai_co_moc_hop_le(self, db) -> None:
        with pytest.raises(ApiError, match="Mốc cắt"):
            sv.tao(
                db,
                ten="X",
                nguon=NguonGiong.CAT_TU_FILE.value,
                nha_cung_cap="fish_mlx",
                co_file=True,
                cat_tu_giay=12.0,
                cat_den_giay=8.0,
            )


class TestDatMacDinh:
    def test_giong_cu_bi_TAT_truoc_khi_bat_giong_moi(self, db) -> None:
        cu = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural", mac_dinh=True)
        moi = _dung_san(db, "Nam Minh", "vi-VN-NamMinhNeural")

        sv.dat_mac_dinh(db, moi.id)
        db.commit()

        assert [g.mac_dinh for g in (db.get(GiongDoc, cu.id), db.get(GiongDoc, moi.id))] == [
            False,
            True,
        ]

    def test_dat_lai_chinh_no_khong_lam_sao(self, db) -> None:
        g = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural", mac_dinh=True)
        sv.dat_mac_dinh(db, g.id)
        db.commit()
        assert db.get(GiongDoc, g.id).mac_dinh is True

    def test_khong_dat_mac_dinh_giong_dang_xu_ly(self, db) -> None:
        #: Đặt mặc định một giọng chưa dựng xong là hẹn giờ cho lỗi: video kế
        #: tiếp sẽ đòi một đoạn mẫu chưa tồn tại.
        moi = sv.tao(
            db,
            ten="Giọng tôi",
            nguon=NguonGiong.TU_THU.value,
            nha_cung_cap="fish_mlx",
            co_file=True,
        )
        db.commit()
        with pytest.raises(ApiError, match="chưa xong"):
            sv.dat_mac_dinh(db, moi.id)


class TestXoa:
    def test_KHONG_xoa_duoc_giong_dung_san(self, db) -> None:
        g = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        with pytest.raises(ApiError, match="dựng sẵn"):
            sv.xoa(db, g.id)

    def test_xoa_giong_dang_mac_dinh_thi_CHUYEN_mac_dinh_sang_giong_khac(self, db) -> None:
        con_lai = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        cua_toi = sv.tao(
            db,
            ten="Giọng tôi",
            nguon=NguonGiong.TU_THU.value,
            nha_cung_cap="fish_mlx",
            co_file=True,
        )
        cua_toi.trang_thai = TrangThaiGiong.SAN_SANG.value
        db.commit()
        sv.dat_mac_dinh(db, cua_toi.id)
        db.commit()

        sv.xoa(db, cua_toi.id)
        db.commit()

        assert db.get(GiongDoc, cua_toi.id) is None
        assert db.get(GiongDoc, con_lai.id).mac_dinh is True

    def test_mac_dinh_chuyen_sang_giong_SAN_SANG_cu_nhat(self, db) -> None:
        #: Chuyển sang một giọng đang xử lý là chuyển sang thứ chưa dùng được.
        dau_tien = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        _dung_san(db, "Nam Minh", "vi-VN-NamMinhNeural")
        cua_toi = sv.tao(
            db,
            ten="Giọng tôi",
            nguon=NguonGiong.TU_THU.value,
            nha_cung_cap="fish_mlx",
            co_file=True,
        )
        cua_toi.trang_thai = TrangThaiGiong.SAN_SANG.value
        db.commit()
        sv.dat_mac_dinh(db, cua_toi.id)
        db.commit()

        sv.xoa(db, cua_toi.id)
        db.commit()

        assert db.get(GiongDoc, dau_tien.id).mac_dinh is True

    def test_id_khong_co_that(self, db) -> None:
        with pytest.raises(NotFound):
            sv.xoa(db, uuid.uuid4())


class TestSua:
    def test_doi_ten_khong_dung_lai_gi_ca(self, db) -> None:
        g = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        row, can_dung_lai = sv.sua(db, g.id, ten="Chị Mai")
        db.commit()
        assert row.ten == "Chị Mai"
        assert can_dung_lai is False

    def test_doi_mau_text_lam_ban_MA_HOA_cu_vo_nghia(self, db) -> None:
        g = sv.tao(
            db,
            ten="Giọng tôi",
            nguon=NguonGiong.TU_THU.value,
            nha_cung_cap="fish_mlx",
            co_file=True,
        )
        g.trang_thai = TrangThaiGiong.SAN_SANG.value
        g.co_ma_hoa = True
        g.mau_text = "Chữ Whisper gõ sai"
        db.commit()

        row, can_dung_lai = sv.sua(db, g.id, mau_text="Chữ người dùng sửa lại cho đúng")
        db.commit()

        assert can_dung_lai is True
        assert row.co_ma_hoa is False
        assert row.trang_thai == TrangThaiGiong.DANG_XU_LY.value

    def test_mau_text_KHONG_doi_thi_khong_dung_lai(self, db) -> None:
        #: Giao diện gửi cả form mỗi lần Lưu. Coi "gửi lên" là "đã đổi" thì mỗi
        #: lần sửa ghi chú lại chạy lại cả Whisper lẫn mã hoá.
        g = sv.tao(
            db,
            ten="Giọng tôi",
            nguon=NguonGiong.TU_THU.value,
            nha_cung_cap="fish_mlx",
            co_file=True,
        )
        g.mau_text = "Y hệt"
        g.trang_thai = TrangThaiGiong.SAN_SANG.value
        db.commit()

        _, can_dung_lai = sv.sua(db, g.id, mau_text="Y hệt", ghi_chu="thêm ghi chú")
        assert can_dung_lai is False

    def test_dat_mac_dinh_qua_sua(self, db) -> None:
        cu = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural", mac_dinh=True)
        moi = _dung_san(db, "Nam Minh", "vi-VN-NamMinhNeural")
        sv.sua(db, moi.id, mac_dinh=True)
        db.commit()
        assert db.get(GiongDoc, cu.id).mac_dinh is False
        assert db.get(GiongDoc, moi.id).mac_dinh is True


class TestDanhSach:
    def test_giong_mac_dinh_dung_dau(self, db) -> None:
        #: Giọng mặc định là thứ người dùng cần thấy trước nhất — nó là giọng
        #: mọi video sẽ dùng nếu không ai chọn gì.
        _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        moi = _dung_san(db, "Nam Minh", "vi-VN-NamMinhNeural", mac_dinh=True)
        assert sv.danh_sach(db)[0].id == moi.id

    def test_giong_mac_dinh_tra_dung_dong(self, db) -> None:
        _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        moi = _dung_san(db, "Nam Minh", "vi-VN-NamMinhNeural", mac_dinh=True)
        assert sv.giong_mac_dinh(db).id == moi.id

    def test_khong_co_giong_nao_thi_tra_None(self, db) -> None:
        assert sv.giong_mac_dinh(db) is None
        assert db.scalars(select(GiongDoc)).all() == []
