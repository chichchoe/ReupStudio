#!/usr/bin/env python
"""Burn thử phụ đề lên một video thật rồi xuất ảnh khung để MẮT NGƯỜI kiểm.

Vị trí phụ đề không test tự động được (CLAUDE.md: FFmpeg kiểm bằng script chạy
tay trên file thật). Test tự động chỉ chứng minh file ASS đúng cú pháp và đúng
con số — không chứng minh được chữ có thật sự nằm trong khung hình hay không.
Chính khoảng trống đó đã giấu lỗi phụ đề bay ra ngoài khung suốt nhiều tháng.

    python scripts/try_burn.py video.mp4 [--platform tiktok] [--giay 5]

In ra đường dẫn video đã burn và một ảnh PNG chụp ở giây ``--giay``. Mở ảnh lên:
chữ phải nằm TRỌN trong khung, cách đáy đúng vùng an toàn của nền tảng.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reup_core.logging import setup_logging  # noqa: E402

from src.ffmpeg.burn import burn_subtitles  # noqa: E402
from src.ffmpeg.probe import probe  # noqa: E402
from src.ffmpeg.runner import run_ffmpeg  # noqa: E402
from src.pipeline.cues import Cue  # noqa: E402
from src.pipeline.shortform.safe_area import SafeArea  # noqa: E402
from src.pipeline.subtitle_ass import build_ass_style, write_ass  # noqa: E402

#: Vùng an toàn đã seed trong bảng ``platform_limits``. Script chạy tay không
#: đọc DB nên chép lại ở đây — đổi bảng thì nhớ đổi cả chỗ này.
VUNG_AN_TOAN = {
    "tiktok": SafeArea(top=0.06, bottom=0.18, left=0.05, right=0.20),
    "youtube": SafeArea(top=0.06, bottom=0.15, left=0.05, right=0.15),
    "facebook": SafeArea(top=0.08, bottom=0.20, left=0.05, right=0.18),
    "instagram": SafeArea(top=0.08, bottom=0.22, left=0.05, right=0.20),
}

CAU_THU = [
    Cue(0, 0.5, 4.0, "Dòng phụ đề thử — chữ phải nằm trọn trong khung hình"),
    Cue(1, 4.0, 8.0, "Dòng hai kiểm dấu tiếng Việt:\nượt, ỷ, ẫn, ọc, ỗi, ằng"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--platform", default="tiktok", choices=sorted(VUNG_AN_TOAN))
    parser.add_argument("--giay", type=float, default=5.0, help="mốc chụp ảnh khung")
    args = parser.parse_args()

    if not args.video.exists():
        print(f"Không thấy file: {args.video}")
        return 1

    setup_logging()
    info = probe(args.video)
    safe = VUNG_AN_TOAN[args.platform]
    print(f"Khung nguồn: {info.width}x{info.height} · nền tảng: {args.platform}")

    style = build_ass_style(safe, info.width, info.height)
    print(
        f"Cỡ chữ {style.font_size}px · lề dưới {style.margin_v}px "
        f"· lề trái {style.margin_l}px · lề phải {style.margin_r}px"
    )
    if style.margin_v >= (info.height or 0):
        print("⚠ Lề dưới lớn hơn cả khung hình — phụ đề sẽ không hiện!")

    ass = write_ass(
        CAU_THU,
        args.video.with_suffix(".thu.ass"),
        width=info.width,
        height=info.height,
        style=style,
    )
    out = args.video.with_suffix(".thu-burn.mp4")
    burn_subtitles(args.video, ass, out, duration_sec=min(info.duration_sec, 10))

    anh = args.video.with_suffix(".thu-burn.png")
    run_ffmpeg(["-ss", str(args.giay), "-i", str(out), "-frames:v", "1", str(anh)])

    print(f"\n✅ Video: {out}\n✅ Ảnh  : {anh}")
    print("Mở ảnh lên xem: chữ có nằm trọn trong khung không, có đè vùng UI không.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
