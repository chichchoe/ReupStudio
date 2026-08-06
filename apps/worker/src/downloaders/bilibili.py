from __future__ import annotations

from typing import Any

from reup_core.enums import SourcePlatform

from .ytdlp_downloader import YtDlpDownloader


class BilibiliDownloader(YtDlpDownloader):
    platform = SourcePlatform.BILIBILI

    extra_opts: dict[str, Any] = {
        "http_headers": {"Referer": "https://www.bilibili.com/"},
    }
