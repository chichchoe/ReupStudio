"""Bước render: burn phụ đề tiếng Việt vào video, lập kế hoạch render_variants."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from reup_core.logging import get_logger
from reup_core.paths import (
    out_video,
    proxy_path,
    reframed_video,
    subtitle_ass_path,
    variant_video,
)

from ..errors import InvalidReframeModeError, PlatformLimitNotFoundError
from ..ffmpeg.burn import burn_subtitles, make_proxy, trim_video
from .cues import Cue
from .shortform.hook import build_hook_filter, hook_box, trim_slow_intro
from .shortform.reframe import DEFAULT_OUT_HEIGHT, DEFAULT_OUT_WIDTH, reframe_blur, reframe_crop
from .shortform.safe_area import SafeArea
from .shortform.split import silence_cut_points, split_by_duration
from .subtitle_ass import build_ass_style, write_ass

log = get_logger(__name__)

#: Giá trị hợp lệ của ``reframe_mode`` (``video.process_config["reframe_mode"]``).
#: Giá trị khác ném ``InvalidReframeModeError`` — xem ``render_variant``.
_VALID_REFRAME_MODES = {"blur", "crop"}


def render_with_subtitles(
    video_id: str,
    source: Path,
    cues: list[Cue],
    *,
    target: str = "master",
    progress_cb: Callable[[int], None] | None = None,
    duration_sec: float | None = None,
    safe: SafeArea,
    video_width: int | None,
    video_height: int | None,
) -> Path:
    """Ghi phụ đề ra file ASS rồi burn vào video, trả về đường dẫn kết quả.

    ``safe`` (vùng an toàn của nền tảng đích, đọc từ ``platform_limits``) cùng
    ``video_width``/``video_height`` quyết định lề và cỡ chữ — tất cả tính bằng
    pixel của khung, khớp với ``PlayRes`` ghi trong chính file ASS.

    Thiếu kích thước khung thì ném ``InvalidFrameSizeError`` chứ KHÔNG render
    tiếp bằng số mặc định: hỏng kiểu đó cho ra video trông bình thường nhưng
    mất sạch phụ đề, loại hỏng khó phát hiện nhất.
    """
    ass = write_ass(
        cues,
        subtitle_ass_path(video_id, "vi"),
        width=video_width,
        height=video_height,
        style=build_ass_style(safe, video_width, video_height),
    )
    dst = out_video(video_id, target)

    if dst.exists() and dst.stat().st_size > 0:
        log.info("render.skip_existing", path=str(dst))
        return dst

    burn_subtitles(
        source,
        ass,
        dst,
        progress_cb=progress_cb,
        duration_sec=duration_sec,
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


def _cues_for_segment(cues: list[Cue], start: float, end: float) -> list[Cue]:
    """Lọc cue rơi vào đoạn ``[start, end)`` và dịch mốc thời gian về gốc 0.

    Cue giao một phần với biên đoạn bị CẮT NGẮN theo biên (không loại bỏ toàn
    bộ) — tránh mất một phần lời thoại nằm sát ranh giới giữa hai tập.
    """
    segment: list[Cue] = []
    for c in cues:
        if c.end <= start or c.start >= end:
            continue
        new_start = max(0.0, c.start - start)
        new_end = min(end - start, c.end - start)
        if new_end <= new_start:
            continue
        segment.append(replace(c, start=new_start, end=new_end))
    return segment


def _reframe_if_horizontal(
    video_id: str,
    source: Path,
    video_width: int | None,
    video_height: int | None,
    reframe_mode: str,
) -> tuple[Path, int | None, int | None]:
    """Đổi khung ngang -> dọc nếu cần. Trả ``(nguồn để render, rộng, cao)``.

    Nguồn đã dọc thì giữ nguyên — scale đi scale lại chỉ làm giảm chất lượng.
    Thiếu kích thước (hiếm, ``probe`` luôn chạy trước) thì coi như không đổi
    khung, không ném lỗi.

    File trung gian đặt tên theo ``video_id`` + ``reframe_mode``, KHÔNG theo
    nền tảng hay tập: đổi khung không phụ thuộc hai thứ đó, nên chỉ tốn công
    đổi MỘT LẦN cho cả video rồi mọi lần gọi sau dùng lại.
    """
    is_horizontal = (
        video_width is not None and video_height is not None and video_width > video_height
    )
    if not is_horizontal:
        return source, video_width, video_height

    if reframe_mode not in _VALID_REFRAME_MODES:
        raise InvalidReframeModeError(
            f"reframe_mode '{reframe_mode}' không hợp lệ — chỉ nhận {sorted(_VALID_REFRAME_MODES)}."
        )
    reframed = reframed_video(video_id, reframe_mode)
    if reframed.exists() and reframed.stat().st_size > 0:
        log.info("render.reframe_skip_existing", path=str(reframed))
    else:
        reframe_fn = reframe_blur if reframe_mode == "blur" else reframe_crop
        reframe_fn(source, reframed)
        log.info("render.reframe_done", mode=reframe_mode, path=str(reframed))
    return reframed, DEFAULT_OUT_WIDTH, DEFAULT_OUT_HEIGHT


def render_normalized(
    video_id: str,
    source: Path,
    *,
    safe: SafeArea,
    video_width: int | None,
    video_height: int | None,
    target: str = "master",
    reframe_mode: str = "blur",
    hook_text: str | None = None,
    duration_sec: float | None = None,
    progress_cb: Callable[[int], None] | None = None,
) -> Path:
    """Chuẩn hoá video KHÔNG có phụ đề: đổi khung 9:16, chèn hook.

    Dùng cho video không có lời thoại (nhạc nền, vlog câm) hoặc video mà bước
    nhận dạng không nghe ra gì. Trước đây trường hợp này ``copyfile`` nguyên
    bản gốc sang thư mục ``out/`` rồi báo READY — hệ thống nói "xong" trong khi
    thứ giao ra đúng bằng thứ nhận vào. Chốt ngày 2026-08-14: vẫn chuẩn hoá,
    chỉ bỏ phần phụ đề.

    Không có hook thì chỉ CẮT (``trim_video``, ``-c copy``) chứ không encode
    lại: không có chữ nào để vẽ lên hình thì encode lại chỉ tốn thời gian và
    mất chất lượng.
    """
    dst = out_video(video_id, target)
    if dst.exists() and dst.stat().st_size > 0:
        log.info("render_normalized.skip_existing", path=str(dst))
        return dst

    render_source, out_width, out_height = _reframe_if_horizontal(
        video_id, source, video_width, video_height, reframe_mode
    )

    hook_filter: str | None = None
    if hook_text and out_width is not None and out_height is not None:
        hook_filter = build_hook_filter(hook_text, hook_box(safe), out_width, out_height)
    elif hook_text:
        log.warning("render_normalized.hook_skip_thieu_kich_thuoc", video_id=video_id)

    if hook_filter is None:
        trim_video(render_source, dst, duration_sec=duration_sec)
    else:
        #: ASS rỗng: không có cue nào để vẽ, nhưng ``burn_subtitles`` là chỗ
        #: duy nhất biết ghép ``hook_filter`` vào lệnh ffmpeg — đi qua đây để
        #: không nhân đôi logic dựng lệnh.
        ass = write_ass(
            [],
            subtitle_ass_path(video_id, f"vi.{target}"),
            width=out_width,
            height=out_height,
            style=build_ass_style(safe, out_width, out_height),
        )
        burn_subtitles(
            render_source,
            ass,
            dst,
            progress_cb=progress_cb,
            duration_sec=duration_sec,
            hook_filter=hook_filter,
        )

    log.info("render_normalized.done", path=str(dst), size=dst.stat().st_size)
    return dst


def render_variant(
    video_id: str,
    source: Path,
    cues: list[Cue],
    plan: VariantPlan,
    *,
    progress_cb: Callable[[int], None] | None = None,
    #: BẮT BUỘC. Trước đây tham số này có mặc định ``None`` và bước burn âm
    #: thầm rơi về lề cứng 120 — chính cơ chế đó che lỗi phụ đề bay ra ngoài
    #: khung suốt nhiều tháng. Không có vùng an toàn thì không đặt được lề,
    #: và render ra video mất phụ đề còn tệ hơn dừng lại.
    safe: SafeArea,
    video_width: int | None = None,
    video_height: int | None = None,
    reframe_mode: str = "blur",
    hook_text: str | None = None,
) -> Path:
    """Render MỘT tập của MỘT nền tảng đích (một dòng ``render_variants``).

    Idempotent (luật số 4 CLAUDE.md): file đích đã tồn tại và không rỗng thì
    bỏ qua, không render lại. Đoạn không có lời thoại VÀ không có hook chỉ
    được CẮT (``trim_video``, không re-encode, không gọi filter nào) — giống
    cách ``render_video_task`` xử lý video không lời thoại ở M1.

    THỨ TỰ BẮT BUỘC (M4-WK-05b): reframe (ngang -> dọc) chạy TRƯỚC, hook và
    phụ đề burn SAU. ``hook_box``/lề phụ đề (``SafeArea``) tính theo phần trăm
    của khung ĐÍCH (dọc 1080x1920 mặc định) — nếu burn hook/phụ đề trước rồi
    mới scale sang dọc, toạ độ đã tính sẵn bị kéo lệch theo tỉ lệ scale và chữ
    rơi ra ngoài khung hình. ĐỪNG đảo hai bước này.

    - ``video_width``/``video_height``: kích thước NGUỒN thật (từ bước
      ``probe`` M1). Chỉ đổi khung khi nguồn NGANG (``width > height``) —
      nguồn đã dọc giữ nguyên, không scale đi scale lại làm giảm chất lượng.
      Thiếu một trong hai (hiếm — ``probe`` M1 luôn chạy trước bước này) thì
      coi như không đổi khung, không ném lỗi.
    - File reframe trung gian (``reup_core.paths.reframed_video``) đặt tên
      theo ``video_id`` + ``reframe_mode``, KHÔNG theo nền tảng/tập — đổi
      khung không phụ thuộc platform hay part, nên chỉ tốn công đổi khung
      MỘT LẦN cho cả video: tập/nền tảng gọi ``render_variant`` đầu tiên tạo
      file, các lần gọi sau (tập khác, nền tảng khác) thấy file đã tồn tại
      thì tái sử dụng luôn (vẫn qua nhánh idempotent-skip bên dưới).
    - ``reframe_mode``: ``"blur"`` (mặc định, an toàn — không cắt mất ai) hoặc
      ``"crop"``. Giá trị khác ném ``InvalidReframeModeError`` — KHÔNG âm thầm
      rơi về mặc định (luật số 7 CLAUDE.md).
    - ``hook_text``: chỉ chèn vào TẬP ĐẦU TIÊN (``plan.part_index == 1``).
      Không truyền (``None``/rỗng) thì KHÔNG chèn hook gì cả — hàm này không
      tự sinh câu hook, chỉ dựng filter từ text truyền vào.
    - Tập đầu còn được ``trim_slow_intro`` cắt bớt phần mở đầu im lặng (dựa
      trên cue của chính tập đó, chỉ áp khi tập có lời thoại) trước khi burn.
    """
    dst = variant_video(video_id, plan.target_platform, plan.part_index)
    if dst.exists() and dst.stat().st_size > 0:
        log.info("render_variant.skip_existing", path=str(dst))
        return dst

    # --- Bước 1: reframe ngang -> dọc TRƯỚC (xem lý do thứ tự ở docstring) ---
    render_source, out_width, out_height = _reframe_if_horizontal(
        video_id, source, video_width, video_height, reframe_mode
    )

    # --- Bước 2: hook + cắt mở đầu ì ạch, chỉ áp cho TẬP ĐẦU (M4-WK-03) ---
    segment_cues = _cues_for_segment(cues, plan.start, plan.end)
    start, duration = plan.start, plan.duration
    hook_filter: str | None = None
    if plan.part_index == 1:
        if segment_cues:
            skip = trim_slow_intro(segment_cues)
            if skip > 0:
                start += skip
                duration -= skip
                segment_cues = _cues_for_segment(segment_cues, skip, plan.duration)
        if hook_text and safe is not None and out_width is not None and out_height is not None:
            hook_filter = build_hook_filter(hook_text, hook_box(safe), out_width, out_height)
        elif hook_text:
            log.warning(
                "render_variant.hook_skip_thieu_du_lieu",
                has_safe=safe is not None,
                has_out_dims=out_width is not None and out_height is not None,
            )

    # --- Bước 3: burn (hoặc chỉ cắt, nếu không có phụ đề lẫn hook) ---
    if not segment_cues and hook_filter is None:
        trim_video(render_source, dst, start=start, duration_sec=duration)
        log.info("render_variant.trim_only", path=str(dst), size=dst.stat().st_size)
        return dst

    #: Kích thước dùng để dựng ASS là khung SAU reframe (``out_width``/
    #: ``out_height``), không phải khung nguồn — burn chạy trên video đã đổi
    #: khung, lề tính theo khung nguồn sẽ lệch đúng bằng tỉ lệ scale.
    ass = write_ass(
        segment_cues,
        subtitle_ass_path(video_id, f"vi.{plan.target_platform}.p{plan.part_index}"),
        width=out_width,
        height=out_height,
        style=build_ass_style(safe, out_width, out_height),
    )
    burn_subtitles(
        render_source,
        ass,
        dst,
        progress_cb=progress_cb,
        duration_sec=duration,
        start=start,
        hook_filter=hook_filter,
    )
    log.info("render_variant.done", path=str(dst), size=dst.stat().st_size)
    return dst
