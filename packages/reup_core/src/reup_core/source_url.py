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


#: Mỗi mẫu BẮT ĐẦU bằng tên miền và được ghép thêm ``_HOST_BOUNDARY`` ở đầu khi
#: biên dịch. Không có chốt đó thì ``re.search`` khớp cả chuỗi con:
#: ``khongphaidouyin.com/video/1`` chứa ``douyin.com/video/1`` và bị nhận nhầm
#: thành Douyin. Ranh giới hợp lệ chỉ có: đầu chuỗi, sau ``//``, hoặc sau ``.``.
_HOST_BOUNDARY = r"(?:^|//|\.)"

_RAW_PATTERNS: list[tuple[SourcePlatform, str, bool]] = [
    # Douyin
    (SourcePlatform.DOUYIN, r"douyin\.com/video/(\d+)", False),
    (SourcePlatform.DOUYIN, r"douyin\.com/note/(\d+)", False),
    #: Dạng URL khi bấm vào video trong trang khám phá (`/jingxuan/...`,
    #: `/discover`, `/user/...`). yt-dlp KHÔNG hiểu dạng này — đo ngày
    #: 2026-08-14: `ERROR: Unsupported URL`. Bóc ID rồi viết lại về dạng chuẩn,
    #: xem `_canonical_url`.
    (SourcePlatform.DOUYIN, r"douyin\.com/[\w/-]*\?(?:.*&)?modal_id=(\d+)", False),
    (SourcePlatform.DOUYIN, r"v\.douyin\.com/([A-Za-z0-9_-]+)", True),
    (SourcePlatform.DOUYIN, r"iesdouyin\.com/share/video/(\d+)", False),
    # Bilibili
    (SourcePlatform.BILIBILI, r"bilibili\.com/video/(BV[A-Za-z0-9]+)", False),
    (SourcePlatform.BILIBILI, r"b23\.tv/([A-Za-z0-9]+)", True),
    # Kuaishou
    (SourcePlatform.KUAISHOU, r"kuaishou\.com/short-video/([A-Za-z0-9_-]+)", False),
    (SourcePlatform.KUAISHOU, r"v\.kuaishou\.com/([A-Za-z0-9]+)", True),
    # Xiaohongshu
    (SourcePlatform.XIAOHONGSHU, r"xiaohongshu\.com/explore/([a-f0-9]+)", False),
    (SourcePlatform.XIAOHONGSHU, r"xhslink\.com/([A-Za-z0-9]+)", True),
    # Weibo
    (SourcePlatform.WEIBO, r"weibo\.com/tv/show/([\w:-]+)", False),
    (SourcePlatform.WEIBO, r"video\.weibo\.com/show\?fid=([\w:-]+)", False),
    # YouTube
    (SourcePlatform.YOUTUBE, r"youtube\.com/watch\?(?:.*&)?v=([\w-]+)", False),
    (SourcePlatform.YOUTUBE, r"youtube\.com/shorts/([\w-]+)", False),
    (SourcePlatform.YOUTUBE, r"youtu\.be/([\w-]+)", False),
    # TikTok
    (SourcePlatform.TIKTOK, r"tiktok\.com/@[\w.-]+/video/(\d+)", False),
    (SourcePlatform.TIKTOK, r"vm\.tiktok\.com/([A-Za-z0-9]+)", True),
    (SourcePlatform.TIKTOK, r"tiktok\.com/t/([A-Za-z0-9]+)", True),
    # Instagram
    (SourcePlatform.INSTAGRAM, r"instagram\.com/(?:reels?|p|tv)/([\w-]+)", False),
    # Facebook
    (SourcePlatform.FACEBOOK, r"facebook\.com/reel/(\d+)", False),
    (SourcePlatform.FACEBOOK, r"facebook\.com/watch/?\?(?:.*&)?v=(\d+)", False),
    (SourcePlatform.FACEBOOK, r"facebook\.com/[\w.]+/videos/(\d+)", False),
    (SourcePlatform.FACEBOOK, r"fb\.watch/([\w-]+)", True),
    # X (Twitter)
    (SourcePlatform.TWITTER, r"(?:twitter|x)\.com/\w+/status/(\d+)", False),
]

_PATTERNS: list[tuple[SourcePlatform, re.Pattern[str], bool]] = [
    (platform, re.compile(_HOST_BOUNDARY + raw), provisional)
    for platform, raw, provisional in _RAW_PATTERNS
]

_DOMAIN_HINTS: dict[str, SourcePlatform] = {
    "douyin.com": SourcePlatform.DOUYIN,
    "bilibili.com": SourcePlatform.BILIBILI,
    "kuaishou.com": SourcePlatform.KUAISHOU,
    "xiaohongshu.com": SourcePlatform.XIAOHONGSHU,
    "weibo.com": SourcePlatform.WEIBO,
    "youtube.com": SourcePlatform.YOUTUBE,
    "youtu.be": SourcePlatform.YOUTUBE,
    "tiktok.com": SourcePlatform.TIKTOK,
    "instagram.com": SourcePlatform.INSTAGRAM,
    "facebook.com": SourcePlatform.FACEBOOK,
    "twitter.com": SourcePlatform.TWITTER,
    "x.com": SourcePlatform.TWITTER,
}


def _host_matches(host: str, domain: str) -> bool:
    """Khớp trọn nhãn tên miền, không phải khớp đuôi chuỗi.

    ``"netflix.com".endswith("x.com")`` là ``True`` — dùng ``endswith`` trần sẽ
    gán Netflix thành Twitter. Phải là chính tên miền đó hoặc tên miền con.
    """
    return host == domain or host.endswith("." + domain)


#: Nền tảng có dạng URL "chuẩn" mà bước tải hiểu được. Khoá là nền tảng, giá
#: trị là khuôn để dựng lại URL từ ID video.
_CANONICAL_URL: dict[SourcePlatform, str] = {
    SourcePlatform.DOUYIN: "https://www.douyin.com/video/{video_id}",
}


def _canonical_url(platform: SourcePlatform, video_id: str, url: str) -> str:
    """URL để LƯU và để đưa cho bước tải.

    Douyin có nhiều dạng URL cho cùng một video (`/jingxuan/vlog?modal_id=`,
    `/discover?modal_id=`, `/video/<id>` kèm tham số share). yt-dlp chỉ nhận
    dạng `/video/<id>` — đo ngày 2026-08-14: các dạng còn lại trả về
    `ERROR: Unsupported URL`. Quy về một dạng ngay ở cổng vào có thêm cái lợi
    phụ: hai người dán hai dạng URL của cùng một video sẽ ra cùng một chuỗi,
    nên chống trùng chặt hơn.

    ID tạm (link rút gọn, chưa biết ID thật) thì GIỮ NGUYÊN url gốc — dựng URL
    chuẩn từ một ID bịa ra sẽ tạo link chết.
    """
    khuon = _CANONICAL_URL.get(platform)
    if khuon is None or not video_id.isdigit():
        return url
    return khuon.format(video_id=video_id)


def parse_source_url(url: str) -> ParsedSource | None:
    """Nhận diện nguồn từ URL video.

    Trả về ``None`` **chỉ khi** chuỗi không phải URL http/https. Mọi URL hợp lệ
    đều được nhận: khớp mẫu thì lấy đúng ID video (cần cho chống trùng), không
    khớp thì rơi vào ``OTHER`` với ID tạm và để ``YtDlpDownloader`` thử — nó hỗ
    trợ hơn 1800 site. Đoán "nguồn này không tải được" ngay ở cổng vào chỉ chặn
    nhầm nguồn hợp lệ; sai hay đúng để bước tải trả lời bằng lỗi thật.
    """
    url = url.strip()
    if not url or not url.startswith(("http://", "https://")):
        return None

    for platform, pattern, provisional in _PATTERNS:
        m = pattern.search(url)
        if m:
            video_id = m.group(1)
            if provisional:
                #: Chưa biết ID thật (link rút gọn) — không dựng URL chuẩn từ
                #: một mã rút gọn được, giữ nguyên để yt-dlp tự resolve.
                return ParsedSource(platform, video_id, url, provisional)
            return ParsedSource(
                platform, video_id, _canonical_url(platform, video_id, url), provisional
            )

    # Không khớp mẫu nào: vẫn nhận. Domain quen thì giữ đúng nền tảng để thư
    # mục media và thống kê không lẫn, còn lại xếp vào OTHER.
    host = (urlparse(url).hostname or "").lower()
    for domain, platform in _DOMAIN_HINTS.items():
        if _host_matches(host, domain):
            return ParsedSource(platform, _fallback_id(url), url, provisional=True)

    return ParsedSource(SourcePlatform.OTHER, _fallback_id(url), url, provisional=True)


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
