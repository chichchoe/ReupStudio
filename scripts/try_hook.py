#!/usr/bin/env python3
"""Xuất ảnh hook để kiểm bằng MẮT — chữ có tràn khối không, có bị cắt không.

Phần này không test tự động được (CLAUDE.md: ffmpeg kiểm bằng script chạy tay).
``fit_hook_text`` chỉ ƯỚC LƯỢNG bề rộng chữ vì ``drawtext`` không cho hỏi kích
thước trước khi render; ước sai bao nhiêu thì chỉ nhìn ảnh mới biết.

    python scripts/try_hook.py                       # bộ câu mẫu
    python scripts/try_hook.py "CÂU HOOK CỦA BẠN"    # câu bất kỳ
    python scripts/try_hook.py --nen video.mp4 "..."  # đặt lên khung video thật

Ảnh ra nằm trong ``media/tmp/try_hook/``. Mở lên và soi ba thứ:

1. Chữ có nằm TRỌN trong khối tối không, hay bị cắt cụt hai đầu.
2. Khối hook có đè xuống vùng phụ đề không (phụ đề nằm sát đáy vùng an toàn).
3. Cỡ chữ có còn đọc được ở kích thước điện thoại không.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "worker"))

from src.pipeline.shortform.hook import (
    build_hook_filter,
    fit_hook_text,
    hook_box,
)
from src.pipeline.shortform.safe_area import SafeArea

#: Vùng an toàn TikTok — nền tảng chật nhất, hook vừa ở đây thì vừa ở mọi nơi.
TIKTOK = SafeArea(top=0.06, bottom=0.18, left=0.05, right=0.20)
KHUNG_W, KHUNG_H = 1080, 1920
THU_MUC_RA = REPO / "media" / "tmp" / "try_hook"

CAU_MAU = [
    "Xem hết nhé",
    "BA NĂM SAU CÔ ẤY QUAY LẠI",
    "ĐỪNG LƯỚT QUA VIDEO NÀY",
    "Cô ấy tỉnh ra sau ba năm bị coi thường và tất cả đã quá muộn",
    "WWWWW MMMMM ƠỚỜỞ",
]


def xuat_anh(text: str, chi_so: int, nen: Path | None) -> Path:
    box = hook_box(TIKTOK)
    da_ngat, co_chu = fit_hook_text(
        text,
        box_w_px=round(box[2] * KHUNG_W),
        box_h_px=round(box[3] * KHUNG_H),
    )
    print(f"[{chi_so}] cỡ chữ {co_chu:>3}  {da_ngat.splitlines()}")

    THU_MUC_RA.mkdir(parents=True, exist_ok=True)
    ra = THU_MUC_RA / f"hook_{chi_so:02d}.png"
    if nen is not None:
        vao = ["-i", str(nen)]
        loc = f"scale={KHUNG_W}:{KHUNG_H}," + build_hook_filter(
            text, box, KHUNG_W, KHUNG_H
        )
    else:
        vao = ["-f", "lavfi", "-i", f"color=c=0x2a3140:s={KHUNG_W}x{KHUNG_H}:d=1"]
        loc = build_hook_filter(text, box, KHUNG_W, KHUNG_H)

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        *vao,
        "-vf",
        loc,
        "-frames:v",
        "1",
        str(ra),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg lỗi:\n{proc.stderr[-2000:]}")
    return ra


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "text", nargs="*", help="câu hook cần thử; bỏ trống thì dùng bộ mẫu"
    )
    parser.add_argument("--nen", type=Path, help="video làm nền thay cho nền trơn")
    args = parser.parse_args()

    cac_cau = args.text or CAU_MAU
    for chi_so, cau in enumerate(cac_cau, start=1):
        print(f"  -> {xuat_anh(cau, chi_so, args.nen)}")
    print(f"\nMở thư mục để soi: {THU_MUC_RA}")


if __name__ == "__main__":
    main()
