"""Burn phụ đề và tạo bản proxy để preview."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from reup_core.logging import get_logger
from reup_core.paths import tmp_sibling

from ..config import get_settings
from ..pipeline.shortform.safe_area import SafeArea, margin_v_pixels
from .runner import run_ffmpeg, run_ffmpeg_progress

log = get_logger(__name__)

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
        # Có safe HOẶC video_height (không phải cả hai) nghĩa là chỗ gọi định
        # dùng vùng an toàn nhưng thiếu dữ liệu (VD: video.height chưa có lúc
        # render) — khác với chỗ gọi cũ chủ động không truyền gì cả. Log rõ để
        # không lặng lẽ rơi về lề cứng mà không ai biết.
        if safe is not None or video_height is not None:
            log.warning(
                "burn.margin_v.thieu_du_lieu_dung_le_du_phong",
                has_safe=safe is not None,
                has_video_height=video_height is not None,
                margin_v_du_phong=_LEGACY_MARGIN_V_PX,
            )
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
    start: float | None = None,
) -> Path:
    """Ghi phụ đề vào khung hình.

    Ghi ra file tạm rồi rename để không bao giờ có file dở dang ở đường dẫn đích.
    Truyền cả ``progress_cb`` lẫn ``duration_sec`` thì bắn tiến trình qua
    ``run_ffmpeg_progress``; thiếu một trong hai thì giữ nguyên hành vi cũ.
    ``safe``/``video_height`` được chuyển thẳng cho ``build_force_style`` để
    đặt lề dưới theo vùng an toàn của nền tảng đích (xem module đó).

    ``start`` (giây, tuỳ chọn) cắt một ĐOẠN của ``src`` thay vì burn cả video —
    dùng khi render một tập của ``render_variants`` (M4-WK-05). Đoạn dài
    ``duration_sec`` giây kể từ ``start``; ``srt`` phải đã được dịch mốc thời
    gian về gốc 0 của đoạn đó (xem ``pipeline/render.py::render_variant``).
    Không truyền ``start`` thì burn nguyên video như trước (backward-compat).
    """
    tmp = tmp_sibling(dst)
    tmp.parent.mkdir(parents=True, exist_ok=True)

    force_style = build_force_style(safe, video_height)
    vf = f"subtitles='{_escape_for_filter(srt)}':force_style='{force_style}'"
    args: list[str] = []
    if start is not None and start > 0:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src)]
    if start is not None and duration_sec is not None:
        args += ["-t", f"{duration_sec:.3f}"]
    args += [
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


def trim_video(
    src: Path,
    dst: Path,
    *,
    start: float = 0.0,
    duration_sec: float | None = None,
    timeout: int | None = None,
) -> Path:
    """Cắt một đoạn của ``src`` MÀ KHÔNG burn phụ đề (video không lời thoại).

    Dùng ``-c copy`` (không re-encode) để nhanh — chấp nhận cắt lệch tới khung
    hình khoá (keyframe) gần nhất, đủ tốt cho ranh giới tập vì mốc cắt luôn lấy
    từ khoảng lặng giữa câu, không cần chính xác tới từng khung hình.
    """
    tmp = tmp_sibling(dst)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    args: list[str] = []
    if start > 0:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src)]
    if duration_sec is not None:
        args += ["-t", f"{duration_sec:.3f}"]
    args += ["-c", "copy", "-movflags", "+faststart", str(tmp)]
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
