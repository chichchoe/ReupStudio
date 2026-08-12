#!/usr/bin/env python3
"""Đổi thử một video ngang sang dọc 9:16 bằng cả hai chế độ. Không đụng DB.

    python scripts/try_reframe.py ngang.mp4

Xuất ra ``<tên>.blur.mp4`` và ``<tên>.crop.mp4`` cạnh file gốc, in kích thước
đầu ra và thời gian xử lý mỗi chế độ.

Cách tự tạo mẫu để kiểm nhanh (không cần tải video thật):

    ffmpeg -f lavfi -i testsrc2=size=1920x1080:rate=30 -t 6 -pix_fmt yuv420p ngang.mp4
    python scripts/try_reframe.py ngang.mp4
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reup_core.logging import setup_logging  # noqa: E402

from src.ffmpeg.probe import probe  # noqa: E402
from src.pipeline.shortform.reframe import reframe_blur, reframe_crop  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Dùng: python scripts/try_reframe.py <video_ngang.mp4>")
        return 1

    src = Path(sys.argv[1])
    if not src.exists():
        print(f"❌ Không tìm thấy {src}")
        return 1

    setup_logging()

    info = probe(src)
    print(f"Nguồn: {src.name} — {info.width}x{info.height} · {info.duration_sec:.1f}s")

    for mode, fn in (("blur", reframe_blur), ("crop", reframe_crop)):
        dst = src.with_name(f"{src.stem}.{mode}{src.suffix}")
        start = time.monotonic()
        fn(src, dst)
        elapsed = time.monotonic() - start
        out_info = probe(dst)
        print(
            f"  {mode:5s} → {dst.name} ({out_info.width}x{out_info.height}) "
            f"trong {elapsed:.2f}s"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
