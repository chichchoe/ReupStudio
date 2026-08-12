"""M4-WK-03 — chèn text hook 3 giây đầu.

Toàn bộ hàm test ở đây là hàm THUẦN (``pipeline/shortform/hook.py``), chạy
được không cần ffmpeg/DB/Redis. Vùng an toàn TikTok dùng xuyên suốt, đúng giá
trị đã seed ở Task 1 (giống ``test_safe_area.py``):
``{"top": 0.06, "bottom": 0.18, "left": 0.05, "right": 0.20}``.
"""

from __future__ import annotations

import re

from src.pipeline.cues import Cue
from src.pipeline.shortform.hook import (
    HOOK_DURATION_SEC,
    build_hook_filter,
    hook_box,
    trim_slow_intro,
)
from src.pipeline.shortform.safe_area import SafeArea, fits_in_safe_area

TIKTOK = SafeArea(top=0.06, bottom=0.18, left=0.05, right=0.20)


# ---------------------------------------------------------------------------
# hook_box
# ---------------------------------------------------------------------------


def test_hook_box_nam_gon_trong_vung_an_toan() -> None:
    """hook_box phải nằm trọn trong vùng an toàn — dùng đúng phép kiểm của Task 2,
    không viết lại phép kiểm chồng/không chồng ở đây."""
    box = hook_box(TIKTOK)
    assert fits_in_safe_area(box, TIKTOK) is True


def test_hook_box_nam_tren_vung_phu_de_khong_de_len_nhau() -> None:
    """Đáy hộp hook phải nằm hẳn TRÊN mép trên của vùng caption (``safe.bottom``)
    — nơi phụ đề đặt sát đáy — để hook và phụ đề không bao giờ chồng nhau."""
    x, y, w, h = hook_box(TIKTOK)
    subtitle_top = 1 - TIKTOK.bottom  # mép trên của dải phụ đề sát đáy
    assert y + h <= subtitle_top


def test_hook_box_neo_vao_mep_tren_vung_an_toan() -> None:
    x, y, w, h = hook_box(TIKTOK)
    assert y == TIKTOK.top
    assert x == TIKTOK.left
    assert w == 1 - TIKTOK.left - TIKTOK.right


def test_hook_box_vung_an_toan_qua_hep_van_khong_de_len_phu_de() -> None:
    """Nền tảng giả định có top/bottom cực lớn (vùng trống dọc gần như bằng 0)
    — hook_box phải tự co lại, KHÔNG bao giờ tràn xuống vùng phụ đề."""
    safe_hep = SafeArea(top=0.45, bottom=0.45, left=0.05, right=0.05)
    box = hook_box(safe_hep)
    assert fits_in_safe_area(box, safe_hep) is True


# ---------------------------------------------------------------------------
# build_hook_filter — enable window
# ---------------------------------------------------------------------------


def test_build_hook_filter_co_enable_gioi_han_dung_0_den_3s() -> None:
    box = hook_box(TIKTOK)
    filt = build_hook_filter("Xem hết video!", box, 1080, 1920)
    assert f"enable='between(t,0,{HOOK_DURATION_SEC})'" in filt
    assert "between(t,0,3.0)" in filt


def test_build_hook_filter_la_filter_drawtext() -> None:
    box = hook_box(TIKTOK)
    filt = build_hook_filter("Hook", box, 1080, 1920)
    assert filt.startswith("drawtext=")


# ---------------------------------------------------------------------------
# build_hook_filter — escape từng ký tự nguy hiểm
# ---------------------------------------------------------------------------


def _text_value(filt: str) -> str:
    """Lấy phần giá trị của ``text=...`` ra khỏi chuỗi filter để so khớp,
    không dựa vào việc phải tách đúng dấu ``:`` phân tách option (tự thân dấu
    ``:`` trong text đã bị escape nên không lẫn với dấu phân tách thật của
    ``:expansion=none`` ngay sau nó)."""
    # "drawtext=" tự nó CHỨA chuỗi con "text=" (draw-TEXT=) — phải neo vào
    # "drawtext=text=" ở đầu, không thì regex khớp nhầm vào giữa "drawtext=".
    match = re.search(r"^drawtext=text=(.*?):expansion=none", filt)
    assert match is not None, f"không tìm thấy text=... trong filter: {filt}"
    return match.group(1)


def test_escape_dau_hai_cham() -> None:
    box = hook_box(TIKTOK)
    filt = build_hook_filter("Giờ: 3 giây", box, 1080, 1920)
    assert _text_value(filt) == "Giờ\\\\: 3 giây"


def test_escape_dau_nhay_don() -> None:
    box = hook_box(TIKTOK)
    filt = build_hook_filter("Đừng bỏ lỡ 'phần cuối'", box, 1080, 1920)
    assert _text_value(filt) == "Đừng bỏ lỡ \\\\\\'phần cuối\\\\\\'"


def test_escape_dau_gach_cheo_nguoc() -> None:
    box = hook_box(TIKTOK)
    filt = build_hook_filter("C:\\Video", box, 1080, 1920)
    # ":" gốc -> 2 backslash + ":"; "\\" gốc -> 4 backslash.
    text_value = _text_value(filt)
    assert text_value == "C" + "\\" * 2 + ":" + "\\" * 4 + "Video"


def test_escape_dau_phan_tram_khong_can_escape_vi_tat_expansion() -> None:
    """``expansion=none`` khiến ``%`` là ký tự thường — không được thêm backslash
    trước nó (thêm vào sẽ hiện dư một dấu \\ trên màn hình, sai)."""
    box = hook_box(TIKTOK)
    filt = build_hook_filter("Giảm 50% ngay", box, 1080, 1920)
    assert _text_value(filt) == "Giảm 50% ngay"
    assert "expansion=none" in filt


def test_escape_dau_phay() -> None:
    box = hook_box(TIKTOK)
    filt = build_hook_filter("Xem, đừng bỏ lỡ", box, 1080, 1920)
    assert _text_value(filt) == "Xem\\, đừng bỏ lỡ"


def test_escape_chuoi_tieng_viet_co_dau_giu_nguyen_khong_bi_bien_dang() -> None:
    """Chữ tiếng Việt có dấu không chứa ký tự đặc biệt nào của drawtext — phải
    hiện ra y nguyên, không bị escape nhầm hay mất dấu."""
    box = hook_box(TIKTOK)
    text = "Đừng lướt qua xem hết để biết kết quả bất ngờ!"
    filt = build_hook_filter(text, box, 1080, 1920)
    assert _text_value(filt) == text


def test_escape_tat_ca_ky_tu_nguy_hiem_cung_luc_khong_pha_cu_phap() -> None:
    """Trộn cả 5 ký tự nguy hiểm (: ' \\ % ,) trong một chuỗi — kết quả phải có
    số dấu nháy đơn CHẴN quanh mỗi cặp escape và không vỡ cấu trúc filter."""
    box = hook_box(TIKTOK)
    text = "Giá: 'giảm' 50%, còn C:\\videos"
    filt = build_hook_filter(text, box, 1080, 1920)
    # Filter phải parse được thành các cặp key=value phân tách bởi dấu ':' KHÔNG
    # bị escape (enable=, expansion=, fontsize=... vẫn còn nguyên vẹn).
    assert "expansion=none:fontsize=" in filt
    assert filt.endswith(f"enable='between(t,0,{HOOK_DURATION_SEC})'")


# ---------------------------------------------------------------------------
# build_hook_filter — pixel chỉ xuất hiện ở đây, không lọt ra hook_box
# ---------------------------------------------------------------------------


def test_build_hook_filter_doi_toa_do_sang_pixel_dung_video_size() -> None:
    box = hook_box(TIKTOK)  # (0.05, 0.06, 0.75, 0.14)
    filt = build_hook_filter("Hook", box, 1080, 1920)
    expected_x_px = round(0.05 * 1080)
    expected_y_px = round(0.06 * 1920)
    assert f"x={expected_x_px}+" in filt
    assert f"y={expected_y_px}+" in filt


# ---------------------------------------------------------------------------
# trim_slow_intro
# ---------------------------------------------------------------------------


def _cue(i: int, start: float, end: float, text: str = "x") -> Cue:
    return Cue(i=i, start=start, end=end, text=text)


def test_trim_slow_intro_cue_dau_o_giay_5_tra_ve_lon_hon_0() -> None:
    cues = [_cue(1, 5.0, 6.0), _cue(2, 6.5, 8.0)]
    assert trim_slow_intro(cues) > 0


def test_trim_slow_intro_cue_dau_o_giay_0_5_tra_ve_0() -> None:
    cues = [_cue(1, 0.5, 1.5), _cue(2, 2.0, 3.0)]
    assert trim_slow_intro(cues) == 0.0


def test_trim_slow_intro_khong_co_cue_nao_tra_ve_0() -> None:
    assert trim_slow_intro([]) == 0.0


def test_trim_slow_intro_dung_dung_bang_thoi_diem_cue_dau_tien() -> None:
    cues = [_cue(1, 4.2, 5.0)]
    assert trim_slow_intro(cues) == 4.2


def test_trim_slow_intro_nguong_tuy_chinh_qua_tham_so() -> None:
    cues = [_cue(1, 1.0, 2.0)]
    # Mặc định 2.0s thì 1.0s không bị cắt, nhưng hạ ngưỡng xuống 0.5s thì phải cắt.
    assert trim_slow_intro(cues) == 0.0
    assert trim_slow_intro(cues, max_silent_head_sec=0.5) == 1.0


def test_trim_slow_intro_lay_cue_som_nhat_khong_phai_cue_dau_danh_sach() -> None:
    """Danh sách cue không nhất thiết đã sắp xếp theo thời gian — hàm phải tự
    tìm thời điểm SỚM NHẤT, không tin vào thứ tự phần tử."""
    cues = [_cue(2, 5.0, 6.0), _cue(1, 0.5, 1.0)]
    assert trim_slow_intro(cues) == 0.0
