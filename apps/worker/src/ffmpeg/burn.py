"""Burn phụ đề và tạo bản proxy để preview."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from reup_core.paths import tmp_sibling

from ..config import get_settings
from ..pipeline.shortform.safe_area import SafeArea, margin_v_pixels
from .runner import run_ffmpeg, run_ffmpeg_progress

#: Lề dưới cũ, dùng trước khi bảng platform_limits tồn tại. CHỈ còn dùng khi
#: không truyền ``safe``/``video_height`` — giữ để không phá hành vi của các
#: chỗ gọi sẵn có (backward-compat, xem test_safe_area.py).
_LEGACY_MARGIN_V_PX = 120


def _escape_for_filter(path: Path) -> str:
    """Escape đường dẫn cho filter subtitles của FFmpeg.

    Dấu ``:`` và ``\\`` trong đường dẫn sẽ phá cú pháp filter nếu không escape.
    """
    text = str(path)
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    return text


def build_force_style(
    safe: SafeArea | None = None, video_height: int | None = None
) -> str:
    """Kiểu chữ phụ đề tiếng Việt: chữ vàng, viền đen dày, đặt trên vùng UI.

    Truyền cả ``safe`` (vùng an toàn đọc từ bảng ``platform_limits``) lẫn
    ``video_height`` thì ``MarginV`` tính từ ``margin_v_pixels`` — không còn
    số cứng. Thiếu một trong hai thì giữ nguyên lề mặc định cũ, để các chỗ
    gọi sẵn có (chưa truyền hai tham số này) không đổi hành vi.
    """
    s = get_settings()
    if safe is not None and video_height is not None:
        margin_v = margin_v_pixels(safe, video_height)
    else:
        margin_v = _LEGACY_MARGIN_V_PX
    parts = [
        f"FontName={s.sub_font}",
        f"FontSize={s.sub_font_size}",
        "PrimaryColour=&H006BE8FF",  # vàng (BGR)
        "OutlineColour=&H00000000",
        "BorderStyle=1",
        "Outline=3",
        "Shadow=1",
        "Alignment=2",  # căn giữa, sát đáy
        f"MarginV={margin_v}",
        "Bold=1",
    ]
    return ",".join(parts)


def burn_subtitles(
    src: Path,
    srt: Path,
    dst: Path,
    *,
    timeout: int | None = None,
    progress_cb: Callable[[int], None] | None = None,
    duration_sec: float | None = None,
    safe: SafeArea | None = None,
    video_height: int | None = None,
) -> Path:
    """Ghi phụ đề vào khung hình.

    Ghi ra file tạm rồi rename để không bao giờ có file dở dang ở đường dẫn đích.
    Truyền cả ``progress_cb`` lẫn ``duration_sec`` thì bắn tiến trình qua
    ``run_ffmpeg_progress``; thiếu một trong hai thì giữ nguyên hành vi cũ.
    ``safe``/``video_height`` được chuyển thẳng cho ``build_force_style`` để
    đặt lề dưới theo vùng an toàn của nền tảng đích (xem module đó).
    """
    tmp = tmp_sibling(dst)
    tmp.parent.mkdir(parents=True, exist_ok=True)

    force_style = build_force_style(safe, video_height)
    vf = f"subtitles='{_escape_for_filter(srt)}':force_style='{force_style}'"
    args = [
        "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(tmp),
    ]
    if progress_cb is not None and duration_sec is not None:
        run_ffmpeg_progress(
            args, duration_sec=duration_sec, on_percent=progress_cb, timeout=timeout
        )
    else:
        run_ffmpeg(args, timeout=timeout)
    tmp.replace(dst)
    return dst


def extract_audio(src: Path, dst: Path) -> Path:
    """Tách audio 16kHz mono — định dạng Whisper cần."""
    tmp = tmp_sibling(dst)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        ["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)]
    )
    tmp.replace(dst)
    return dst


def make_proxy(
    src: Path,
    dst: Path,
    *,
    progress_cb: Callable[[int], None] | None = None,
    duration_sec: float | None = None,
) -> Path:
    """Bản 540p nhẹ để tua mượt trên web. Render cuối vẫn dùng bản gốc."""
    tmp = tmp_sibling(dst)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-i", str(src),
        "-vf", "scale=-2:540",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        str(tmp),
    ]
    if progress_cb is not None and duration_sec is not None:
        run_ffmpeg_progress(args, duration_sec=duration_sec, on_percent=progress_cb)
    else:
        run_ffmpeg(args)
    tmp.replace(dst)
    return dst
