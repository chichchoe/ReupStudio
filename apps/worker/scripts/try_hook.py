#!/usr/bin/env python3
"""Dựng filter hook rồi burn thử lên một video dọc tổng hợp — kiểm bằng mắt.

    ffmpeg -f lavfi -i testsrc2=size=1080x1920:rate=30 -t 5 -pix_fmt yuv420p doc.mp4
    python scripts/try_hook.py doc.mp4

In ra chuỗi filter đã dựng cho vài chuỗi text (thường + đủ 5 ký tự nguy hiểm
`: ' \\ % ,` + tiếng Việt có dấu), rồi thử burn thật bằng ffmpeg trên máy chạy
script. Nếu ffmpeg máy dev không build kèm libfreetype (không có filter
``drawtext`` — trường hợp của Homebrew ``ffmpeg`` mặc định, phải cài
``ffmpeg-full`` mới có), script vẫn có giá trị: lỗi ``Unknown filter
'drawtext'`` nghĩa là CÚ PHÁP filter đã đúng (ffmpeg parse xong toàn bộ chuỗi,
chỉ không tìm thấy filter để chạy) — khác hẳn lỗi cú pháp thật (``Error
parsing filterchain`` / ``No option name``), là dấu hiệu escape sai.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reup_core.logging import setup_logging  # noqa: E402

from src.errors import FFmpegError  # noqa: E402
from src.ffmpeg.probe import probe  # noqa: E402
from src.ffmpeg.runner import run_ffmpeg  # noqa: E402
from src.pipeline.shortform.hook import build_hook_filter, hook_box  # noqa: E402
from src.pipeline.shortform.safe_area import SafeArea  # noqa: E402

# Vùng an toàn TikTok, đúng giá trị seed ở Task 1 (dùng lại cho ví dụ này).
TIKTOK = SafeArea(top=0.06, bottom=0.18, left=0.05, right=0.20)

SAMPLE_TEXTS = [
    "Xem hết video để biết kết quả!",
    "Giá: 'giảm' 50%, còn C:\\videos — đừng bỏ lỡ!",  # đủ 5 ký tự nguy hiểm
    "áàảãạ ăằẳẵặ âầẩẫậ đ êềểễệ ôồổỗộ ơờởỡợ ưừửữự",  # tiếng Việt đủ dấu
]


def main() -> int:
    if len(sys.argv) != 2:
        print("Dùng: python scripts/try_hook.py <video_doc.mp4>")
        return 1

    src = Path(sys.argv[1])
    if not src.exists():
        print(f"Không tìm thấy {src}")
        return 1

    setup_logging()
    info = probe(src)
    print(f"Nguồn: {src.name} — {info.width}x{info.height} · {info.duration_sec:.1f}s")

    box = hook_box(TIKTOK)
    print(f"hook_box(TIKTOK) = {box}")

    for i, text in enumerate(SAMPLE_TEXTS, start=1):
        filt = build_hook_filter(text, box, info.width, info.height)
        print(f"\n[{i}] text = {text!r}")
        print(f"    filter = {filt}")

        dst = src.with_name(f"{src.stem}.hook{i}{src.suffix}")
        args = [
            "-i", str(src),
            "-vf", filt,
            "-t", "1",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-an",
            str(dst),
        ]
        try:
            run_ffmpeg(args, timeout=30)
        except FFmpegError as exc:
            msg = str(exc)
            if "nknown filter" in msg or "o such filter" in msg:
                print(
                    "    CÚ PHÁP OK — ffmpeg máy này thiếu filter 'drawtext' "
                    "(build không kèm libfreetype), không phải lỗi escape."
                )
            else:
                print(f"    LỖI CÚ PHÁP THẬT (escape sai):\n{msg}")
                return 1
        else:
            print(f"    Burn thành công -> {dst.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
