"""Sinh file ASS để burn phụ đề — hàm thuần, không chạm ffmpeg/DB/Celery.

VÌ SAO KHÔNG DÙNG ``subtitles=file.srt:force_style=...`` NHƯ TRƯỚC

FFmpeg quy đổi SRT sang ASS bằng một khung toạ độ CỐ ĐỊNH:

    PlayResX: 384
    PlayResY: 288

Mọi con số trong ``force_style`` (``FontSize``, ``MarginV``, ``Outline``) nằm
trong hệ đó, rồi libass scale tất cả lên kích thước khung hình thật. Với khung
1080×1920 hệ số là 1920/288 ≈ 6,67 lần — nên ``MarginV=346`` (pixel tính từ
``platform_limits.safe_area``) hoá thành lề ~2307px, lớn hơn cả chiều cao
khung, và phụ đề bị đẩy hẳn ra ngoài hình. Đo bằng ffmpeg thật ngày
2026-08-14: MỌI bản render 1080×1920 đều không có phụ đề, dù file SRT đúng.

Ở đây ta tự sinh ASS với ``PlayResX``/``PlayResY`` bằng ĐÚNG khung đích. Khi
đó đơn vị của script chính là pixel: ``margin_v_pixels()`` và
``max_line_width_pixels()`` dùng được nguyên văn, không cần quy đổi, và không
còn phụ thuộc con số 384×288 mà một phiên bản ffmpeg nào đó có thể đổi.

Xem ``tests/test_subtitle_ass.py`` và ``scripts/try_burn.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings
from ..errors import InvalidFrameSizeError
from .cues import Cue
from .shortform.safe_area import SafeArea, margin_v_pixels

#: Khung tham chiếu để quy đổi cỡ chữ: video dọc 9:16 1080×1920 — mặc định của
#: dự án (xem CLAUDE.md, "Video dọc 9:16 là mặc định"). ``SUB_FONT_SIZE`` trong
#: cấu hình là cỡ chữ TÍNH BẰNG PIXEL Ở KHUNG NÀY; khung khác được quy đổi theo
#: tỉ lệ chiều cao để chữ trông y hệt ở mọi độ phân giải.
SUB_REFERENCE_HEIGHT = 1920

#: Viền và bóng cũng tính theo pixel ở khung tham chiếu, quy đổi cùng cách với
#: cỡ chữ — viền dày 3px ở 1920 mà giữ nguyên 3px ở 480 sẽ nuốt mất nét chữ.
_OUTLINE_AT_REFERENCE = 3
_SHADOW_AT_REFERENCE = 1

#: Màu ASS theo thứ tự &HAABBGGRR (xanh-lục-đỏ ngược so với HTML).
#: Trắng viền đen — chuẩn video ngắn, đọc được trên cả nền sáng lẫn nền tối.
#: Trước đây dùng vàng ``&H006BE8FF``; vàng chìm hẳn khi nền sáng.
_PRIMARY_COLOUR = "&H00FFFFFF"  # trắng
_OUTLINE_COLOUR = "&H00000000"  # đen

#: Căn giữa, sát đáy (ASS numpad layout: 2 = bottom-center).
_ALIGNMENT_BOTTOM_CENTER = 2

#: Thứ tự cột BẮT BUỘC của ASS v4.00+. Lệch một cột là libass đọc sai toàn bộ
#: kiểu chữ mà không hề báo lỗi.
_STYLE_FORMAT = (
    "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, "
    "Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, "
    "Encoding"
)
_EVENT_FORMAT = "Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"

#: ASS dùng -1 cho "bật", 0 cho "tắt" — không phải 1/0.
_ASS_TRUE = -1
_ASS_FALSE = 0


@dataclass(frozen=True)
class AssStyle:
    """Kiểu chữ phụ đề. MỌI số đo tính bằng PIXEL của khung đích."""

    font_name: str
    font_size: int
    outline: int
    shadow: int
    margin_v: int
    margin_l: int
    margin_r: int
    bold: bool = True


def _scale_to_frame(value_at_reference: int, height: int) -> int:
    """Quy đổi một số đo từ khung tham chiếu sang khung cao ``height`` pixel."""
    return max(1, round(value_at_reference * height / SUB_REFERENCE_HEIGHT))


def _kiem_kich_thuoc(width: int | None, height: int | None) -> tuple[int, int]:
    """Chốt chặn: thiếu hoặc sai kích thước khung thì dừng ngay, có lý do rõ.

    Nhận ``None`` vì kích thước đi từ bước ``probe`` xuống và về lý thuyết có
    thể trống — nhưng render tiếp trong tình trạng đó chỉ cho ra video mất
    phụ đề, nên chặn ở đây.
    """
    if width is None or height is None or width <= 0 or height <= 0:
        raise InvalidFrameSizeError(
            f"Kích thước khung không hợp lệ: {width}x{height} — không tính được "
            "lề và cỡ chữ phụ đề. Kiểm tra bước probe đã điền width/height chưa."
        )
    return width, height


def build_ass_style(
    safe: SafeArea,
    width: int | None,
    height: int | None,
    *,
    font_name: str | None = None,
    font_size: int | None = None,
) -> AssStyle:
    """Dựng kiểu chữ từ vùng an toàn của nền tảng đích.

    ``safe`` đọc từ bảng ``platform_limits`` (luật số 5 CLAUDE.md) — lề dưới
    né caption, lề trái/phải né cột nút tim/bình luận/chia sẻ.
    """
    width, height = _kiem_kich_thuoc(width, height)
    settings = get_settings()
    size_at_reference = font_size if font_size is not None else settings.sub_font_size
    return AssStyle(
        font_name=font_name if font_name is not None else settings.sub_font,
        font_size=_scale_to_frame(size_at_reference, height),
        outline=_scale_to_frame(_OUTLINE_AT_REFERENCE, height),
        shadow=_scale_to_frame(_SHADOW_AT_REFERENCE, height),
        margin_v=margin_v_pixels(safe, height),
        #: Lề ngang ĐỐI XỨNG, lấy ``safe.left`` cho cả hai bên. Cố tình KHÔNG
        #: dùng ``safe.right``: con số đó (20% với TikTok) mô tả cột nút tim/
        #: bình luận/chia sẻ, mà cột đó nằm PHÍA TRÊN dải phụ đề — áp vào phụ
        #: đề chỉ làm chữ lệch tâm sang trái, thấy rõ trên khung hình render
        #: thật. Vùng an toàn phải/trái vẫn được ``hook_box`` dùng đúng nghĩa
        #: cho lớp hook ở dải trên.
        margin_l=round(safe.left * width),
        margin_r=round(safe.left * width),
    )


def _timestamp(seconds: float) -> str:
    """Mốc giờ ASS: ``H:MM:SS.cc`` (phần trăm giây), khác SRT ``HH:MM:SS,mmm``."""
    total = max(0.0, seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    centis = round(secs * 100)
    #: Làm tròn có thể đẩy 59.999 -> 6000 centi giây; dồn ngược lên phút.
    if centis >= 6000:
        centis -= 6000
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        hours += 1
    return f"{int(hours)}:{int(minutes):02d}:{centis // 100:02d}.{centis % 100:02d}"


def _escape_text(text: str) -> str:
    """Đưa lời thoại về dạng an toàn cho một dòng ``Dialogue``.

    - ``{`` ``}`` là khối lệnh ghi đè kiểu chữ của ASS: lời thoại chứa ngoặc
      nhọn mà để nguyên thì libass nuốt cả đoạn, câu biến mất khỏi màn hình.
      Đổi sang ngoặc tròn — thà sai một ký tự còn hơn mất cả câu.
    - Xuống dòng thật phải thành ``\\N``; ký tự ``\\n`` sót lại sẽ cắt dòng
      Dialogue làm đôi và libass đọc phần sau thành rác.
    """
    return (
        text.replace("{", "(")
        .replace("}", ")")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\N")
    )


def build_ass(cues: list[Cue], *, width: int | None, height: int | None, style: AssStyle) -> str:
    """Trả về nội dung file ASS hoàn chỉnh cho khung ``width``×``height``."""
    width, height = _kiem_kich_thuoc(width, height)

    style_values = [
        "Default",
        style.font_name,
        str(style.font_size),
        _PRIMARY_COLOUR,
        _PRIMARY_COLOUR,
        _OUTLINE_COLOUR,
        _OUTLINE_COLOUR,
        str(_ASS_TRUE if style.bold else _ASS_FALSE),
        str(_ASS_FALSE),  # Italic
        str(_ASS_FALSE),  # Underline
        str(_ASS_FALSE),  # StrikeOut
        "100",  # ScaleX
        "100",  # ScaleY
        "0",  # Spacing
        "0",  # Angle
        "1",  # BorderStyle: 1 = viền + bóng
        str(style.outline),
        str(style.shadow),
        str(_ALIGNMENT_BOTTOM_CENTER),
        str(style.margin_l),
        str(style.margin_r),
        str(style.margin_v),
        "1",  # Encoding
    ]

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        #: 0 = tự xuống dòng, dòng trên dài hơn dòng dưới.
        "WrapStyle: 0",
        #: Viền/bóng scale cùng khung hình thay vì giữ nguyên pixel.
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        f"Format: {_STYLE_FORMAT}",
        "Style: " + ",".join(style_values),
        "",
        "[Events]",
        f"Format: {_EVENT_FORMAT}",
    ]
    for cue in cues:
        lines.append(
            f"Dialogue: 0,{_timestamp(cue.start)},{_timestamp(cue.end)},Default,,0,0,0,,"
            f"{_escape_text(cue.text)}"
        )
    return "\n".join(lines) + "\n"


def write_ass(
    cues: list[Cue], path: Path, *, width: int | None, height: int | None, style: AssStyle
) -> Path:
    """Ghi file ASS (UTF-8, không BOM) và trả về đường dẫn."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_ass(cues, width=width, height=height, style=style), encoding="utf-8")
    return path
