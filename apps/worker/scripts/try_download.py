#!/usr/bin/env python3
"""Thử tải một link, in metadata. Không đụng DB.

    python scripts/try_download.py "https://v.douyin.com/xxxx/"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reup_core.source_url import parse_source_url  # noqa: E402

from src.ffmpeg.probe import probe  # noqa: E402
from src.pipeline.download import download_video  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Dùng: python scripts/try_download.py <url>")
        return 1

    url = sys.argv[1]
    parsed = parse_source_url(url)
    if parsed is None:
        print(f"❌ Không nhận diện được nền tảng từ URL: {url}")
        return 1

    print(f"Nền tảng : {parsed.platform.value}")
    print(f"ID       : {parsed.video_id}{' (tạm)' if parsed.provisional else ''}")

    result = download_video(
        url,
        parsed.platform,
        parsed.video_id,
        progress_cb=lambda p: print(f"\r  tải… {p}%", end="", flush=True),
    )
    print()

    info = probe(result.path)
    print(f"✅ File     : {result.path}")
    print(f"   Tiêu đề  : {result.title}")
    print(f"   Tác giả  : {result.author}")
    print(f"   Lượt xem : {result.view_count}")
    print(f"   Kích thước: {info.width}x{info.height} · {info.duration_sec:.1f}s · {info.fps:.1f}fps")
    print(f"   Có audio : {info.has_audio} · dọc: {info.is_vertical}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
