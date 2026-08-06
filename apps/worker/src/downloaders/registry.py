"""Chọn downloader theo nền tảng."""

from __future__ import annotations

from reup_core.enums import SourcePlatform

from .base import BaseDownloader
from .bilibili import BilibiliDownloader
from .douyin import DouyinDownloader
from .kuaishou import KuaishouDownloader
from .ytdlp_downloader import YtDlpDownloader

_REGISTRY: dict[SourcePlatform, type[BaseDownloader]] = {
    SourcePlatform.DOUYIN: DouyinDownloader,
    SourcePlatform.BILIBILI: BilibiliDownloader,
    SourcePlatform.KUAISHOU: KuaishouDownloader,
}


def get_downloader(platform: SourcePlatform | str) -> BaseDownloader:
    if isinstance(platform, str):
        platform = SourcePlatform(platform)
    cls = _REGISTRY.get(platform, YtDlpDownloader)
    return cls()
