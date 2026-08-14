"""Hook phải nằm TRỌN trong khối hook — vừa cả bề ngang lẫn chiều cao.

Sinh ra từ một khung hình render thật (2026-08-14): câu hook
``Thử hook 3 giây đầu`` hiện lên thành ``hook 3 giây đ``, cụt cả hai đầu.
Nguyên nhân: cỡ chữ hook = chiều cao khối × 0,6 = 161px ở khung 1920, mà
``drawtext`` KHÔNG tự xuống dòng — 19 ký tự cần ~1520px trong khi khối hook
chỉ rộng 810px.

Ràng buộc thứ hai, lộ ra khi sửa: 161px là cỡ dành cho MỘT dòng trong khối cao
269px. Xuống hai dòng ở cỡ đó thì chữ tràn xuống dưới khối, đè vào video. Nên
phép ép phải xét cả hai chiều.

Khác lỗi phụ đề đã sửa trước đó: ``drawtext`` tính bằng pixel thật, không dính
chuyện ``PlayRes`` của ASS. Đây là lỗi riêng — thiếu hẳn bước đo chữ.
"""

from __future__ import annotations

from src.pipeline.shortform.hook import (
    HOOK_MAX_LINES,
    build_hook_filter,
    fit_hook_text,
    hook_box,
)
from src.pipeline.shortform.safe_area import SafeArea

TIKTOK = SafeArea(top=0.06, bottom=0.18, left=0.05, right=0.20)
#: Khối hook của khung 1080×1920 với vùng an toàn TikTok:
#: rộng 1080 × (1 − 0,05 − 0,20) = 810 · cao 1920 × 0,14 = 269.
BOX_W, BOX_H = 810, 269

CAU_DAI = "Cô ấy tỉnh ra sau ba năm bị coi thường và tất cả đã quá muộn"


def _dong(text: str) -> list[str]:
    return text.splitlines()


def test_cau_ngan_khong_phai_xuong_dong() -> None:
    text, _ = fit_hook_text("Xem hết nhé", box_w_px=BOX_W, box_h_px=BOX_H)
    assert "\n" not in text


def test_cau_dai_duoc_xuong_dong_thay_vi_tran_ra_ngoai() -> None:
    """Đúng câu đã làm lộ lỗi trên khung hình thật."""
    text, _ = fit_hook_text("Thử hook 3 giây đầu", box_w_px=BOX_W, box_h_px=BOX_H)
    assert "\n" in text
    assert len(_dong(text)) <= HOOK_MAX_LINES


def test_chu_luon_vua_be_ngang_khoi_hook() -> None:
    """Ràng buộc chính. Ước lượng bề rộng: mỗi ký tự ~0,5 cỡ chữ."""
    for cau in ("Xem hết nhé", "Thử hook 3 giây đầu", CAU_DAI):
        text, size = fit_hook_text(cau, box_w_px=BOX_W, box_h_px=BOX_H)
        for dong in _dong(text):
            assert len(dong) * size * 0.5 <= BOX_W


def test_chu_luon_vua_chieu_cao_khoi_hook() -> None:
    """Hai dòng ở cỡ chữ của một dòng sẽ tràn xuống đè vào video."""
    for cau in ("Xem hết nhé", "Thử hook 3 giây đầu", CAU_DAI):
        text, size = fit_hook_text(cau, box_w_px=BOX_W, box_h_px=BOX_H)
        assert len(_dong(text)) * size <= BOX_H


def test_khong_bao_gio_vuot_qua_so_dong_toi_da() -> None:
    text, _ = fit_hook_text(CAU_DAI, box_w_px=BOX_W, box_h_px=BOX_H)
    assert len(_dong(text)) <= HOOK_MAX_LINES


def test_cau_cang_dai_co_chu_cang_nho() -> None:
    _, nho = fit_hook_text(CAU_DAI, box_w_px=BOX_W, box_h_px=BOX_H)
    _, to = fit_hook_text("Xem hết nhé", box_w_px=BOX_W, box_h_px=BOX_H)
    assert nho < to


def test_khong_thu_nho_qua_san_du_cau_dai_bao_nhieu() -> None:
    """Thà chữ hơi tràn còn hơn nhỏ tới mức không ai đọc được."""
    _, size = fit_hook_text("x " * 200, box_w_px=BOX_W, box_h_px=BOX_H)
    assert size >= 24


def test_khong_cat_giua_tu() -> None:
    goc = "Thử hook 3 giây đầu"
    text, _ = fit_hook_text(goc, box_w_px=BOX_W, box_h_px=BOX_H)
    assert text.replace("\n", " ").split() == goc.split()


def test_tu_don_dai_hon_ca_dong_van_khong_bi_mat_chu() -> None:
    """Một từ dài hơn cả dòng thì không xuống dòng được — vẫn phải giữ đủ chữ."""
    text, _ = fit_hook_text("Neopolitanmatxacoocxetgiangsinh", box_w_px=200, box_h_px=BOX_H)
    assert text.replace("\n", "") == "Neopolitanmatxacoocxetgiangsinh"


def test_cau_rong_khong_no() -> None:
    text, size = fit_hook_text("   ", box_w_px=BOX_W, box_h_px=BOX_H)
    assert text == ""
    assert size > 0


def test_filter_dung_co_chu_da_ep_vua() -> None:
    """``build_hook_filter`` phải dùng kết quả của ``fit_hook_text``, không
    dùng lại cỡ chữ gốc — nếu không, tính xong rồi vứt đi."""
    _, size = fit_hook_text(CAU_DAI, box_w_px=BOX_W, box_h_px=BOX_H)
    loc = build_hook_filter(CAU_DAI, hook_box(TIKTOK), 1080, 1920)
    assert f"fontsize={size}:" in loc


def test_filter_giu_xuong_dong_trong_text() -> None:
    loc = build_hook_filter("Thử hook 3 giây đầu", hook_box(TIKTOK), 1080, 1920)
    #: ``\n`` không phải ký tự đặc biệt của filtergraph nên đi thẳng vào chuỗi
    #: filter (xem ``_escape_drawtext_text``); drawtext tự vẽ thành nhiều dòng.
    assert "\n" in loc
