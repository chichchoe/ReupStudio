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


class TaskArgumentError(ReupError):
    """Task pipeline nhận sai thứ ở vị trí ``video_id``.

    Gần như luôn là do khai báo ``@app.task(bind=True)``: Celery chèn ``self``
    vào **tham số đầu tiên**, đúng chỗ ``pipeline_step`` đang đợi ``video_id``.
    Lỗi này thay cho ``ValueError: badly formed hexadecimal UUID string`` — câu
    đó không nói được nguyên nhân, từng làm bước tải chết câm suốt nhiều tháng.
    """


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


class InvalidReframeModeError(ReupError):
    """``reframe_mode`` không nằm trong tập giá trị hợp lệ (``"blur"``, ``"crop"``).

    Cố tình KHÔNG âm thầm rơi về mặc định ``"blur"`` khi gặp giá trị lạ (luật
    số 7 CLAUDE.md) — giá trị lạ thường là lỗi đánh máy trong ``process_config``,
    im lặng dùng mặc định sẽ khiến người cấu hình không biết lựa chọn của họ
    chưa hề được áp dụng.
    """


class InvalidFrameSizeError(ReupError):
    """Chiều rộng/cao khung hình <= 0 khi dựng phụ đề ASS.

    Cỡ chữ và lề phụ đề quy đổi theo chiều cao khung, nên số 0 hoặc số âm sẽ
    thành ``ZeroDivisionError`` hoặc một file ASS vô nghĩa. Báo lỗi rõ ngay
    thay vì render ra một video không có phụ đề mà không ai hiểu vì sao.
    """


class InvalidSplitLimitError(ReupError):
    """``max_duration_sec`` hoặc ``min_part_sec`` âm khi chia tập theo thời lượng.

    Số 0 của ``max_duration_sec`` là hợp lệ (nghĩa là không giới hạn); chỉ số
    ÂM mới là lỗi. Cố tình KHÔNG âm thầm coi số âm là "không giới hạn".
    """
