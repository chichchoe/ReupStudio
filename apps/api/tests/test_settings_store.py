"""Cấu hình lưu trong DB — bí mật phải mã hoá và KHÔNG BAO GIỜ trả ra ngoài.

Vì sao có module này: file ``.env`` nằm cạnh mã nguồn nên chỉ cần một lần
``git add -A`` bất cẩn là khoá API lên GitHub. Chuyện đó suýt xảy ra ngày
2026-08-16, chặn được chỉ nhờ bộ quét bí mật của GitHub.

Đây là phần dễ sai nhất và sai thì lộ khoá, nên test kỹ hơn mọi chỗ khác.
"""

from __future__ import annotations

import os

import pytest
from reup_core.models import AppSetting
from reup_core.models.base import Base
from reup_core.settings_store import (
    CHE,
    KHOA_BOOTSTRAP,
    KhoaMaHoaThieu,
    doc_de_hien,
    doc_tat_ca_that,
    ghi,
    la_bi_mat,
    nap_vao_moi_truong,
    sinh_khoa,
    xoa,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(autouse=True)
def khoa_ma_hoa(monkeypatch):
    monkeypatch.setenv("SETTINGS_KEY", sinh_khoa())


# --------------------------------------------------------------------------- #
# Mã hoá
# --------------------------------------------------------------------------- #


def test_bi_mat_khong_bao_gio_nam_dang_van_ban_thuong(db) -> None:
    """Ai đọc được DB cũng không được thấy khoá API."""
    ghi(db, "LLM_API_KEY", "khoa-gia-dung-cho-test-khong-phai-khoa-that")

    row = db.get(AppSetting, "LLM_API_KEY")
    assert row.value_plain is None
    assert "khoa-gia" not in (row.value_encrypted or "")


def test_bi_mat_giai_ma_lai_dung_nguyen_van(db) -> None:
    ghi(db, "LLM_API_KEY", "khoa-gia-dung-cho-test-khong-phai-khoa-that")

    assert doc_tat_ca_that(db)["LLM_API_KEY"] == "khoa-gia-dung-cho-test-khong-phai-khoa-that"


def test_gia_tri_thuong_khong_bi_ma_hoa(db) -> None:
    """Mã hoá cả những thứ không phải bí mật làm DB không đọc được bằng mắt khi
    cần dò lỗi, mà chẳng bảo vệ thêm gì."""
    ghi(db, "WHISPER_MODEL", "small")

    row = db.get(AppSetting, "WHISPER_MODEL")
    assert row.value_plain == "small"
    assert row.value_encrypted is None


def test_khong_co_khoa_ma_hoa_thi_bao_loi_ro(db, monkeypatch) -> None:
    """Thà dừng với lời nhắc sinh khoá còn hơn lưu khoá API dạng thô."""
    monkeypatch.delenv("SETTINGS_KEY", raising=False)

    with pytest.raises(KhoaMaHoaThieu):
        ghi(db, "LLM_API_KEY", "khoa-that")


def test_doi_khoa_ma_hoa_thi_BO_QUA_dong_hong_chu_khong_sap(db, monkeypatch) -> None:
    """Đổi SETTINGS_KEY mà quên nhập lại khoá API: cả ứng dụng không được chết
    vì một dòng, nó phải rơi về biến môi trường như trước."""
    ghi(db, "LLM_API_KEY", "khoa-cu")
    ghi(db, "WHISPER_MODEL", "small")
    monkeypatch.setenv("SETTINGS_KEY", sinh_khoa())

    ra = doc_tat_ca_that(db)

    assert "LLM_API_KEY" not in ra
    assert ra["WHISPER_MODEL"] == "small"


# --------------------------------------------------------------------------- #
# Không rò rỉ ra ngoài
# --------------------------------------------------------------------------- #


def test_ban_de_hien_luon_che_bi_mat(db) -> None:
    ghi(db, "LLM_API_KEY", "khoa-gia-cho-test")

    muc = next(m for m in doc_de_hien(db) if m.key == "LLM_API_KEY")

    assert muc.value == CHE
    assert muc.da_dat is True


def test_bi_mat_chua_dat_thi_bao_la_chua_dat(db) -> None:
    """Giao diện phải phân biệt "đã đặt" với "chưa đặt" mà không biết giá trị."""
    ghi(db, "WHISPER_MODEL", "small")

    muc = [m for m in doc_de_hien(db) if m.key == "LLM_API_KEY"]

    assert muc == []


def test_luu_o_trong_KHONG_xoa_bi_mat_dang_co(db) -> None:
    """Giao diện không bao giờ nhận được giá trị thật nên nó gửi lên chuỗi rỗng
    mỗi lần người dùng bấm Lưu mà không sửa ô khoá. Coi đó là "xoá" thì chỉ cần
    sửa một ô khác là mất khoá API."""
    ghi(db, "LLM_API_KEY", "khoa-that")

    ghi(db, "LLM_API_KEY", "")

    assert doc_tat_ca_that(db)["LLM_API_KEY"] == "khoa-that"


# --------------------------------------------------------------------------- #
# Nạp vào môi trường
# --------------------------------------------------------------------------- #


def test_nap_vao_moi_truong_dat_dung_bien(db, monkeypatch) -> None:
    monkeypatch.delenv("WHISPER_MODEL", raising=False)
    ghi(db, "WHISPER_MODEL", "large-v3")

    nap_vao_moi_truong(db)

    assert os.environ["WHISPER_MODEL"] == "large-v3"


def test_DB_de_len_env(db, monkeypatch) -> None:
    """Trang cấu hình là nơi người dùng vừa bấm Lưu; .env là giá trị cũ họ không
    nhìn thấy. Ưu tiên ngược lại làm nút Lưu trông như không ăn."""
    monkeypatch.setenv("WHISPER_MODEL", "tiny")
    ghi(db, "WHISPER_MODEL", "large-v3")

    nap_vao_moi_truong(db)

    assert os.environ["WHISPER_MODEL"] == "large-v3"


def test_KHONG_dung_toi_ba_bien_bootstrap(db, monkeypatch) -> None:
    """DATABASE_URL nằm trong DB mà lại đè lên biến đang dùng để tới DB thì lần
    khởi động sau không vào nổi database."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://that/duoc-dung")
    db.add(AppSetting(key="DATABASE_URL", value_plain="postgresql://bay/khong-ton-tai"))
    db.flush()

    nap_vao_moi_truong(db)

    assert os.environ["DATABASE_URL"] == "postgresql://that/duoc-dung"


def test_ba_bien_bootstrap_duoc_khai_ro(db) -> None:
    assert {"DATABASE_URL", "REDIS_URL", "SETTINGS_KEY"} == KHOA_BOOTSTRAP


def test_xoa_dong_thi_khong_con_trong_danh_sach(db) -> None:
    ghi(db, "WHISPER_MODEL", "small")

    xoa(db, "WHISPER_MODEL")

    assert doc_tat_ca_that(db) == {}


def test_ten_khoa_khong_phan_biet_hoa_thuong(db) -> None:
    """Người dùng gõ tay tên khoá trên giao diện — 'llm_api_key' phải trúng."""
    assert la_bi_mat("llm_api_key")
    ghi(db, "whisper_model", "small")

    assert doc_tat_ca_that(db)["WHISPER_MODEL"] == "small"
