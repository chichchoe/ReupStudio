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
        _ = settings  # giữ chỗ cho proxy/cookie ở M2
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
                for k in ("id", "title", "uploader", "view_count", "like_count",
                          "upload_date", "webpage_url", "duration", "width", "height")
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
