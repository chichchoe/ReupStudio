"""Douyin — ưu tiên bản không watermark khi nền tảng có cung cấp."""

from __future__ import annotations

from typing import Any

from reup_core.enums import SourcePlatform

from .ytdlp_downloader import YtDlpDownloader


class DouyinDownloader(YtDlpDownloader):
    platform = SourcePlatform.DOUYIN

    extra_opts: dict[str, Any] = {
        # Douyin trả nhiều format; bản "play_addr" thường đã bỏ watermark.
        "format": "bestvideo+bestaudio/best",
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile Safari/604.1"
            ),
            "Referer": "https://www.douyin.com/",
        },
    }
