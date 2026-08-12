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


class PlatformLimitNotFoundError(ReupError):
    """Không tìm thấy dòng ``platform_limits`` cho nền tảng cần tính vùng an toàn.

    Cố tình KHÔNG âm thầm dùng số mặc định khi thiếu dòng — làm vậy là tái
    lập đúng kiểu hardcode mà bảng ``platform_limits`` sinh ra để dọn (luật
    số 5 CLAUDE.md).
    """


class InvalidSplitLimitError(ReupError):
    """``max_duration_sec`` hoặc ``min_part_sec`` âm khi chia tập theo thời lượng.

    Số 0 của ``max_duration_sec`` là hợp lệ (nghĩa là không giới hạn); chỉ số
    ÂM mới là lỗi. Cố tình KHÔNG âm thầm coi số âm là "không giới hạn".
    """
