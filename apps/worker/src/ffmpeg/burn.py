"""Burn phụ đề và tạo bản proxy để preview."""

from __future__ import annotations

from pathlib import Path

from reup_core.paths import tmp_sibling

from ..config import get_settings
from .runner import run_ffmpeg


def _escape_for_filter(path: Path) -> str:
    """Escape đường dẫn cho filter subtitles của FFmpeg.

    Dấu ``:`` và ``\\`` trong đường dẫn sẽ phá cú pháp filter nếu không escape.
    """
    text = str(path)
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    return text


def build_force_style() -> str:
    """Kiểu chữ phụ đề tiếng Việt: chữ vàng, viền đen dày, đặt trên vùng UI."""
    s = get_settings()
    parts = [
        f"FontName={s.sub_font}",
        f"FontSize={s.sub_font_size}",
        "PrimaryColour=&H006BE8FF",  # vàng (BGR)
        "OutlineColour=&H00000000",
        "BorderStyle=1",
        "Outline=3",
        "Shadow=1",
        "Alignment=2",  # căn giữa, sát đáy
        "MarginV=120",  # đẩy lên tránh vùng caption của TikTok
        "Bold=1",
    ]
    return ",".join(parts)


def burn_subtitles(src: Path, srt: Path, dst: Path, *, timeout: int | None = None) -> Path:
    """Ghi phụ đề vào khung hình.

    Ghi ra file tạm rồi rename để không bao giờ có file dở dang ở đường dẫn đích.
    """
    tmp = tmp_sibling(dst)
    tmp.parent.mkdir(parents=True, exist_ok=True)

    vf = f"subtitles='{_escape_for_filter(srt)}':force_style='{build_force_style()}'"
    run_ffmpeg(
        [
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
        ],
        timeout=timeout,
    )
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


def make_proxy(src: Path, dst: Path) -> Path:
    """Bản 540p nhẹ để tua mượt trên web. Render cuối vẫn dùng bản gốc."""
    tmp = tmp_sibling(dst)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i", str(src),
            "-vf", "scale=-2:540",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
            "-c:a", "aac", "-b:a", "96k",
            "-movflags", "+faststart",
            str(tmp),
        ]
    )
    tmp.replace(dst)
    return dst
