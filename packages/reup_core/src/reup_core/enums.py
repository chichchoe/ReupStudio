"""Enum dùng chung cho toàn hệ thống.

Giá trị của enum được lưu thẳng vào DB dạng chuỗi (không dùng native enum của
Postgres) để tránh phải migration mỗi lần thêm giá trị mới.
"""

from __future__ import annotations

try:  # Python >= 3.11
    from enum import StrEnum
except ImportError:  # Python 3.10
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        def __str__(self) -> str:
            return str(self.value)


class VideoStatus(StrEnum):
    QUEUED = "queued"  # chờ tới lượt xử lý
    RUNNING = "running"  # đang chạy pipeline
    REVIEW = "review"  # cần người duyệt trước khi đi tiếp
    READY = "ready"  # đã render xong, chờ xếp lịch
    SCHEDULED = "scheduled"  # đã có lịch đăng
    POSTED = "posted"  # đã đăng ít nhất một nơi
    ERROR = "error"
    SKIPPED = "skipped"  # bị bộ lọc loại bỏ


class PipelineStep(StrEnum):
    DOWNLOAD = "download"
    PROBE = "probe"
    TRANSCRIBE = "transcribe"
    TRANSLATE = "translate"
    FORMAT_SUB = "format_sub"
    DETECT = "detect"  # M3
    INPAINT = "inpaint"  # M3
    SHORTFORM = "shortform"  # M4
    TTS = "tts"  # M8
    RENDER = "render"
    QC = "qc"
    UPLOAD = "upload"  # M5


#: Thứ tự các bước của pipeline M1. Dùng để tính tiến trình và cho phép retry
#: từ một bước cụ thể.
M1_STEPS: tuple[PipelineStep, ...] = (
    PipelineStep.DOWNLOAD,
    PipelineStep.PROBE,
    PipelineStep.TRANSCRIBE,
    PipelineStep.TRANSLATE,
    PipelineStep.FORMAT_SUB,
    PipelineStep.RENDER,
)


class SourcePlatform(StrEnum):
    """Nền tảng nguồn (Trung Quốc)."""

    DOUYIN = "douyin"
    BILIBILI = "bilibili"
    KUAISHOU = "kuaishou"
    XIAOHONGSHU = "xiaohongshu"
    WEIBO = "weibo"
    OTHER = "other"


class Platform(StrEnum):
    """Nền tảng đăng (Việt Nam) — tập trung vào video ngắn."""

    TIKTOK = "tiktok"
    YOUTUBE = "youtube"  # Shorts
    FACEBOOK = "facebook"  # Reels
    INSTAGRAM = "instagram"  # Reels
    ZALO = "zalo"


class LicenseStatus(StrEnum):
    """Tình trạng quyền sử dụng của kênh nguồn.

    ``UNKNOWN`` là mặc định và **chặn luồng tự động** — đây là chốt an toàn
    pháp lý, không được bỏ qua vì tiện.
    """

    UNKNOWN = "unknown"
    PERMITTED = "permitted"  # đã xin phép creator
    LICENSED = "licensed"  # có hợp đồng / đã mua license
    OPEN = "open"  # CC / public domain
    OWN = "own"  # nội dung của chính mình


#: Các trạng thái license cho phép luồng tự động chạy.
AUTO_ALLOWED_LICENSES = frozenset(
    {
        LicenseStatus.PERMITTED,
        LicenseStatus.LICENSED,
        LicenseStatus.OPEN,
        LicenseStatus.OWN,
    }
)
