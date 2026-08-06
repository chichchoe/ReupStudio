"""Nơi DUY NHẤT được phép ghép đường dẫn file.

Không viết ``os.path.join`` hay f-string ghép path ở bất kỳ chỗ nào khác — khi
đổi cấu trúc lưu trữ chỉ cần sửa file này.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_KEY = "MEDIA_ROOT"


def media_root() -> Path:
    return Path(os.getenv(_ENV_KEY, "./media")).resolve()


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def raw_dir(platform: str, source_video_id: str) -> Path:
    """Thư mục chứa file gốc tải về."""
    return _ensure(media_root() / "raw" / platform / source_video_id)


def raw_video(platform: str, source_video_id: str) -> Path:
    return raw_dir(platform, source_video_id) / "source.mp4"


def raw_meta(platform: str, source_video_id: str) -> Path:
    return raw_dir(platform, source_video_id) / "meta.json"


def work_dir(video_id: str) -> Path:
    """Thư mục chứa file trung gian: audio, phụ đề, mask, proxy."""
    return _ensure(media_root() / "work" / str(video_id))


def audio_path(video_id: str) -> Path:
    return work_dir(video_id) / "audio.wav"


def subtitle_path(video_id: str, lang: str) -> Path:
    return work_dir(video_id) / f"sub.{lang}.srt"


def proxy_path(video_id: str) -> Path:
    """Bản 540p dùng cho preview trên web — tua nhanh hơn bản gốc."""
    return work_dir(video_id) / "proxy.mp4"


def out_dir(video_id: str) -> Path:
    return _ensure(media_root() / "out" / str(video_id))


def out_video(video_id: str, target: str = "master") -> Path:
    """File render cuối. ``target`` là tên nền tảng đích (M4 trở đi)."""
    return out_dir(video_id) / f"{target}.mp4"


def tmp_sibling(path: Path) -> Path:
    """Đường dẫn tạm cạnh file đích.

    Luôn ghi ra file tạm rồi ``rename`` sang tên chính thức, để một file dở dang
    (do crash giữa chừng) không bị bước sau coi là hợp lệ.

    Phần mở rộng được GIỮ NGUYÊN ở cuối tên (``.a.tmp.wav`` chứ không phải
    ``.a.wav.tmp``) vì FFmpeg đoán định dạng đầu ra từ phần mở rộng.
    """
    return path.with_name(f".{path.stem}.tmp{path.suffix}")
