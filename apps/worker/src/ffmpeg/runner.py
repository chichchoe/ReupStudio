"""Wrapper FFmpeg. Không dùng thư viện bọc — che mất thông báo lỗi."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from reup_core.logging import get_logger

from ..config import get_settings
from ..errors import FFmpegError

log = get_logger(__name__)


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegError("Không tìm thấy ffmpeg trong PATH. Cài FFmpeg 7 trước.")
    return path


def ffprobe_bin() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise FFmpegError("Không tìm thấy ffprobe trong PATH.")
    return path


def run_ffmpeg(args: list[str], *, timeout: int | None = None) -> str:
    """Chạy ffmpeg với danh sách tham số (KHÔNG dùng shell=True).

    Khi lỗi giữ 2000 ký tự cuối stderr — FFmpeg báo lỗi ở cuối.
    """
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", *args]
    log.debug("ffmpeg.run", cmd=" ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout or get_settings().ffmpeg_timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"FFmpeg quá thời gian cho phép: {exc}") from exc

    if proc.returncode != 0:
        raise FFmpegError(proc.stderr[-2000:] or "ffmpeg thất bại không rõ lý do")
    return proc.stdout


def atomic_output(dst: Path, args_builder) -> Path:
    """Ghi ra file tạm rồi rename — tránh file dở dang bị coi là hợp lệ.

    ``args_builder(tmp_path)`` phải trả về danh sách tham số ffmpeg.
    """
    from reup_core.paths import tmp_sibling

    tmp = tmp_sibling(dst)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(args_builder(tmp))
    if not tmp.exists() or tmp.stat().st_size == 0:
        raise FFmpegError(f"FFmpeg không tạo ra file: {dst.name}")
    tmp.replace(dst)
    return dst
