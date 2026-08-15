"""Phần THUẦN của bước vá: chọn mask đang hiện, và quy đổi phần trăm sang pixel.

Việc LaMa vá đẹp hay xấu thì không test tự động được, kiểm bằng ảnh trước/sau
trong ``scripts/try_va_chu.py``. Nhưng hai phép tính quanh nó thì phải đúng
tuyệt đối:

1. **Chọn mask đang hiện tại thời điểm t.** Sai ở đây thì hoặc vá vào khung
   không có chữ (mờ một mảng hình vô cớ), hoặc bỏ sót khung có chữ.

2. **Quy đổi phần trăm sang pixel.** Đây là ranh giới cuối cùng giữa hệ toạ độ
   phần trăm của toàn chặng M3 (luật số 2 CLAUDE.md) và pixel thật của ảnh.
"""

from __future__ import annotations

import pytest

from src.pipeline.masking.timeline import MaskRegion
from src.pipeline.masking.vaa import hop_pixel, mask_dang_hien

RONG, CAO = 720, 1280


def _mask(*, y: float = 0.6, h: float = 0.08, bat_dau: float = 2.0, ket_thuc: float = 5.0):
    return MaskRegion(
        x=0.1, y=y, w=0.8, h=h, bat_dau=bat_dau, ket_thuc=ket_thuc, diem=3.0, ly_do=()
    )


# --------------------------------------------------------------------------- #
# Chọn mask đang hiện
# --------------------------------------------------------------------------- #


def test_trong_khoang_thi_mask_dang_hien() -> None:
    assert mask_dang_hien([_mask()], 3.0) == [_mask()]


def test_truoc_khoang_thi_khong_hien() -> None:
    assert mask_dang_hien([_mask()], 1.0) == []


def test_sau_khoang_thi_khong_hien() -> None:
    assert mask_dang_hien([_mask()], 9.0) == []


def test_dung_hai_dau_khoang_thi_van_hien() -> None:
    """Biên đã được nới ở ``timeline.py`` rồi. Cắt thêm ở đây thì khung đầu và
    khung cuối của mỗi câu lại còn nguyên chữ."""
    assert mask_dang_hien([_mask()], 2.0)
    assert mask_dang_hien([_mask()], 5.0)


def test_nhieu_mask_chi_lay_cai_dang_hien() -> None:
    som = _mask(y=0.2, bat_dau=0.0, ket_thuc=1.0)
    muon = _mask(y=0.8, bat_dau=10.0, ket_thuc=12.0)

    assert mask_dang_hien([som, muon], 11.0) == [muon]


def test_khong_co_mask_nao_thi_khong_no() -> None:
    assert mask_dang_hien([], 3.0) == []


# --------------------------------------------------------------------------- #
# Quy đổi phần trăm sang pixel
# --------------------------------------------------------------------------- #


def test_quy_doi_dung_ti_le() -> None:
    x1, y1, x2, y2 = hop_pixel(_mask(y=0.5, h=0.1), RONG, CAO, bien=0)

    assert (x1, x2) == (72, 648)
    assert (y1, y2) == (640, 768)


def test_bien_noi_rong_vung_cat_ra_bon_phia() -> None:
    """LaMa cần thấy nền XUNG QUANH chỗ thủng mới dựng lại được. Cắt sát mask
    thì model chỉ nhìn thấy chữ và vá ra một mảng bệt."""
    khong_bien = hop_pixel(_mask(), RONG, CAO, bien=0)
    co_bien = hop_pixel(_mask(), RONG, CAO, bien=40)

    assert co_bien[0] < khong_bien[0]
    assert co_bien[1] < khong_bien[1]
    assert co_bien[2] > khong_bien[2]
    assert co_bien[3] > khong_bien[3]


def test_bien_khong_tran_ra_ngoai_anh() -> None:
    """Cắt lố ra ngoài ảnh làm numpy trả về mảng rỗng, và LaMa ném lỗi khó hiểu
    ở tận đáy thay vì báo đúng chỗ."""
    x1, y1, x2, y2 = hop_pixel(_mask(y=0.0, h=1.0), RONG, CAO, bien=100)

    assert x1 >= 0
    assert y1 >= 0
    assert x2 <= RONG
    assert y2 <= CAO


def test_hop_luon_co_dien_tich_duong() -> None:
    """Mask mỏng tới mức quy đổi ra 0 pixel thì phép cắt cho mảng rỗng."""
    x1, y1, x2, y2 = hop_pixel(_mask(y=0.5, h=0.0001), RONG, CAO, bien=0)

    assert x2 > x1
    assert y2 > y1


def test_kich_thuoc_anh_khong_hop_le_thi_bao_loi() -> None:
    from src.errors import InvalidFrameSizeError

    with pytest.raises(InvalidFrameSizeError):
        hop_pixel(_mask(), 0, CAO, bien=0)


# --------------------------------------------------------------------------- #
# Hạ độ phân giải vùng vá
# --------------------------------------------------------------------------- #


def test_thu_nho_roi_phong_lai_giu_nguyen_kich_thuoc() -> None:
    """Vá ở độ phân giải thấp cho nhanh, nhưng miếng vá phải khớp lại đúng ô cũ.

    Lệch một pixel thì có đường nối thấy rõ quanh chỗ vừa vá.
    """
    import numpy as np

    from src.pipeline.masking.vaa import thu_nho_va_phong_lai

    cat = np.zeros((192, 720, 3), dtype=np.uint8)
    mat_na = np.zeros((192, 720), dtype=np.uint8)
    mat_na[40:120, 60:600] = 255

    ra = thu_nho_va_phong_lai(cat, mat_na, 0.75, lambda c, m: c)

    assert ra.shape == cat.shape


def test_ti_le_mot_thi_khong_dong_vao_anh() -> None:
    """Tỉ lệ 1.0 phải là đường đi thẳng, không thu nhỏ rồi phóng lại — mỗi lần
    resize là một lần mất nét, làm không công."""
    import numpy as np

    from src.pipeline.masking.vaa import thu_nho_va_phong_lai

    cat = np.random.randint(0, 255, (64, 128, 3), dtype=np.uint8)
    mat_na = np.zeros((64, 128), dtype=np.uint8)
    mat_na[10:50, 10:100] = 255

    ra = thu_nho_va_phong_lai(cat, mat_na, 1.0, lambda c, m: c)

    assert np.array_equal(ra, cat)


def test_vung_qua_nho_thi_khong_thu_nho_them() -> None:
    """Thu nhỏ một vùng đã bé xíu cho ra vài chục pixel — model không còn gì để
    đọc, mà tiết kiệm được vài mili giây."""
    import numpy as np

    from src.pipeline.masking.vaa import thu_nho_va_phong_lai

    cat = np.zeros((20, 30, 3), dtype=np.uint8)
    mat_na = np.zeros((20, 30), dtype=np.uint8)
    mat_na[5:15, 5:25] = 255

    goi = []
    thu_nho_va_phong_lai(cat, mat_na, 0.5, lambda c, m: goi.append(c.shape) or c)

    assert goi[0] == cat.shape
