"""Trích khung hình xám thô từ video.

Trả về mảng byte ``size × size``, mỗi byte là một pixel xám 0–255 — vừa đủ cho
pHash. Không dùng thư viện ảnh: FFmpeg đã scale và đổi màu giúp rồi.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import FFmpegError
from .runner import run_ffmpeg_binary

#: Thời gian tối đa cho một lần trích khung. Chỉ giải mã 1 frame nên rất nhanh;
#: quá mốc này gần như chắc chắn là file hỏng.
FRAME_TIMEOUT_SEC = 60


def sample_timestamps(duration_sec: float, count: int) -> list[float]:
    """Các mốc thời gian rải đều để lấy mẫu khung hình.

    Lấy ở giữa mỗi khoảng ``(i + 0.5) / count`` chứ không lấy ở hai đầu: khung
    đầu và khung cuối của video ngắn Trung Quốc thường là fade đen hoặc bìa,
    giống nhau giữa các video khác hẳn nội dung.
    """
    if count <= 0:
        raise ValueError("count phải > 0")
    if duration_sec <= 0:
        return [0.0] * count
    return [round(duration_sec * (i + 0.5) / count, 3) for i in range(count)]


def extract_gray_frame(src: Path, at_sec: float, size: int, *, timeout: int | None = None) -> bytes:
    """Một khung tại giây ``at_sec``, scale về ``size × size``, xám, thô.

    Ép về hình vuông (bỏ tỷ lệ khung hình) là cố ý: nhờ vậy bản 9:16 và bản đã
    cắt cạnh của cùng một video vẫn cho pHash gần nhau.
    """
    expected = size * size
    data = run_ffmpeg_binary(
        [
            "-ss",
            f"{max(0.0, at_sec):.3f}",
            "-i",
            str(src),
            "-frames:v",
            "1",
            "-an",
            "-vf",
            f"scale={size}:{size}:flags=bilinear",
            "-pix_fmt",
            "gray",
            "-f",
            "rawvideo",
            "-",
        ],
        timeout=timeout or FRAME_TIMEOUT_SEC,
    )
    if len(data) < expected:
        raise FFmpegError(
            f"Không đọc được khung tại {at_sec:.3f}s của {src.name}: "
            f"nhận {len(data)} byte, cần {expected}"
        )
    return data[:expected]


def extract_gray_frames(
    src: Path, timestamps: list[float], size: int, *, timeout: int | None = None
) -> list[bytes]:
    """Nhiều khung theo danh sách mốc thời gian, giữ nguyên thứ tự."""
    return [extract_gray_frame(src, t, size, timeout=timeout) for t in timestamps]
