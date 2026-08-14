"""Downloader dựa trên yt-dlp — dùng chung cho hầu hết nền tảng Trung Quốc.

Dùng yt-dlp như THƯ VIỆN, không gọi CLI: bắt lỗi rõ ràng hơn và lấy được
metadata đầy đủ.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reup_core.enums import SourcePlatform
from reup_core.logging import get_logger

from ..config import get_settings
from ..errors import DownloadBlockedError, DownloadError
from .base import BaseDownloader, DownloadResult

log = get_logger(__name__)

_BLOCKED_HINTS = ("403", "429", "forbidden", "rate limit", "blocked", "geo")


def _cookie_opts(settings) -> dict[str, Any]:
    """Tuỳ chọn cookie cho yt-dlp, dựng từ cấu hình.

    Một số nền tảng (Douyin rõ nhất) từ chối mọi request không kèm cookie —
    thông báo của họ ghi "Fresh cookies (not necessarily logged in) are
    needed", nghĩa là cookie KHÁCH của một trình duyệt đã ghé trang là đủ,
    không cần tài khoản.

    File cookie được ưu tiên hơn đọc trình duyệt: trong Docker không có trình
    duyệt nào để đọc, nên chỉ đường file mới chạy được ở cả hai môi trường.
    Không cấu hình gì thì KHÔNG thêm tuỳ chọn nào — không tự ý đụng vào trình
    duyệt của người dùng khi chưa được yêu cầu.
    """
    cookie_file = (settings.ytdlp_cookie_file or "").strip()
    if cookie_file:
        if not Path(cookie_file).exists():
            raise DownloadError(f"YTDLP_COOKIE_FILE trỏ tới file không tồn tại: {cookie_file}")
        log.info("download.cookie", nguon="file")
        return {"cookiefile": cookie_file}

    browser = (settings.ytdlp_cookies_from_browser or "").strip().lower()
    if browser:
        log.info("download.cookie", nguon="browser", browser=browser)
        #: yt-dlp nhận tuple ``(tên, hồ_sơ, keyring, container)``; chỉ tên là bắt buộc.
        return {"cookiesfrombrowser": (browser,)}

    return {}


class YtDlpDownloader(BaseDownloader):
    """Cấu hình mặc định ưu tiên bản chất lượng cao nhất, mp4 nếu có."""

    platform = SourcePlatform.OTHER

    #: Nền tảng con ghi đè để thêm header / cookie riêng.
    extra_opts: dict[str, Any] = {}

    def build_opts(self, dest_dir: Path, progress_cb=None) -> dict[str, Any]:
        settings = get_settings()

        def hook(d: dict[str, Any]) -> None:
            if progress_cb is None or d.get("status") != "downloading":
                return
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            if total:
                progress_cb(int(done / total * 100))

        opts: dict[str, Any] = {
            "outtmpl": str(dest_dir / "source.%(ext)s"),
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 3,
            "progress_hooks": [hook],
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                )
            },
        }
        opts.update(self.extra_opts)
        #: Áp SAU ``extra_opts`` để cấu hình cookie không bị nền tảng con ghi đè.
        opts.update(_cookie_opts(settings))
        return opts

    def download(self, url: str, dest_dir: Path, *, progress_cb=None) -> DownloadResult:
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:  # pragma: no cover
            raise DownloadError("Chưa cài yt-dlp: pip install yt-dlp") from exc

        dest_dir.mkdir(parents=True, exist_ok=True)
        opts = self.build_opts(dest_dir, progress_cb)

        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as exc:
            message = str(exc).lower()
            if any(hint in message for hint in _BLOCKED_HINTS):
                raise DownloadBlockedError(
                    f"Nền tảng chặn request — cần đổi proxy. Chi tiết: {exc}"
                ) from exc
            raise DownloadError(f"Tải thất bại: {exc}") from exc

        if info is None:
            raise DownloadError("yt-dlp không trả về metadata")
        if "entries" in info:  # link playlist — lấy phần tử đầu
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise DownloadError("Playlist rỗng")
            info = entries[0]

        path = self._find_output(dest_dir)
        return DownloadResult(
            path=path,
            source_video_id=str(info.get("id") or path.stem),
            title=info.get("title"),
            description=info.get("description"),
            author=info.get("uploader") or info.get("channel"),
            view_count=info.get("view_count"),
            duration_sec=float(info["duration"]) if info.get("duration") else None,
            width=info.get("width"),
            height=info.get("height"),
            raw_meta={
                k: info.get(k)
                for k in (
                    "id",
                    "title",
                    "uploader",
                    "view_count",
                    "like_count",
                    "upload_date",
                    "webpage_url",
                    "duration",
                    "width",
                    "height",
                )
            },
        )

    @staticmethod
    def _find_output(dest_dir: Path) -> Path:
        candidates = sorted(
            (p for p in dest_dir.glob("source.*") if p.suffix != ".part"),
            key=lambda p: p.stat().st_size,
            reverse=True,
        )
        if not candidates:
            raise DownloadError(f"Không tìm thấy file đã tải trong {dest_dir}")
        return candidates[0]
