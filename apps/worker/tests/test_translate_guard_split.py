"""Lô dịch lệch số dòng thì CHIA ĐÔI, không nhảy thẳng xuống dịch từng dòng.

Đo thật 2026-08-14 trên video 672 câu, lô 100:

    count_mismatch  expected=100 got=101
    count_mismatch  expected=100 got=101
    fallback_line_by_line  count=100

Model trả 101 dòng cho 100 câu. Cơ chế dự phòng cũ rơi thẳng xuống dịch TỪNG
DÒNG — 100 lượt gọi cho một lô. Kết quả đo được: 4 lô sinh ra 189 lượt gọi
thành công và 75 lượt bị từ chối 429, vào một model chỉ cho 15 lượt/phút.

Với API có hạn mức, dịch từng dòng là phương án ĐẮT NHẤT có thể chọn. Chia đôi
rồi thử lại giữ được lợi thế dịch theo lô (có ngữ cảnh, ít lượt gọi) mà vẫn thu
hẹp dần vùng hỏng: 100 -> 2x50 -> 4x25 -> ... chỉ dịch từng dòng khi lô đã nhỏ
tới mức không chia được nữa.
"""

from __future__ import annotations

import pytest

from src.pipeline.translate import _translate_with_guard


class TranslatorGia:
    """Trả sai số dòng cho lô LỚN, đúng cho lô nhỏ — mô phỏng hành vi thật."""

    def __init__(self, nguong_dung: int):
        self.nguong_dung = nguong_dung
        self.so_luot_goi = 0
        self.co_lo = []

    def translate_batch(self, texts, *, tone, glossary):
        self.so_luot_goi += 1
        self.co_lo.append(len(texts))
        if len(texts) > self.nguong_dung:
            #: Thừa một dòng — đúng kiểu lỗi quan sát được (101 cho 100).
            return [f"vi:{t}" for t in texts] + ["dòng thừa"]
        return [f"vi:{t}" for t in texts]


def _texts(n: int) -> list[str]:
    return [f"câu {i}" for i in range(n)]


def test_lo_dung_ngay_thi_goi_dung_mot_lan() -> None:
    t = TranslatorGia(nguong_dung=100)

    ra = _translate_with_guard(t, _texts(100), "doi_thuong", {})

    assert len(ra) == 100
    assert t.so_luot_goi == 1


def test_lo_lech_thi_chia_doi_chu_khong_dich_tung_dong() -> None:
    """Ngưỡng 50: lô 100 hỏng, hai nửa 50 chạy được."""
    t = TranslatorGia(nguong_dung=50)

    ra = _translate_with_guard(t, _texts(100), "doi_thuong", {})

    assert len(ra) == 100
    assert 50 in t.co_lo, "phải có lô 50 — dấu hiệu đã chia đôi"
    assert 1 not in t.co_lo, "không được rơi xuống dịch từng dòng"


def test_so_luot_goi_it_hon_han_so_cau() -> None:
    """Chốt chặn chính: 100 câu KHÔNG được sinh ra ~100 lượt gọi."""
    t = TranslatorGia(nguong_dung=25)

    _translate_with_guard(t, _texts(100), "doi_thuong", {})

    assert t.so_luot_goi < 20, f"quá nhiều lượt gọi: {t.so_luot_goi}"


def test_giu_dung_thu_tu_cau_sau_khi_chia() -> None:
    """Ghép hai nửa sai thứ tự là phụ đề lệch hết — lỗi khó thấy nhất."""
    t = TranslatorGia(nguong_dung=25)

    ra = _translate_with_guard(t, _texts(60), "doi_thuong", {})

    assert ra == [f"vi:câu {i}" for i in range(60)]


def test_lo_nho_toi_muc_khong_chia_duoc_thi_moi_dich_tung_dong() -> None:
    """Hết đường chia thì vẫn phải có phương án cuối, không được mất câu."""
    t = TranslatorGia(nguong_dung=0)  # sai với mọi kích thước lô

    ra = _translate_with_guard(t, _texts(4), "doi_thuong", {})

    assert len(ra) == 4


def test_khong_bao_gio_mat_cau_du_moi_lo_deu_hong() -> None:
    class LuonHong:
        def translate_batch(self, texts, *, tone, glossary):
            from src.errors import TranslateError

            raise TranslateError("nhà cung cấp từ chối")

    ra = _translate_with_guard(LuonHong(), _texts(10), "doi_thuong", {})

    #: Giữ nguyên tiếng Trung còn hơn mất dòng — hành vi cũ, không được đổi.
    assert ra == _texts(10)


@pytest.mark.parametrize("n", [1, 2, 3, 7, 8, 9])
def test_lo_rat_nho_khong_lam_vo_thuat_toan(n: int) -> None:
    t = TranslatorGia(nguong_dung=0)

    ra = _translate_with_guard(t, _texts(n), "doi_thuong", {})

    assert len(ra) == n
