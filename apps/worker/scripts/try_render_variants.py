#!/usr/bin/env python3
"""Render thử nhiều bản (``render_variants``) từ MỘT video — kiểm bằng mắt, không đụng DB.

    ffmpeg -f lavfi -i testsrc2=size=1920x1080:rate=30 -t 200 -pix_fmt yuv420p ngang.mp4
    python scripts/try_render_variants.py ngang.mp4

Dựng giới hạn thời lượng mẫu (tiktok/youtube/facebook, cùng giá trị với seed
migration 0007) — script này KHÔNG đụng DB nên tự khai giá trị mẫu, sản phẩm
thật luôn đọc từ bảng ``platform_limits`` (luật số 5 CLAUDE.md). Gọi
``plan_variants`` rồi ``render_variant`` cho từng tập, ghi ra
``media/out/try-render-variants/<platform>.p<part>.mp4`` (đổi thư mục gốc qua
biến môi trường ``MEDIA_ROOT``).

Chạy với ``cues=[]`` (video mẫu ``testsrc2`` không có lời thoại) nên MỌI tập đi
qua nhánh ``trim_video`` (chỉ CẮT, không burn phụ đề) — nhánh có phụ đề
(``burn_subtitles``) cần ffmpeg build kèm libass/libfreetype, môi trường dev
container hiện KHÔNG có (xem task-6-report.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reup_core.logging import setup_logging  # noqa: E402

from src.ffmpeg.probe import probe  # noqa: E402
from src.pipeline.render import plan_variants, render_variant  # noqa: E402

#: Giới hạn mẫu — GIỐNG giá trị seed migration 0007, chỉ để script này tự
#: chạy được không cần Postgres. KHÔNG phải nguồn sự thật (đó là platform_limits).
SAMPLE_LIMITS = {"tiktok": 180, "youtube": 180, "facebook": 90}

VIDEO_ID = "try-render-variants"


def main() -> int:
    if len(sys.argv) != 2:
        print("Dùng: python scripts/try_render_variants.py <video.mp4>")
        return 1

    src = Path(sys.argv[1])
    if not src.exists():
        print(f"Không tìm thấy {src}")
        return 1

    setup_logging()
    info = probe(src)
    print(f"Nguồn: {src.name} — {info.width}x{info.height} · {info.duration_sec:.1f}s")

    plans = plan_variants(info.duration_sec, list(SAMPLE_LIMITS), SAMPLE_LIMITS)
    print(f"plan_variants -> {len(plans)} tập")

    for plan in plans:
        out = render_variant(VIDEO_ID, src, [], plan)
        size_mb = out.stat().st_size / 1_000_000
        print(
            f"  {plan.target_platform} p{plan.part_index}/{plan.part_total} "
            f"[{plan.start:.1f}s-{plan.end:.1f}s] -> {out} ({size_mb:.2f} MB)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
