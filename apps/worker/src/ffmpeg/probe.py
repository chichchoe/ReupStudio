"""Đọc thông số video bằng ffprobe."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..errors import ProbeError
from .runner import ffprobe_bin


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
