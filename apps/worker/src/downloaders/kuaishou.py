from __future__ import annotations

from typing import Any

from reup_core.enums import SourcePlatform

from .ytdlp_downloader import YtDlpDownloader


class KuaishouDownloader(YtDlpDownloader):
    platform = SourcePlatform.KUAISHOU

    extra_opts: dict[str, Any] = {
        "http_headers": {"Referer": "https://www.kuaishou.com/"},
    }
