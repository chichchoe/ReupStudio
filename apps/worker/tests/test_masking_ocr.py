"""Quy đổi toạ độ OCR sang phần trăm — ranh giới pixel/phần trăm của M3.

RapidOCR trả về bốn ĐỈNH theo pixel của khung hình. Toàn bộ phần còn lại của
chặng này làm việc bằng phần trăm 0–1 (luật số 2 CLAUDE.md). Chỗ quy đổi là
ranh giới duy nhất giữa hai hệ, nên nó phải đúng tuyệt đối: lệch ở đây thì mask
lệch theo, mà video vẫn chạy nên không ai biết.

Chỉ phần THUẦN được test tự động. Việc RapidOCR đọc đúng chữ hay không thì kiểm
bằng script chạy tay trên ảnh thật (CLAUDE.md: model AI không test tự động).
"""

from __future__ import annotations

import pytest

from src.pipeline.masking.ocr import doi_sang_phan_tram

#: Khung hình 720×1280 — đúng kích thước video rednote đã dùng để đo.
RONG, CAO = 720, 1280


def test_hop_chu_nhat_doi_dung_ti_le() -> None:
    diem = [[72, 128], [648, 128], [648, 192], [72, 192]]

    x, y, w, h = doi_sang_phan_tram(diem, RONG, CAO)

    assert x == pytest.approx(0.1)
    assert y == pytest.approx(0.1)
    assert w == pytest.approx(0.8)
    assert h == pytest.approx(0.05)


def test_hop_nghieng_lay_khung_bao_tron_bon_dinh() -> None:
    """OCR trả về tứ giác chứ không phải hình chữ nhật khi chữ hơi nghiêng.
    Lấy khung bao trọn, nếu không thì góc chữ thò ra ngoài mask."""
    diem = [[72, 128], [648, 160], [648, 224], [72, 192]]

    x, y, w, h = doi_sang_phan_tram(diem, RONG, CAO)

    assert x == pytest.approx(0.1)
    assert y == pytest.approx(0.1)
    assert w == pytest.approx(0.8)
    assert h == pytest.approx(0.075)


def test_toa_do_am_bi_kep_ve_khong() -> None:
    """OCR đôi khi trả đỉnh lố ra ngoài mép khung. Toạ độ âm làm hỏng mọi phép
    tính phía sau mà không báo lỗi."""
    diem = [[-20, -10], [648, -10], [648, 192], [-20, 192]]

    x, y, _, _ = doi_sang_phan_tram(diem, RONG, CAO)

    assert x == 0.0
    assert y == 0.0


def test_toa_do_vuot_mep_bi_kep_ve_mot() -> None:
    diem = [[72, 128], [900, 128], [900, 1400], [72, 1400]]

    x, y, w, h = doi_sang_phan_tram(diem, RONG, CAO)

    assert x + w <= 1.0
    assert y + h <= 1.0


def test_kich_thuoc_khung_khong_hop_le_thi_bao_loi() -> None:
    """Chia cho 0 — báo lỗi rõ thay vì ném ZeroDivisionError từ tận đáy."""
    from src.errors import InvalidFrameSizeError

    with pytest.raises(InvalidFrameSizeError):
        doi_sang_phan_tram([[0, 0], [10, 0], [10, 10], [0, 10]], 0, CAO)


def test_khong_du_bon_dinh_thi_bao_loi() -> None:
    from src.errors import InvalidFrameSizeError

    with pytest.raises(InvalidFrameSizeError):
        doi_sang_phan_tram([[0, 0], [10, 10]], RONG, CAO)
