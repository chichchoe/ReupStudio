"""Đẩy phụ đề khỏi vùng UI của nền tảng (M4-WK-02).

Hàm THUẦN: không đụng DB, không đụng ffmpeg, không import celery. Nhận
``SafeArea`` — vùng UI cần tránh, toạ độ phần trăm khung hình 0–1, đọc từ
bảng ``platform_limits`` ở tầng ``tasks/`` (tầng được phép chạm DB) — rồi quy
đổi sang pixel hoặc kiểm tra một hộp phụ đề có nằm trọn trong vùng an toàn
hay không.

Trước khi có module này, ``apps/worker/src/ffmpeg/burn.py::build_force_style``
hardcode ``MarginV=120`` — vi phạm luật số 5 CLAUDE.md ("Giới hạn nền tảng
đọc từ bảng `platform_limits`, không hardcode trong code"). Module này là nơi
đầu tiên tiêu thụ ``platform_limits.safe_area`` để gỡ số cứng đó.

Xem ``tests/test_safe_area.py``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SafeArea:
    """Vùng UI của nền tảng cần tránh, toạ độ phần trăm khung hình 0–1.

    Ví dụ TikTok: ``{"top": 0.06, "bottom": 0.18, "left": 0.05, "right": 0.20}``
    — phụ đề không được nằm trong 6% trên, 18% dưới (caption của TikTok), 5%
    trái, 20% phải (cột nút tim/bình luận/chia sẻ) của khung hình.
    """

    top: float
    bottom: float
    left: float
    right: float


def margin_v_pixels(safe: SafeArea, video_height: int) -> int:
    """Lề dưới tính bằng pixel cho ASS/libass, từ vùng an toàn phần trăm.

    Làm tròn theo quy tắc làm tròn chuẩn (``round``) — sai số tối đa nửa pixel
    nên không lệch quá 1 pixel khi so lại với tỷ lệ phần trăm gốc.
    """
    return round(safe.bottom * video_height)


def max_line_width_pixels(safe: SafeArea, video_width: int) -> int:
    """Bề ngang tối đa của dòng phụ đề sau khi trừ lề trái/phải, theo pixel."""
    return round(video_width * (1 - safe.left - safe.right))


def fits_in_safe_area(box: tuple[float, float, float, float], safe: SafeArea) -> bool:
    """``box`` = ``(x, y, w, h)`` theo phần trăm 0–1 (gốc toạ độ ở góc trên-trái).

    Trả về ``True`` nếu hộp nằm trọn trong vùng an toàn — không lấn vào vùng
    UI ở bất kỳ cạnh nào (trên/dưới/trái/phải).
    """
    x, y, w, h = box
    return x >= safe.left and y >= safe.top and x + w <= 1 - safe.right and y + h <= 1 - safe.bottom
