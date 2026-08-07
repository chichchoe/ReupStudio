"""Bước render: burn phụ đề tiếng Việt vào video."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from reup_core.logging import get_logger
from reup_core.paths import out_video, proxy_path, subtitle_path

from ..ffmpeg.burn import burn_subtitles, make_proxy
from .cues import Cue, write_srt
from .shortform.safe_area import SafeArea

log = get_logger(__name__)


def render_with_subtitles(
    video_id: str,
    source: Path,
    cues: list[Cue],
    *,
    target: str = "master",
    progress_cb: Callable[[int], None] | None = None,
    duration_sec: float | None = None,
    safe: SafeArea | None = None,
    video_height: int | None = None,
) -> Path:
    """Ghi SRT rồi burn vào video, trả về đường dẫn file kết quả.

    ``safe``/``video_height`` (tuỳ chọn) được chuyển thẳng cho
    ``burn_subtitles`` để đặt lề dưới phụ đề theo vùng an toàn của nền tảng
    đích — không truyền thì giữ lề mặc định cũ.
    """
    srt = write_srt(cues, subtitle_path(video_id, "vi"))
    dst = out_video(video_id, target)

    if dst.exists() and dst.stat().st_size > 0:
        log.info("render.skip_existing", path=str(dst))
        return dst

    burn_subtitles(
        source,
        srt,
        dst,
        progress_cb=progress_cb,
        duration_sec=duration_sec,
        safe=safe,
        video_height=video_height,
    )
    log.info("render.done", path=str(dst), size=dst.stat().st_size)
    return dst


def build_proxy(
    video_id: str,
    source: Path,
    *,
    progress_cb: Callable[[int], None] | None = None,
    duration_sec: float | None = None,
) -> Path | None:
    """Bản 540p cho preview trên web. Lỗi ở đây không được làm hỏng cả job."""
    dst = proxy_path(video_id)
    if dst.exists():
        return dst
    try:
        return make_proxy(source, dst, progress_cb=progress_cb, duration_sec=duration_sec)
    except Exception as exc:
        log.warning("proxy.failed", error=str(exc))
        return None
