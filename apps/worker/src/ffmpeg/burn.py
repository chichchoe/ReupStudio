"""Burn phụ đề và tạo bản proxy để preview."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from reup_core.logging import get_logger
from reup_core.paths import tmp_sibling

from .runner import run_ffmpeg, run_ffmpeg_progress

log = get_logger(__name__)


def _escape_for_filter(path: Path) -> str:
    """Escape đường dẫn cho filter subtitles của FFmpeg.

    Dấu ``:`` và ``\\`` trong đường dẫn sẽ phá cú pháp filter nếu không escape.
    """
    text = str(path)
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    return text


def burn_subtitles(
    src: Path,
    subtitle_file: Path,
    dst: Path,
    *,
    timeout: int | None = None,
    progress_cb: Callable[[int], None] | None = None,
    duration_sec: float | None = None,
    start: float | None = None,
    hook_filter: str | None = None,
) -> Path:
    """Ghi phụ đề vào khung hình.

    ``subtitle_file`` là file **ASS** do ``pipeline/subtitle_ass.py`` sinh ra:
    kiểu chữ, cỡ chữ và lề nằm SẴN trong file, tính bằng pixel của khung đích.
    Ở đây KHÔNG còn ``force_style`` — trước đây hàm này burn từ SRT kèm
    ``force_style``, mà số trong ``force_style`` bị libass hiểu theo khung
    384×288 do ffmpeg tự đặt cho SRT, không phải pixel thật; hậu quả là lề dưới
    346px hoá thành ~2307px và phụ đề bay hẳn ra ngoài mọi khung 1080×1920.
    Đừng đưa ``force_style`` trở lại (xem ``tests/test_burn_filter.py``).

    Ghi ra file tạm rồi rename để không bao giờ có file dở dang ở đường dẫn đích.
    Truyền cả ``progress_cb`` lẫn ``duration_sec`` thì bắn tiến trình qua
    ``run_ffmpeg_progress``; thiếu một trong hai thì giữ nguyên hành vi cũ.

    ``start`` (giây, tuỳ chọn) cắt một ĐOẠN của ``src`` thay vì burn cả video —
    dùng khi render một tập của ``render_variants`` (M4-WK-05). Đoạn dài
    ``duration_sec`` giây kể từ ``start``; ``srt`` phải đã được dịch mốc thời
    gian về gốc 0 của đoạn đó (xem ``pipeline/render.py::render_variant``).
    Không truyền ``start`` thì burn nguyên video như trước (backward-compat).

    ``hook_filter`` (tuỳ chọn, M4-WK-05b): chuỗi filter ``drawtext`` dựng sẵn
    bởi ``pipeline/shortform/hook.py::build_hook_filter`` — nối thêm vào SAU
    filter ``subtitles`` trong cùng một ``-vf`` (một lượt encode, không chạy
    ffmpeg hai lần). Hai filter phủ hai vùng khung hình tách biệt (hook ở
    trên, phụ đề sát đáy — xem ``hook_box``) nên thứ tự áp giữa chúng không
    ảnh hưởng kết quả hiển thị. ``src`` (tham số ``src`` của hàm này) PHẢI đã
    được đổi sang khung ĐÍCH từ trước (xem ``pipeline/render.py::render_variant``,
    lý do trong docstring ở đó) — tọa độ trong ``hook_filter`` tính theo khung
    đích, đưa vào khung còn ở tỉ lệ nguồn sẽ lệch vị trí.
    """
    tmp = tmp_sibling(dst)
    tmp.parent.mkdir(parents=True, exist_ok=True)

    vf = f"subtitles='{_escape_for_filter(subtitle_file)}'"
    if hook_filter:
        vf = f"{vf},{hook_filter}"
    args: list[str] = []
    if start is not None and start > 0:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src)]
    if start is not None and duration_sec is not None:
        args += ["-t", f"{duration_sec:.3f}"]
    args += [
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
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
    run_ffmpeg(["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)])
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
        "-i",
        str(src),
        "-vf",
        "scale=-2:540",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    if progress_cb is not None and duration_sec is not None:
        run_ffmpeg_progress(args, duration_sec=duration_sec, on_percent=progress_cb)
    else:
        run_ffmpeg(args)
    tmp.replace(dst)
    return dst
