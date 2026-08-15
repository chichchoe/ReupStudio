"""Wrapper FFmpeg. Không dùng thư viện bọc — che mất thông báo lỗi."""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Callable
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


def _run(args: list[str], *, timeout: int | None, text: bool):
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", *args]
    log.debug("ffmpeg.run", cmd=" ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=text,
            timeout=timeout or get_settings().ffmpeg_timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"FFmpeg quá thời gian cho phép: {exc}") from exc

    if proc.returncode != 0:
        stderr = proc.stderr if text else proc.stderr.decode("utf-8", "replace")
        raise FFmpegError(stderr[-2000:] or "ffmpeg thất bại không rõ lý do")
    return proc.stdout


def run_ffmpeg(args: list[str], *, timeout: int | None = None) -> str:
    """Chạy ffmpeg với danh sách tham số (KHÔNG dùng shell=True).

    Khi lỗi giữ 2000 ký tự cuối stderr — FFmpeg báo lỗi ở cuối.
    """
    return _run(args, timeout=timeout, text=True)


def run_ffmpeg_binary(args: list[str], *, timeout: int | None = None) -> bytes:
    """Như ``run_ffmpeg`` nhưng trả stdout dạng nhị phân.

    Dùng khi đẩy dữ liệu thô ra stdout (``-f rawvideo -``) thay vì ghi ra file.
    """
    return _run(args, timeout=timeout, text=False)


def parse_progress_line(line: str) -> int | None:
    """Đọc ``out_time_ms=<số>`` từ một dòng ``-progress``, ``None`` nếu không phải.

    Hàm thuần — test được mà không cần ffmpeg. Các dòng khác (``frame=12``,
    ``progress=continue``, dòng rỗng, dòng rác) đều trả ``None``. Tên trường
    giữ nguyên ``out_time_ms`` vì đó là tên ffmpeg in ra — xem
    :func:`out_time_to_percent` để biết vì sao giá trị của nó thực ra là micro
    giây chứ không phải mili giây.
    """
    line = line.strip()
    if not line or "=" not in line:
        return None
    key, _, value = line.partition("=")
    if key != "out_time_ms":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def out_time_to_percent(out_time_us: int, duration_sec: float) -> int:
    """Quy đổi mốc thời gian ``-progress`` của ffmpeg sang % kẹp trong [0, 100].

    Tham số đặt tên ``out_time_us`` (KHÔNG phải ``out_time_ms``) có chủ đích:
    trường ``out_time_ms`` mà ffmpeg in ra thực chất tính bằng MICRO giây, tên
    gọi đánh lừa (quirk lâu năm của ffmpeg, không phải lỗi gõ nhầm ở đây).
    Kiểm bằng ffmpeg thật: video dài 15s cho dòng ``out_time_ms`` cuối cùng
    ``~14_933_333`` — chỉ hợp lý nếu hiểu là micro giây (``14.93s``); hiểu
    nhầm là mili giây sẽ ra ``~14933s`` (~4 tiếng, vô lý) và % sẽ vọt qua 100
    ngay dòng progress đầu tiên, kẹp cứng ở 100 — xem
    ``test_out_time_to_percent_neu_hieu_nham_mili_giay_thi_vo_ly`` trong
    ``tests/test_progress.py``.

    ``duration_sec <= 0`` trả ``0`` thay vì chia cho 0.
    """
    if duration_sec <= 0:
        return 0
    return max(0, min(100, int(out_time_us / 1_000_000 / duration_sec * 100)))


def run_ffmpeg_progress(
    args: list[str],
    *,
    duration_sec: float,
    on_percent: Callable[[int], None],
    timeout: int | None = None,
) -> None:
    """Chạy ffmpeg với ``-progress pipe:1 -nostats``, gọi ``on_percent`` khi tiến.

    Đọc từng dòng stdout qua ``subprocess.Popen`` (không ``shell=True``). stderr
    được đọc song song ở luồng riêng để không bị đầy pipe làm treo tiến trình.
    Có timeout qua ``threading.Timer`` kill tiến trình khi quá hạn. ``-stats_period
    0.1`` để ffmpeg báo tiến trình dày hơn mặc định (~0.5s) — video ngắn vẫn ra
    đủ mốc. Nếu ``on_percent`` ném lỗi (vd mất Redis giữa chừng) thì kill tiến
    trình con trước khi raise lại — không để lại tiến trình ffmpeg mồ côi.
    Mã trả về khác 0 thì ``raise FFmpegError`` kèm 2000 ký tự cuối stderr.
    """
    cmd = [
        ffmpeg_bin(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-progress",
        "pipe:1",
        "-nostats",
        "-stats_period",
        "0.1",
        *args,
    ]
    limit = timeout or get_settings().ffmpeg_timeout_sec
    log.debug("ffmpeg.run_progress", cmd=" ".join(cmd), timeout=limit)

    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
        stderr_lines: list[str] = []

        def _drain_stderr() -> None:
            if proc.stderr is None:
                return
            for line in proc.stderr:
                stderr_lines.append(line)

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        timed_out = threading.Event()
        timer = threading.Timer(limit, lambda: (timed_out.set(), proc.kill()))
        timer.start()

        last_percent: int | None = None
        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    out_time_us = parse_progress_line(line)
                    if out_time_us is None:
                        continue
                    percent = out_time_to_percent(out_time_us, duration_sec)
                    if percent != last_percent:
                        on_percent(percent)
                        last_percent = percent
            proc.wait()
        except BaseException:
            # on_percent ném lỗi (vd mất Redis) hoặc bất kỳ lỗi nào khác giữa
            # chừng: giết tiến trình ffmpeg con trước khi raise tiếp, không để
            # nó chạy mồ côi.
            proc.kill()
            proc.wait()
            raise
        finally:
            timer.cancel()
            stderr_thread.join(timeout=5)

    if timed_out.is_set():
        raise FFmpegError(f"FFmpeg quá thời gian cho phép: {limit}s")

    if proc.returncode != 0:
        stderr = "".join(stderr_lines)
        raise FFmpegError(stderr[-2000:] or "ffmpeg thất bại không rõ lý do")


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
