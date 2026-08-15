"""Đọc thông số video bằng ffprobe."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from reup_core.logging import get_logger

from ..errors import ProbeError
from .runner import ffprobe_bin

log = get_logger(__name__)


@dataclass(frozen=True)
class MediaInfo:
    duration_sec: float
    width: int
    height: int
    fps: float
    has_audio: bool
    video_codec: str
    size_bytes: int

    @property
    def is_vertical(self) -> bool:
        return self.height > self.width

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 0.0


def probe(path: Path) -> MediaInfo:
    if not path.exists():
        raise ProbeError(f"Không tìm thấy file: {path}")

    cmd = [
        ffprobe_bin(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise ProbeError(proc.stderr[-1000:])

    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise ProbeError("File không có luồng video")

    return MediaInfo(
        duration_sec=float(data.get("format", {}).get("duration") or 0.0),
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=_parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"),
        has_audio=audio is not None,
        video_codec=str(video.get("codec_name") or ""),
        size_bytes=int(data.get("format", {}).get("size") or 0),
    )


def _parse_fps(value: str) -> float:
    try:
        num, den = value.split("/")
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def do_dai_am_thanh(path: Path) -> float:
    """Độ dài file ÂM THANH, tính bằng giây.

    Tách khỏi ``probe()``: hàm kia đòi có luồng video và ném ``ProbeError`` với
    file mp3. Đo được hậu quả ngày 2026-08-15 — bước lồng tiếng gọi ``probe()``
    cho từng mẩu giọng, nhận lỗi, coi mọi câu là 0 giây, và dựng ra một dải
    tiếng IM HOÀN TOÀN dài đúng bằng video. Video vẫn chạy, vẫn có track âm
    thanh, chỉ là không ai nói gì.

    File hỏng hoặc rỗng trả 0,0 chứ không ném lỗi: một câu hỏng không được làm
    hỏng cả bản lồng tiếng, và chỗ gọi tự bỏ qua câu 0 giây.
    """
    if not path.exists() or path.stat().st_size == 0:
        return 0.0

    args = [
        ffprobe_bin(),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    if proc.returncode != 0:
        log.warning("probe.am_thanh_hong", path=str(path), error=proc.stderr[-300:])
        return 0.0

    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0
