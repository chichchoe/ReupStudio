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
    PipelineStep.TTS,
    PipelineStep.DETECT,
    PipelineStep.INPAINT,
    PipelineStep.RENDER,
)

#: Pipeline dừng lại giữa chừng để người dùng CHỌN MODEL AI rồi mới dịch
#: (chốt 2026-08-14). Dừng đúng sau bước nhận dạng chứ không sớm hơn, vì tới
#: lúc đó mới biết video có bao nhiêu câu thoại — thông tin quyết định chọn
#: model nào: 672 câu thì cần model hạn mức cao, 50 câu thì chọn model tốt hơn.
#:
#: Nửa đầu chạy tự động ngay sau khi dán link; xong thì video sang trạng thái
#: ``REVIEW`` và hiện ở tab "Chờ dịch".
M1_STEPS_TRUOC_DICH: tuple[PipelineStep, ...] = (
    PipelineStep.DOWNLOAD,
    PipelineStep.PROBE,
    PipelineStep.TRANSCRIBE,
)

#: Nửa sau chỉ chạy khi người dùng bấm Dịch (hoặc khi bật ``auto_translate``
#: trong ``process_config`` — lối cho chặng M7 luồng tự động).
#: Chặng 2 — chạy khi người dùng bấm Dịch. Dừng lại sau khi ĐÃ có giọng đọc,
#: để người dùng đọc lại bản dịch và nghe thử trước khi ghép vào video.
#:
#: Cố ý đặt các bước NẶNG (dò rồi xoá chữ cứng, mất hàng chục phút tới hàng
#: tiếng) ở chặng 3, tức SAU chỗ duyệt: người dùng không ưng bản dịch hay giọng
#: đọc thì không đốt ngần ấy thời gian máy vào một bản sẽ bỏ đi.
M1_STEPS_SAU_DICH: tuple[PipelineStep, ...] = (
    PipelineStep.TRANSLATE,
    PipelineStep.FORMAT_SUB,
    PipelineStep.TTS,
)

#: Chặng 3 — chạy khi người dùng đã duyệt bản dịch và giọng đọc.
M1_STEPS_SAU_DUYET: tuple[PipelineStep, ...] = (
    PipelineStep.DETECT,
    PipelineStep.INPAINT,
    PipelineStep.RENDER,
)


class SourcePlatform(StrEnum):
    """Nền tảng nguồn lấy video về.

    Ban đầu chỉ có 5 nền tảng Trung Quốc. Từ khi ô dán link nhận mọi URL
    http/https (yt-dlp hỗ trợ hơn 1800 site), danh sách này KHÔNG còn là cổng
    chặn — nó chỉ để nhận đúng ID video phục vụ chống trùng và đặt thư mục.
    Nguồn không nằm trong danh sách rơi vào ``OTHER`` và vẫn tải bình thường.
    """

    # --- Trung Quốc ---
    DOUYIN = "douyin"
    BILIBILI = "bilibili"
    KUAISHOU = "kuaishou"
    XIAOHONGSHU = "xiaohongshu"
    WEIBO = "weibo"
    # --- Quốc tế ---
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    TWITTER = "twitter"
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


class PresetKind(StrEnum):
    """Loại preset cấu hình chỉnh được từ giao diện — đổi preset không cần sửa code."""

    FILTER = "filter"  # điều kiện lọc video nguồn
    PROCESS = "process"  # cấu hình xử lý (tone, phụ đề burn-in, ...)
    ANTIDUP = "antidup"  # cấu hình chống trùng
    SUBTITLE = "subtitle"  # cấu hình hiển thị phụ đề (font, cỡ chữ, ...)
