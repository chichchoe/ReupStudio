from __future__ import annotations

import os
from pathlib import Path

from reup_core import paths


def test_moi_duong_dan_nam_duoi_media_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    root = paths.media_root()

    assert paths.raw_dir("douyin", "123").is_relative_to(root)
    assert paths.work_dir("abc").is_relative_to(root)
    assert paths.out_video("abc").is_relative_to(root)


def test_tmp_sibling_nam_cung_thu_muc_va_giu_duoi_file() -> None:
    dst = Path("/tmp/x/out.mp4")
    tmp = paths.tmp_sibling(dst)
    assert tmp.parent == dst.parent
    assert tmp.name.startswith(".")
    # FFmpeg đoán định dạng theo phần mở rộng — bắt buộc giữ .mp4 ở cuối
    assert tmp.suffix == ".mp4"
    assert tmp != dst


def test_tmp_sibling_giu_duoi_wav() -> None:
    assert paths.tmp_sibling(Path("/tmp/a.wav")).name == ".a.tmp.wav"


def test_thu_muc_duoc_tao_tu_dong(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    d = paths.work_dir("video-1")
    assert d.exists() and d.is_dir()
    _ = os  # giữ import cho rõ ràng
