"""Sinh file ASS cho bước burn phụ đề — khoá lại lỗi phụ đề bay ra ngoài khung.

Bối cảnh (đo được bằng ffmpeg thật, 2026-08-14): trước đây bước burn dùng
``subtitles=file.srt:force_style=...``. FFmpeg quy đổi SRT sang ASS với khung
toạ độ CỐ ĐỊNH ``PlayResX=384, PlayResY=288``, rồi libass scale toàn bộ lên
kích thước video. Mọi con số trong ``force_style`` vì thế nằm trong hệ 384×288,
KHÔNG phải pixel của khung hình.

Nhưng ``margin_v_pixels()`` trả về **pixel của video**. Với khung 1080×1920, hệ
số scale là 1920/288 ≈ 6,67 lần:

- ``FontSize=54``  -> chữ cao thực tế ~360px
- ``MarginV=346``  -> lề dưới thực tế ~2307px, lớn hơn cả khung hình

nên phụ đề bị đẩy hẳn ra ngoài hình: mọi bản render 1080×1920 đều KHÔNG có
phụ đề, dù file SRT hoàn toàn đúng. Tiêu chí "Sub không nằm dưới caption
TikTok" của M4-WK-02 chưa từng đạt.

Cách sửa mà bộ test này khoá lại: tự sinh file ASS với ``PlayResX``/``PlayResY``
bằng ĐÚNG khung đích. Khi đó đơn vị của script CHÍNH LÀ pixel — các hàm thuần
sẵn có (``margin_v_pixels``, ``max_line_width_pixels``) trở nên đúng nguyên
văn, và không còn phụ thuộc con số 384×288 do ffmpeg tự đặt.
"""

from __future__ import annotations

import pytest

from src.pipeline.cues import Cue
from src.pipeline.shortform.safe_area import SafeArea, margin_v_pixels
from src.pipeline.subtitle_ass import (
    SUB_REFERENCE_HEIGHT,
    build_ass,
    build_ass_style,
    write_ass,
)

TIKTOK = SafeArea(top=0.06, bottom=0.18, left=0.05, right=0.20)
CUES = [Cue(0, 0.18, 2.5, "Xin chào"), Cue(1, 2.5, 4.0, "dòng một\ndòng hai")]


def _fields(text: str, prefix: str) -> list[str]:
    """Lấy các trường của dòng bắt đầu bằng ``prefix`` (VD ``Style:``)."""
    for line in text.splitlines():
        if line.startswith(prefix):
            return [f.strip() for f in line[len(prefix) :].split(",")]
    raise AssertionError(f"không tìm thấy dòng {prefix!r} trong ASS")


def _style_value(text: str, key: str) -> str:
    """Đọc giá trị một cột của dòng ``Style:`` theo tên cột ở dòng ``Format:``."""
    names = _fields(text, "Format:")
    values = _fields(text, "Style:")
    return values[names.index(key)]


# --- Chính giữa vấn đề: hệ toạ độ ---------------------------------------


def test_play_res_bang_dung_khung_dich() -> None:
    """Gốc của lỗi. PlayRes phải bằng khung hình thật, không phải 384×288."""
    ass = build_ass(CUES, width=1080, height=1920, style=build_ass_style(TIKTOK, 1080, 1920))
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass


def test_margin_v_dung_bang_pixel_cua_vung_an_toan() -> None:
    """PlayRes đã bằng khung nên MarginV là pixel thật, dùng thẳng số của safe area."""
    style = build_ass_style(TIKTOK, 1080, 1920)
    ass = build_ass(CUES, width=1080, height=1920, style=style)
    assert style.margin_v == margin_v_pixels(TIKTOK, 1920) == 346
    assert _style_value(ass, "MarginV") == "346"


def test_margin_v_luon_nho_hon_chieu_cao_khung() -> None:
    """Chốt chặn chống tái diễn: lề dưới lớn hơn khung = phụ đề bay ra ngoài hình."""
    for height in (240, 720, 1280, 1920, 2160):
        style = build_ass_style(TIKTOK, round(height * 9 / 16), height)
        assert style.margin_v < height


def test_le_trai_phai_doi_xung_de_chu_can_giua_khung() -> None:
    """Lề ngang lấy ``safe.left`` cho CẢ HAI bên, không dùng ``safe.right``.

    ``safe.right`` (20% với TikTok) mô tả cột nút tim/bình luận/chia sẻ, mà cột
    đó nằm PHÍA TRÊN dải phụ đề. Áp nó vào phụ đề chỉ làm chữ lệch tâm sang
    trái — nhìn thấy rõ trên khung hình render thật ngày 2026-08-14.
    """
    style = build_ass_style(TIKTOK, 1080, 1920)
    assert style.margin_l == style.margin_r == round(0.05 * 1080) == 54


def test_chu_mau_trang() -> None:
    """Trắng viền đen là chuẩn video ngắn — đọc được trên cả nền sáng lẫn tối.

    Màu vàng dùng trước đây chìm hẳn trên nền sáng.
    """
    ass = build_ass(CUES, width=1080, height=1920, style=build_ass_style(TIKTOK, 1080, 1920))
    assert _style_value(ass, "PrimaryColour") == "&H00FFFFFF"
    assert _style_value(ass, "OutlineColour") == "&H00000000"


# --- Cỡ chữ theo khung, không phải số cứng -------------------------------


def test_co_chu_bang_gia_tri_cau_hinh_o_khung_chuan() -> None:
    style = build_ass_style(TIKTOK, 1080, SUB_REFERENCE_HEIGHT, font_size=54)
    assert style.font_size == 54


def test_co_chu_ti_le_thuan_voi_chieu_cao_khung() -> None:
    """Khung cao một nửa thì chữ nhỏ một nửa — nhìn giống nhau ở mọi độ phân giải.

    Không có phần này thì cỡ chữ 54 vừa mắt ở 1920 sẽ chiếm 22% chiều cao của
    khung 240 (đúng cái đã thấy trên bản master đầu tiên).
    """
    nua = build_ass_style(TIKTOK, 540, SUB_REFERENCE_HEIGHT // 2, font_size=54)
    assert nua.font_size == 27


# --- Định dạng file ------------------------------------------------------


def test_moc_thoi_gian_dung_dinh_dang_ass() -> None:
    """ASS dùng ``H:MM:SS.cc`` (phần trăm giây), không phải ``HH:MM:SS,mmm`` của SRT."""
    ass = build_ass(
        [Cue(0, 3725.5, 3726.25, "A")],
        width=1080,
        height=1920,
        style=build_ass_style(TIKTOK, 1080, 1920),
    )
    assert "Dialogue: 0,1:02:05.50,1:02:06.25,Default" in ass


def test_xuong_dong_thanh_ky_hieu_cua_ass() -> None:
    ass = build_ass(CUES, width=1080, height=1920, style=build_ass_style(TIKTOK, 1080, 1920))
    assert "dòng một\\Ndòng hai" in ass
    #: Ký tự xuống dòng thật chỉ được phép nằm giữa các dòng của file, không
    #: nằm trong một dòng Dialogue — nếu lọt vào, libass đọc thành dòng rác.
    for line in ass.splitlines():
        if line.startswith("Dialogue:"):
            assert "\n" not in line


def test_dau_ngoac_nhon_trong_loi_thoai_khong_thanh_lenh_dinh_dang() -> None:
    """``{...}`` trong ASS là khối lệnh ghi đè kiểu chữ — lời thoại có ngoặc
    nhọn phải bị vô hiệu hoá, nếu không cả câu biến mất khỏi màn hình."""
    ass = build_ass(
        [Cue(0, 0.0, 1.0, "giá {rẻ} lắm")],
        width=1080,
        height=1920,
        style=build_ass_style(TIKTOK, 1080, 1920),
    )
    assert "{" not in ass.split("[Events]")[1]


def test_so_cot_cua_dong_style_khop_dong_format() -> None:
    """Lệch một cột là libass đọc sai toàn bộ kiểu chữ mà không báo lỗi."""
    ass = build_ass(CUES, width=1080, height=1920, style=build_ass_style(TIKTOK, 1080, 1920))
    assert len(_fields(ass, "Style:")) == len(_fields(ass, "Format:"))


def test_write_ass_ghi_file_utf8_va_tra_ve_duong_dan(tmp_path) -> None:
    path = write_ass(
        CUES,
        tmp_path / "sub.vi.ass",
        width=1080,
        height=1920,
        style=build_ass_style(TIKTOK, 1080, 1920),
    )
    assert path.exists()
    noi_dung = path.read_text(encoding="utf-8")
    assert "Xin chào" in noi_dung
    assert noi_dung.startswith("[Script Info]")


@pytest.mark.parametrize("height", [0, -1])
def test_chieu_cao_khong_hop_le_thi_bao_loi(height: int) -> None:
    """Chia cho 0 khi quy đổi cỡ chữ — báo lỗi rõ thay vì ném ZeroDivisionError."""
    from src.errors import InvalidFrameSizeError

    with pytest.raises(InvalidFrameSizeError):
        build_ass_style(TIKTOK, 1080, height)
