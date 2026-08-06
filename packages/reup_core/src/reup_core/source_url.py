"""Nhận diện nền tảng nguồn và trích ID video từ URL.

Dùng chung giữa API (tạo bản ghi, chống trùng) và worker (chọn downloader).
Khi nền tảng đổi cấu trúc URL, chỉ sửa file này.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .enums import SourcePlatform


@dataclass(frozen=True)
class ParsedSource:
    platform: SourcePlatform
    video_id: str
    url: str
    #: True khi ID chỉ là tạm (link rút gọn) — worker phải resolve lại sau khi tải.
    provisional: bool = False


_PATTERNS: list[tuple[SourcePlatform, re.Pattern[str], bool]] = [
    # Douyin
    (SourcePlatform.DOUYIN, re.compile(r"douyin\.com/video/(\d+)"), False),
    (SourcePlatform.DOUYIN, re.compile(r"douyin\.com/note/(\d+)"), False),
    (SourcePlatform.DOUYIN, re.compile(r"v\.douyin\.com/([A-Za-z0-9_-]+)"), True),
    (SourcePlatform.DOUYIN, re.compile(r"iesdouyin\.com/share/video/(\d+)"), False),
    # Bilibili
    (SourcePlatform.BILIBILI, re.compile(r"bilibili\.com/video/(BV[A-Za-z0-9]+)"), False),
    (SourcePlatform.BILIBILI, re.compile(r"b23\.tv/([A-Za-z0-9]+)"), True),
    # Kuaishou
    (SourcePlatform.KUAISHOU, re.compile(r"kuaishou\.com/short-video/([A-Za-z0-9_-]+)"), False),
    (SourcePlatform.KUAISHOU, re.compile(r"v\.kuaishou\.com/([A-Za-z0-9]+)"), True),
    # Xiaohongshu
    (SourcePlatform.XIAOHONGSHU, re.compile(r"xiaohongshu\.com/explore/([a-f0-9]+)"), False),
    (SourcePlatform.XIAOHONGSHU, re.compile(r"xhslink\.com/([A-Za-z0-9]+)"), True),
    # Weibo
    (SourcePlatform.WEIBO, re.compile(r"weibo\.com/tv/show/([\w:-]+)"), False),
    (SourcePlatform.WEIBO, re.compile(r"video\.weibo\.com/show\?fid=([\w:-]+)"), False),
]

_DOMAIN_HINTS: dict[str, SourcePlatform] = {
    "douyin.com": SourcePlatform.DOUYIN,
    "bilibili.com": SourcePlatform.BILIBILI,
    "kuaishou.com": SourcePlatform.KUAISHOU,
    "xiaohongshu.com": SourcePlatform.XIAOHONGSHU,
    "weibo.com": SourcePlatform.WEIBO,
}


def parse_source_url(url: str) -> ParsedSource | None:
    """Trả về ``ParsedSource`` hoặc ``None`` nếu URL không nhận diện được."""
    url = url.strip()
    if not url or not url.startswith(("http://", "https://")):
        return None

    for platform, pattern, provisional in _PATTERNS:
        m = pattern.search(url)
        if m:
            return ParsedSource(platform, m.group(1), url, provisional)

    # Không khớp mẫu nào nhưng domain quen thuộc: vẫn nhận, để yt-dlp thử.
    host = (urlparse(url).hostname or "").lower()
    for domain, platform in _DOMAIN_HINTS.items():
        if host.endswith(domain):
            return ParsedSource(platform, _fallback_id(url), url, provisional=True)

    return None


def _fallback_id(url: str) -> str:
    """ID tạm sinh từ URL để giữ ràng buộc UNIQUE trước khi biết ID thật."""
    import hashlib

    return "u" + hashlib.md5(url.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class ParsedChannel:
    platform: SourcePlatform
    external_id: str
    url: str
    #: Chỉ có giá trị nếu chính URL mang theo handle hiển thị (`@...`); 4 mẫu
    #: URL kênh hiện hỗ trợ đều không mang, nên luôn là ``None`` — việc lấy
    #: handle/tên hiển thị thật do task Celery quét kênh làm sau, không phải
    #: ở đây (endpoint resolve KHÔNG được gọi mạng).
    handle: str | None = None


_CHANNEL_PATTERNS: list[tuple[SourcePlatform, re.Pattern[str]]] = [
    (SourcePlatform.DOUYIN, re.compile(r"douyin\.com/user/([A-Za-z0-9_-]+)")),
    (SourcePlatform.BILIBILI, re.compile(r"space\.bilibili\.com/(\d+)")),
    (SourcePlatform.KUAISHOU, re.compile(r"kuaishou\.com/profile/([A-Za-z0-9_-]+)")),
    (
        SourcePlatform.XIAOHONGSHU,
        re.compile(r"xiaohongshu\.com/user/profile/([A-Za-z0-9_-]+)"),
    ),
]


def parse_channel_url(url: str) -> ParsedChannel | None:
    """Bóc ``platform`` + ``external_id`` từ URL trang kênh (không phải URL video).

    Hàm thuần, KHÔNG gọi mạng — chỉ phân tích chuỗi URL. Trả về ``None`` nếu
    URL không khớp mẫu kênh nào (kể cả khi nó là link video, không phải kênh).
    """
    url = url.strip()
    if not url or not url.startswith(("http://", "https://")):
        return None

    for platform, pattern in _CHANNEL_PATTERNS:
        m = pattern.search(url)
        if m:
            return ParsedChannel(platform, m.group(1), url)

    return None
