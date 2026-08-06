#!/usr/bin/env python3
"""Chạy TOÀN BỘ pipeline M1 trên một link, không cần Celery/Redis/Postgres.

    python scripts/try_pipeline.py "https://v.douyin.com/xxxx/"

Đây là cách nhanh nhất để kiểm tra chất lượng đầu ra khi đang phát triển.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reup_core.logging import setup_logging  # noqa: E402
from reup_core.paths import audio_path  # noqa: E402
from reup_core.source_url import parse_source_url  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.ffmpeg.burn import extract_audio  # noqa: E402
from src.ffmpeg.probe import probe  # noqa: E402
from src.pipeline.download import download_video  # noqa: E402
from src.pipeline.render import render_with_subtitles  # noqa: E402
from src.pipeline.subtitle_format import FormatOptions, format_cues  # noqa: E402
from src.pipeline.transcribe import transcribe  # noqa: E402
from src.pipeline.translate import translate_cues  # noqa: E402


def step(name: str, index: int, total: int) -> None:
    print(f"\n[{index}/{total}] {name}")
    print("-" * 60)


def main() -> int:
    if len(sys.argv) < 2:
        print("Dùng: python scripts/try_pipeline.py <url>")
        return 1

    setup_logging("INFO")
    settings = get_settings()
    url = sys.argv[1]
    parsed = parse_source_url(url)
    if parsed is None:
        print(f"❌ Không nhận diện được URL: {url}")
        return 1

    fake_video_id = f"try-{parsed.video_id}"
    started = time.perf_counter()

    step("Tải video", 1, 6)
    result = download_video(url, parsed.platform, parsed.video_id)
    print(f"  → {result.path}")

    step("Đọc thông số", 2, 6)
    info = probe(result.path)
    print(f"  → {info.width}x{info.height} · {info.duration_sec:.1f}s · audio={info.has_audio}")
    if not info.has_audio:
        print("  ⚠ Video không có audio — bỏ qua nhận dạng và dịch.")
        return 0

    step("Nhận dạng giọng nói (Whisper)", 3, 6)
    wav = audio_path(fake_video_id)
    extract_audio(result.path, wav)
    zh_cues = transcribe(wav)
    print(f"  → {len(zh_cues)} câu tiếng Trung")
    for cue in zh_cues[:3]:
        print(f"     [{cue.start:6.2f}] {cue.text}")

    step(f"Dịch sang tiếng Việt ({settings.llm_provider})", 4, 6)
    vi_cues = translate_cues(zh_cues, tone="ngon_tinh")
    for cue in vi_cues[:3]:
        print(f"     [{cue.start:6.2f}] {cue.text}")

    step("Chuẩn hoá phụ đề", 5, 6)
    formatted = format_cues(
        vi_cues,
        FormatOptions(
            max_chars_per_line=settings.sub_max_chars_per_line,
            max_lines=settings.sub_max_lines,
            min_duration=settings.sub_min_duration,
        ),
    )
    print(f"  → {len(vi_cues)} câu → {len(formatted)} khung sau chuẩn hoá")

    step("Render (burn phụ đề)", 6, 6)
    out = render_with_subtitles(fake_video_id, result.path, formatted)

    elapsed = time.perf_counter() - started
    print(f"\n✅ Xong sau {elapsed:.0f}s")
    print(f"   File kết quả: {out}")
    print(f"   Tỷ lệ xử lý : {elapsed / max(info.duration_sec, 1):.1f}× thời lượng video")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
