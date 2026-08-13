"""Bước render: burn phụ đề tiếng Việt vào video, lập kế hoạch render_variants."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from reup_core.logging import get_logger
from reup_core.paths import out_video, proxy_path, subtitle_path

from ..errors import PlatformLimitNotFoundError
from ..ffmpeg.burn import burn_subtitles, make_proxy
from .cues import Cue, write_srt
from .shortform.safe_area import SafeArea
from .shortform.split import silence_cut_points, split_by_duration

log = get_logger(__name__)


def render_with_subtitles(
    video_id: str,
    source: Path,
    cues: list[Cue],
    *,
    target: str = "master",
    progress_cb: Callable[[int], None] | None = None,
    duration_sec: float | None = None,
    safe: SafeArea | None = None,
    video_height: int | None = None,
) -> Path:
    """Ghi SRT rồi burn vào video, trả về đường dẫn file kết quả.

    ``safe``/``video_height`` (tuỳ chọn) được chuyển thẳng cho
    ``burn_subtitles`` để đặt lề dưới phụ đề theo vùng an toàn của nền tảng
    đích — không truyền thì giữ lề mặc định cũ.
    """
    srt = write_srt(cues, subtitle_path(video_id, "vi"))
    dst = out_video(video_id, target)

    if dst.exists() and dst.stat().st_size > 0:
        log.info("render.skip_existing", path=str(dst))
        return dst

    burn_subtitles(
        source,
        srt,
        dst,
        progress_cb=progress_cb,
        duration_sec=duration_sec,
        safe=safe,
        video_height=video_height,
    )
    log.info("render.done", path=str(dst), size=dst.stat().st_size)
    return dst


def build_proxy(
    video_id: str,
    source: Path,
    *,
    progress_cb: Callable[[int], None] | None = None,
    duration_sec: float | None = None,
) -> Path | None:
    """Bản 540p cho preview trên web. Lỗi ở đây không được làm hỏng cả job."""
    dst = proxy_path(video_id)
    if dst.exists():
        return dst
    try:
        return make_proxy(source, dst, progress_cb=progress_cb, duration_sec=duration_sec)
    except Exception as exc:
        log.warning("proxy.failed", error=str(exc))
        return None


# --------------------------------------------------------------------------- #
# M4-WK-05 — lập kế hoạch render_variants (hàm THUẦN, không chạm DB/ffmpeg)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VariantPlan:
    """Kế hoạch render MỘT tập của MỘT nền tảng đích.

    ``part_index``/``part_total`` tính riêng cho ``target_platform`` này — hai
    nền tảng khác nhau của cùng một video có thể chia số tập khác nhau (giới
    hạn thời lượng khác nhau), nên ``part_total`` KHÔNG phải tổng toàn bộ danh
    sách kế hoạch trả về.
    """

    target_platform: str
    part_index: int  # 1-based
    part_total: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def plan_variants(
    duration_sec: float,
    targets: list[str],
    limits: dict[str, int],
    cues: list[Cue] | None = None,
) -> list[VariantPlan]:
    """Lập kế hoạch render_variants cho từng nền tảng đích.

    Với mỗi nền tảng trong ``targets``, chia video theo ``max_duration_sec``
    của chính nền tảng đó (đọc từ ``limits``, do tầng ``tasks/`` truy vấn bảng
    ``platform_limits`` rồi truyền vào — hàm này KHÔNG chạm DB) bằng
    ``split_by_duration`` (M4-WK-04). ``cues`` (nếu có) sinh ``cut_points`` từ
    khoảng lặng giữa các câu (``silence_cut_points``) để việc chia tập không
    cắt giữa câu — dùng CHUNG một danh sách ``cut_points`` cho mọi nền tảng vì
    nó chỉ phụ thuộc lời thoại, không phụ thuộc giới hạn thời lượng.

    ``targets`` rỗng trả về danh sách rỗng, không ném lỗi (video có thể chưa
    được cấu hình nền tảng đích nào — không phải lỗi). Nền tảng có trong
    ``targets`` nhưng KHÔNG có trong ``limits`` thì ném ``PlatformLimitNotFoundError``
    rõ ràng — im lặng bỏ qua sẽ khiến video "biến mất" khỏi một nền tảng mà
    không ai biết vì sao (đúng tinh thần luật số 5 CLAUDE.md: không âm thầm
    dùng giá trị mặc định khi thiếu cấu hình).
    """
    if not targets:
        return []

    cut_points = silence_cut_points(cues) if cues else []

    plans: list[VariantPlan] = []
    for target in targets:
        if target not in limits:
            raise PlatformLimitNotFoundError(
                f"Không tìm thấy platform_limits cho nền tảng '{target}' — "
                "không thể lập kế hoạch render_variants."
            )
        parts = split_by_duration(duration_sec, limits[target], cut_points=cut_points)
        part_total = len(parts)
        plans.extend(
            VariantPlan(
                target_platform=target,
                part_index=part.index,
                part_total=part_total,
                start=part.start,
                end=part.end,
            )
            for part in parts
        )
    return plans
