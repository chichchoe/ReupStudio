#!/usr/bin/env python3
"""Đo dấu vân tay chống trùng trên file thật. Không đụng DB.

    # một file: in md5 + pHash từng khung
    python scripts/try_dedup.py video.mp4

    # hai file trở lên: so từng cặp, kết luận trùng / không trùng
    python scripts/try_dedup.py goc.mp4 ban_ma_hoa_lai.mp4 video_khac.mp4

Cách tự tạo mẫu để kiểm nhanh (không cần tải video thật):

    ffmpeg -f lavfi -i testsrc2=size=1080x1920:rate=30 -t 10 -pix_fmt yuv420p a.mp4
    ffmpeg -i a.mp4 -vf scale=540:960 -c:v libx264 -crf 34 a_reenc.mp4
    ffmpeg -f lavfi -i mandelbrot=size=1080x1920:rate=30 -t 10 -pix_fmt yuv420p b.mp4
    python scripts/try_dedup.py a.mp4 a_reenc.mp4 b.mp4
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_settings  # noqa: E402
from src.ffmpeg.probe import probe  # noqa: E402
from src.pipeline.dedup import (  # noqa: E402
    PHASH_HEX_PER_FRAME,
    fingerprint,
    is_similar_phash,
    phash_distance,
)


def main() -> int:
    if len(sys.argv) < 2:
        print("Dùng: python scripts/try_dedup.py <video1> [video2 ...]")
        return 1

    settings = get_settings()
    frames = settings.dedup_phash_frames
    max_distance = settings.dedup_phash_max_distance
    total_bits = frames * PHASH_HEX_PER_FRAME * 4

    paths = [Path(p) for p in sys.argv[1:]]
    prints = {}

    for path in paths:
        if not path.exists():
            print(f"❌ Không tìm thấy {path}")
            return 1
        info = probe(path)
        fp = fingerprint(path, frames=frames)
        prints[path] = fp
        per_frame = [
            fp.phash[i : i + PHASH_HEX_PER_FRAME]
            for i in range(0, len(fp.phash), PHASH_HEX_PER_FRAME)
        ]
        print(f"\n{path.name}")
        print(f"   {info.width}x{info.height} · {info.duration_sec:.1f}s · {info.fps:.1f}fps")
        print(f"   md5   : {fp.md5}")
        print(f"   pHash : {' '.join(per_frame)}")

    if len(paths) < 2:
        return 0

    print(f"\nSo sánh (ngưỡng {max_distance}/{total_bits} bit):")
    for i, left in enumerate(paths):
        for right in paths[i + 1 :]:
            a, b = prints[left], prints[right]
            if a.md5 == b.md5:
                verdict, reason = "TRÙNG", "md5 giống hệt"
            else:
                distance = phash_distance(a.phash, b.phash)
                similar = is_similar_phash(a.phash, b.phash, max_distance=max_distance)
                verdict = "TRÙNG" if similar else "khác"
                reason = f"lệch {distance}/{total_bits} bit"
            mark = "🟡" if verdict == "TRÙNG" else "🟢"
            print(f"   {mark} {left.name} ↔ {right.name}: {verdict} ({reason})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
