"""M4-WK-02 — đẩy phụ đề khỏi vùng UI của nền tảng.

Toàn bộ hàm test ở đây là hàm THUẦN (``pipeline/shortform/safe_area.py``) nên
chạy được không cần Postgres/Redis/ffmpeg. Vùng an toàn TikTok dùng xuyên
suốt làm ví dụ, đúng giá trị đã seed ở Task 1:
``{"top": 0.06, "bottom": 0.18, "left": 0.05, "right": 0.20}``.
"""

from __future__ import annotations

import pytest

from src.pipeline.shortform.safe_area import (
    SafeArea,
    fits_in_safe_area,
    margin_v_pixels,
    max_line_width_pixels,
)

TIKTOK = SafeArea(top=0.06, bottom=0.18, left=0.05, right=0.20)


def test_margin_v_pixels_lam_tron_dung() -> None:
    assert margin_v_pixels(TIKTOK, 1920) == 346


def test_margin_v_pixels_bien_bottom_bang_khong() -> None:
    safe = SafeArea(top=0.06, bottom=0, left=0.05, right=0.20)
    assert margin_v_pixels(safe, 1920) == 0


def test_max_line_width_pixels_tru_le_trai_phai() -> None:
    assert max_line_width_pixels(TIKTOK, 1080) == 810


def test_fits_in_safe_area_hop_o_giua_khung_thi_dat() -> None:
    box = (0.3, 0.4, 0.4, 0.1)  # nằm gọn giữa khung, không chạm cạnh nào
    assert fits_in_safe_area(box, TIKTOK) is True


def test_fits_in_safe_area_hop_cham_mep_duoi_thi_khong_dat() -> None:
    box = (0.3, 0.9, 0.4, 0.1)  # đáy hộp = 1.0, lấn vào 18% vùng caption dưới
    assert fits_in_safe_area(box, TIKTOK) is False


def test_fits_in_safe_area_hop_lan_vung_nut_ben_phai_thi_khong_dat() -> None:
    box = (0.7, 0.4, 0.25, 0.1)  # x+w = 0.95 > 1-0.20=0.8, lấn cột nút tim/bình luận
    assert fits_in_safe_area(box, TIKTOK) is False


@pytest.mark.parametrize("width,height", [(720, 1280), (1080, 1920), (540, 960)])
def test_chuyen_doi_phan_tram_pixel_khong_mat_mat(width: int, height: int) -> None:
    """Tỷ lệ lề dưới/chiều cao phải xấp xỉ đúng ``bottom``, sai số làm tròn <= 1px."""
    margin = margin_v_pixels(TIKTOK, height)
    expected_px = TIKTOK.bottom * height
    assert abs(margin - expected_px) <= 1

    # rộng cũng phải đúng tương tự cho lề trái/phải (đối xứng cùng công thức).
    width_px = max_line_width_pixels(TIKTOK, width)
    expected_width_px = width * (1 - TIKTOK.left - TIKTOK.right)
    assert abs(width_px - expected_width_px) <= 1


# Ba test của ``build_force_style`` từng nằm ở đây đã bị xoá cùng chính hàm đó
# (2026-08-14). Chúng khoá lại đúng thứ sinh ra lỗi: số pixel nhét vào
# ``force_style`` của filter ``subtitles``, nơi libass hiểu theo khung 384×288
# mà ffmpeg tự đặt cho SRT — lề 346px hoá ~2307px và phụ đề bay ra ngoài mọi
# khung 1080×1920. Kiểu chữ nay nằm trong file ASS có ``PlayRes`` bằng khung
# đích; xem ``test_subtitle_ass.py`` và ``test_burn_filter.py``.
