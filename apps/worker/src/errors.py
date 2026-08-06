"""Exception có nghĩa. Không bao giờ ``raise Exception("lỗi")``."""

from __future__ import annotations


class ReupError(Exception):
    """Gốc của mọi lỗi trong worker."""


class DownloadError(ReupError):
    pass


class DownloadBlockedError(DownloadError):
    """Nền tảng chặn (403/429) — thường cần đổi proxy."""


class UnsupportedSourceError(DownloadError):
    pass


class FFmpegError(ReupError):
    pass


class ProbeError(ReupError):
    pass


class TranscribeError(ReupError):
    pass


class TranslateError(ReupError):
    pass


class VideoTooLongError(ReupError):
    pass


class DedupError(ReupError):
    """Không tính hoặc không so sánh được dấu vân tay video."""
