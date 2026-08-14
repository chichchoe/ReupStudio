"""Chuỗi task xử lý một video (chặng M1).

Mỗi task nhận ``video_id``, đọc trạng thái từ DB, ghi output ra ``media/work/``
và trả lại ``video_id`` cho bước sau. Mọi bước đều IDEMPOTENT: chạy lại lần hai
với cùng input phải cho cùng kết quả và không hỏng gì.
"""

from __future__ import annotations

from pathlib import Path

from celery import chain
from reup_core.db import session_scope
from reup_core.enums import M1_STEPS, PipelineStep, VideoStatus
from reup_core.logging import get_logger
from reup_core.models import PlatformLimit, RenderVariant, Subtitle, Video
from reup_core.paths import audio_path, raw_video, subtitle_path
from sqlalchemy import select

from .. import progress as prog
from ..celery_app import app
from ..config import get_settings
from ..errors import PlatformLimitNotFoundError, VideoTooLongError
from ..ffmpeg.burn import extract_audio
from ..ffmpeg.probe import probe
from ..milestones import milestones, percent_of
from ..pipeline.cues import Cue, cues_from_dicts, cues_to_dicts
from ..pipeline.dedup import fingerprint, is_similar_phash
from ..pipeline.download import download_video
from ..pipeline.render import (
    VariantPlan,
    build_proxy,
    plan_variants,
    render_normalized,
    render_variant,
    render_with_subtitles,
)
from ..pipeline.shortform.safe_area import SafeArea
from ..pipeline.subtitle_format import FormatOptions, format_cues
from ..pipeline.transcribe import transcribe
from ..pipeline.translate import translate_cues
from . import cost
from .base import pipeline_step

log = get_logger(__name__)

#: Nền tảng dùng khi video chưa cấu hình ``target_platforms`` — tiktok có
#: vùng an toàn phía dưới chặt nhất (bottom=0.18, xem seed platform_limits)
#: nên là lựa chọn an toàn nhất cho bản render "master" duy nhất hiện có.
_DEFAULT_TARGET_PLATFORM = "tiktok"


def _save_subtitle(session, video, lang: str, source: str, cues: list[Cue]) -> None:
    existing = session.scalar(
        select(Subtitle).where(Subtitle.video_id == video.id, Subtitle.lang == lang)
    )
    payload = cues_to_dicts(cues)
    if existing is None:
        session.add(Subtitle(video_id=video.id, lang=lang, source=source, cues=payload))
    elif not existing.edited_by_user:
        existing.cues = payload
        existing.source = source


def _load_subtitle(session, video, lang: str) -> list[Cue]:
    row = session.scalar(
        select(Subtitle).where(Subtitle.video_id == video.id, Subtitle.lang == lang)
    )
    return cues_from_dicts(row.cues) if row else []


def _target_platform(video) -> str:
    """Nền tảng đích dùng để tính vùng an toàn phụ đề cho bản render "master".

    Ở M4, pipeline vẫn chỉ sinh MỘT bản render "master" — tách nhiều
    ``render_variants`` theo từng nền tảng đích (luật số 8 CLAUDE.md) là việc
    của milestone sau. Vì vậy chỉ cần MỘT nền tảng đại diện: nền tảng đầu
    tiên trong ``target_platforms`` nếu có cấu hình, ngược lại mặc định
    tiktok (xem ``_DEFAULT_TARGET_PLATFORM``).
    """
    config = video.process_config or {}
    platforms = config.get("target_platforms")
    if isinstance(platforms, list) and platforms:
        return str(platforms[0])
    if isinstance(platforms, str) and platforms:
        return platforms
    return _DEFAULT_TARGET_PLATFORM


def _load_safe_area(session, platform: str) -> SafeArea:
    """Đọc vùng an toàn của một nền tảng từ bảng ``platform_limits``.

    Không tìm thấy dòng tương ứng thì báo lỗi rõ ràng (``PlatformLimitNotFoundError``)
    — KHÔNG âm thầm dùng số mặc định, vì làm vậy tái lập đúng kiểu hardcode
    mà bảng ``platform_limits`` sinh ra để dọn.
    """
    limit = session.get(PlatformLimit, platform)
    if limit is None:
        raise PlatformLimitNotFoundError(
            f"Không tìm thấy platform_limits cho nền tảng '{platform}' — "
            "không thể tính vùng an toàn phụ đề để burn."
        )
    area = limit.safe_area
    return SafeArea(top=area["top"], bottom=area["bottom"], left=area["left"], right=area["right"])


def _target_platforms(video) -> list[str]:
    """Danh sách nền tảng đích để render ``render_variants`` (M4-WK-05).

    Khác ``_target_platform`` (số ít, chỉ chọn MỘT nền tảng đại diện cho bản
    "master" của pipeline M1): ở đây lấy TOÀN BỘ ``target_platforms`` đã cấu
    hình, vì luật số 8 CLAUDE.md yêu cầu một video sinh nhiều ``render_variants``
    — một bản mỗi nền tảng đích, không phải 1-1.

    Thiếu cấu hình thì mặc định về đúng MỘT nền tảng (``_DEFAULT_TARGET_PLATFORM``)
    thay vì tự ý render cho mọi nền tảng đã biết trong hệ thống — giữ hành vi
    an toàn tương tự ``_target_platform``.
    """
    config = video.process_config or {}
    platforms = config.get("target_platforms")
    if isinstance(platforms, list) and platforms:
        return [str(p) for p in platforms]
    if isinstance(platforms, str) and platforms:
        return [platforms]
    return [_DEFAULT_TARGET_PLATFORM]


def _reframe_mode(video) -> str:
    """Chế độ đổi khung ngang->dọc (M4-WK-05b), đọc từ ``process_config``.

    Thiếu khoá (hoặc rỗng) mặc định ``"blur"`` (an toàn nhất — không cắt mất
    ai). Giá trị LẠ vẫn được trả nguyên văn, không tự chuẩn hoá ở đây —
    ``render_variant`` (tầng pipeline) mới là nơi kiểm hợp lệ và ném lỗi rõ
    ràng (luật số 7 CLAUDE.md); tầng ``tasks/`` chỉ đọc, không phán xét.
    """
    config = video.process_config or {}
    mode = config.get("reframe_mode")
    return str(mode) if mode else "blur"


def _hook_text(video) -> str | None:
    """Câu hook chèn 3 giây đầu (M4-WK-05b), đọc từ ``process_config``.

    Không có (hoặc rỗng) trả ``None`` — ``render_variant`` không tự sinh hook
    khi thiếu, đúng quyết định đã chốt ở task-9-brief.md (sinh bừa còn tệ hơn
    không có).
    """
    config = video.process_config or {}
    text = config.get("hook_text")
    return str(text) if text else None


def _load_platform_limits(session, targets: list[str]) -> dict[str, int]:
    """Đọc ``max_duration_sec`` của các nền tảng trong ``targets`` từ ``platform_limits``.

    Nền tảng không có dòng tương ứng đơn giản VẮNG MẶT trong dict trả về —
    ``plan_variants`` tự phát hiện thiếu và ném ``PlatformLimitNotFoundError``
    rõ ràng, không xử lý trùng lặp ở đây.
    """
    rows = session.scalars(select(PlatformLimit).where(PlatformLimit.platform.in_(targets))).all()
    return {row.platform: row.max_duration_sec for row in rows}


def _probe_variant_dims(path: Path) -> tuple[int | None, int | None]:
    """Đọc kích thước thật của file variant vừa render — best-effort.

    Lỗi probe không được làm hỏng cả job (file đã render xong, chỉ thiếu
    metadata phụ) — giống cách ``build_proxy`` xử lý lỗi tạo proxy.
    """
    try:
        info = probe(path)
        return info.width, info.height
    except Exception as exc:
        log.warning("render_variant.probe_failed", path=str(path), error=str(exc))
        return None, None


def _upsert_render_variant(
    session,
    video,
    plan: VariantPlan,
    out_path: Path,
    config_snapshot: dict,
    width: int | None,
    height: int | None,
) -> RenderVariant:
    """Tạo hoặc cập nhật dòng ``render_variants`` cho ``(video, platform, part)``.

    Idempotent ở tầng DB: khớp đúng ràng buộc duy nhất
    ``(video_id, target_platform, part_index)`` — chạy lại task không tạo dòng
    trùng, chỉ cập nhật lại dòng cũ.
    """
    row = session.scalar(
        select(RenderVariant).where(
            RenderVariant.video_id == video.id,
            RenderVariant.target_platform == plan.target_platform,
            RenderVariant.part_index == plan.part_index,
        )
    )
    if row is None:
        row = RenderVariant(
            video_id=video.id,
            target_platform=plan.target_platform,
            part_index=plan.part_index,
        )
        session.add(row)

    row.part_total = plan.part_total
    row.out_path = str(out_path)
    row.duration_sec = plan.duration
    row.width = width
    row.height = height
    row.file_size = out_path.stat().st_size if out_path.exists() else None
    row.config_snapshot = config_snapshot
    session.flush()
    return row


def _find_duplicate(session, video) -> tuple[Video, str] | None:
    """Tìm video đã có trùng với ``video``. Trả về ``(video_cũ, lý_do)``.

    Chỉ đối chiếu với video còn sống và chưa bị đánh dấu trùng — nhờ vậy bản
    trùng luôn trỏ về bản gốc, không tạo chuỗi trùng-của-trùng.
    """
    settings = get_settings()
    alive = select(Video).where(
        Video.id != video.id,
        Video.deleted_at.is_(None),
        Video.status != VideoStatus.SKIPPED.value,
    )

    if video.md5:
        # Trùng từng byte: có index trên (md5), lấy bản cũ nhất làm bản gốc.
        exact = session.scalars(
            alive.where(Video.md5 == video.md5).order_by(Video.created_at.asc()).limit(1)
        ).first()
        if exact is not None:
            return exact, "md5"

    if video.phash:
        # pHash phải so trong Python nên chỉ quét cửa sổ video gần đây nhất.
        candidates = session.scalars(
            alive.where(Video.phash.is_not(None))
            .order_by(Video.created_at.desc())
            .limit(settings.dedup_phash_scan_limit)
        ).all()
        for other in candidates:
            if is_similar_phash(
                video.phash, other.phash, max_distance=settings.dedup_phash_max_distance
            ):
                return other, "phash"

    return None


def _mark_duplicate(video, original: Video, reason: str) -> None:
    """Đánh dấu trùng và dừng pipeline tại đây (các bước sau tự bỏ qua)."""
    vid = str(video.id)
    video.status = VideoStatus.SKIPPED
    video.current_step = None
    video.flags = {
        **video.flags,
        "duplicate_of": str(original.id),
        "duplicate_reason": reason,
    }
    log.info("dedup.duplicate", video_id=vid, original_id=str(original.id), reason=reason)
    prog.status_changed(vid, VideoStatus.SKIPPED.value, None)


# --------------------------------------------------------------------------- #
# Các bước
# --------------------------------------------------------------------------- #


#: KHÔNG thêm ``bind=True`` vào đây. Celery sẽ chèn ``self`` vào tham số đầu,
#: đúng chỗ ``pipeline_step`` đợi ``video_id`` — bước tải sẽ chết 100% và chết
#: câm. Cần retry thì dùng ``autoretry_for=(DownloadBlockedError,)``, nó không
#: đụng tới danh sách tham số. ``tests/test_task_contract.py`` khoá luật này.
@app.task(name="reup.download_video")
@pipeline_step(PipelineStep.DOWNLOAD)
def download_video_task(session, video) -> dict:
    vid = str(video.id)

    def on_progress(percent: int) -> None:
        prog.progress(vid, PipelineStep.DOWNLOAD.value, percent)

    result = download_video(
        video.source_url,
        video.source_platform,
        video.source_video_id,
        progress_cb=on_progress,
    )

    video.raw_path = str(result.path)
    if result.title and not video.title_original:
        video.title_original = result.title
    if result.description and not video.desc_original:
        video.desc_original = result.description
    if result.author:
        video.source_author = result.author
    if result.view_count:
        video.view_count_source = result.view_count

    settings = get_settings()
    prints = fingerprint(result.path, frames=settings.dedup_phash_frames)
    video.md5 = prints.md5
    video.phash = prints.phash

    meta = {
        "size_bytes": result.path.stat().st_size,
        "md5": prints.md5,
        "phash": prints.phash,
    }
    if not settings.dedup_enabled:
        return meta

    found = _find_duplicate(session, video)
    if found is None:
        return meta

    original, reason = found
    _mark_duplicate(video, original, reason)
    return meta | {"duplicate_of": str(original.id), "duplicate_reason": reason}


@app.task(name="reup.probe_video")
@pipeline_step(PipelineStep.PROBE)
def probe_video_task(session, video) -> dict:
    vid = str(video.id)
    source = (
        Path(video.raw_path)
        if video.raw_path
        else raw_video(video.source_platform, video.source_video_id)
    )
    info = probe(source)

    limit = get_settings().max_video_duration_sec
    if info.duration_sec > limit:
        raise VideoTooLongError(
            f"Video dài {info.duration_sec:.0f}s, vượt giới hạn {limit}s. "
            "Bật chia tập ở chặng M4 hoặc nâng MAX_VIDEO_DURATION_SEC."
        )

    video.duration_sec = info.duration_sec
    video.width = info.width
    video.height = info.height
    video.fps = info.fps
    video.has_audio = info.has_audio
    video.flags = {**video.flags, "is_vertical": info.is_vertical}

    def on_proxy_progress(percent: int) -> None:
        # build_proxy là phần chạy lâu của bước probe -> ánh xạ vào 10-95%.
        prog.progress(vid, PipelineStep.PROBE.value, percent_of(percent, 100, lo=10, hi=95))

    build_proxy(vid, source, progress_cb=on_proxy_progress, duration_sec=info.duration_sec)
    return {
        "duration": info.duration_sec,
        "resolution": f"{info.width}x{info.height}",
        "fps": info.fps,
        "has_audio": info.has_audio,
        "codec": info.video_codec,
    }


@app.task(name="reup.transcribe_video")
@pipeline_step(PipelineStep.TRANSCRIBE)
def transcribe_video_task(session, video) -> dict:
    vid = str(video.id)
    source = Path(video.raw_path)

    if not video.has_audio:
        log.info("transcribe.no_audio", video_id=vid)
        _save_subtitle(session, video, "zh", "asr", [])
        video.flags = {**video.flags, "no_speech": True}
        return {"cues": 0, "skipped": "video không có audio"}

    wav = audio_path(vid)
    if not wav.exists():
        extract_audio(source, wav)

    cues = transcribe(
        wav, progress_cb=lambda p: prog.progress(vid, PipelineStep.TRANSCRIBE.value, p)
    )
    _save_subtitle(session, video, "zh", "asr", cues)

    if not cues:
        video.flags = {**video.flags, "no_speech": True}
    return {"cues": len(cues), "model": get_settings().whisper_model}


@app.task(name="reup.translate_video")
@pipeline_step(PipelineStep.TRANSLATE)
def translate_video_task(session, video) -> dict:
    vid = str(video.id)
    zh_cues = _load_subtitle(session, video, "zh")
    if not zh_cues:
        return {"cues": 0, "skipped": "không có phụ đề nguồn"}

    #: Chặn TRƯỚC khi gọi lượt đầu tiên. Chạm trần ngày hay trần tiền thì retry
    #: cũng hỏng y hệt — dừng ngay còn hơn đốt thêm hạn mức rồi mới chết.
    cost.kiem_han_muc(session)

    config = video.process_config or {}

    #: Ghi bằng TRANSACTION RIÊNG, commit ngay sau mỗi lô — KHÔNG dùng
    #: ``session`` của bước pipeline. Bản đầu dùng chung session và chỉ
    #: ``flush()``: các dòng nằm trong transaction chưa đóng nên tiến trình
    #: khác không đọc thấy cho tới lúc cả bước kết thúc. Kết quả: dựng hẳn một
    #: bảng để chia sẻ số liệu giữa các tiến trình rồi lại ghi theo cách ba
    #: tiếng sau mới thấy. Đo trên video thật mới lộ ra.
    lan_truoc: list = [None]

    def _ghi(usage) -> None:
        with session_scope() as phien_rieng:
            cost.ghi_usage(phien_rieng, video.id, usage, lan_truoc[0])
        lan_truoc[0] = usage

    def _dem_luot_gan_day() -> int:
        """Số lượt gọi của CẢ DỰ ÁN trong 60 giây qua, đọc từ ``cost_logs``.

        Phiên riêng để thấy được cả lượt gọi của tiến trình worker khác — đây
        chính là chỗ bản đầu làm sai khi đếm trong bộ nhớ.
        """
        with session_scope() as phien_rieng:
            return cost.dem_luot(phien_rieng, trong_giay=60)

    vi_cues = translate_cues(
        zh_cues,
        tone=config.get("tone", "doi_thuong"),
        glossary=config.get("glossary"),
        progress_cb=lambda p: prog.progress(vid, PipelineStep.TRANSLATE.value, p),
        on_usage=_ghi,
        dem_luot_gan_day=_dem_luot_gan_day,
    )
    _save_subtitle(session, video, "vi", "llm", vi_cues)
    tong = lan_truoc[0]
    return {
        "cues": len(vi_cues),
        "provider": get_settings().llm_provider,
        "luot_goi": tong.requests if tong else 0,
        "token": tong.total_tokens if tong else 0,
    }


@app.task(name="reup.format_subtitles")
@pipeline_step(PipelineStep.FORMAT_SUB)
def format_subtitles_task(session, video) -> dict:
    vid = str(video.id)
    settings = get_settings()
    vi_cues = _load_subtitle(session, video, "vi")
    if not vi_cues:
        return {"cues": 0, "skipped": "không có phụ đề tiếng Việt"}

    formatted = format_cues(
        vi_cues,
        FormatOptions(
            max_chars_per_line=settings.sub_max_chars_per_line,
            max_lines=settings.sub_max_lines,
            min_duration=settings.sub_min_duration,
        ),
        progress_cb=lambda p: prog.progress(vid, PipelineStep.FORMAT_SUB.value, p),
    )
    _save_subtitle(session, video, "vi", "llm", formatted)
    return {"cues_before": len(vi_cues), "cues_after": len(formatted)}


@app.task(name="reup.render_video")
@pipeline_step(PipelineStep.RENDER)
def render_video_task(session, video) -> dict:
    vid = str(video.id)
    source = Path(video.raw_path)
    vi_cues = _load_subtitle(session, video, "vi")

    platform = _target_platform(video)
    safe = _load_safe_area(session, platform)

    if not vi_cues:
        #: Không có lời thoại (nhạc nền, vlog câm) — VẪN chuẩn hoá 9:16 và chèn
        #: hook, chỉ bỏ phần phụ đề. Trước đây nhánh này copy nguyên bản gốc rồi
        #: báo READY: hệ thống nói "xong" trong khi thứ giao ra đúng bằng thứ
        #: nhận vào. Chốt ngày 2026-08-14 theo yêu cầu chủ dự án.
        out = render_normalized(
            vid,
            source,
            safe=safe,
            video_width=video.width,
            video_height=video.height,
            reframe_mode=_reframe_mode(video),
            hook_text=_hook_text(video),
            duration_sec=video.duration_sec,
            progress_cb=lambda p: prog.progress(vid, PipelineStep.RENDER.value, p),
        )
        video.out_path = str(out)
        video.status = VideoStatus.READY
        video.current_step = None
        #: Cờ để Thư viện lọc ra và người dùng biết vì sao bản này không có chữ.
        video.flags = {**(video.flags or {}), "no_speech": True}
        prog.status_changed(vid, VideoStatus.READY.value, None)
        return {
            "subtitles": 0,
            "out_size": out.stat().st_size,
            "note": "không có lời thoại — đã chuẩn hoá khung hình, không có phụ đề",
        }

    out = render_with_subtitles(
        vid,
        source,
        vi_cues,
        progress_cb=lambda p: prog.progress(vid, PipelineStep.RENDER.value, p),
        duration_sec=video.duration_sec,
        safe=safe,
        video_width=video.width,
        video_height=video.height,
    )
    video.out_path = str(out)
    video.status = VideoStatus.READY
    video.current_step = None
    prog.status_changed(vid, VideoStatus.READY.value, None)
    return {
        "subtitles": len(vi_cues),
        "out_size": out.stat().st_size,
        "srt": str(subtitle_path(vid, "vi")),
    }


@app.task(name="reup.render_variants")
@pipeline_step(PipelineStep.SHORTFORM)
def render_variants_task(session, video) -> dict:
    """M4-WK-05 — render nhiều bản, một bản mỗi nền tảng đích (luật số 8 CLAUDE.md).

    Task chỉ điều phối: đọc ``platform_limits``, gọi ``plan_variants`` (hàm
    thuần) để lập kế hoạch, gọi ``render_variant`` cho từng tập rồi ghi kết quả
    vào bảng ``render_variants``. Idempotent: ``render_variant`` tự bỏ qua nếu
    file đích đã tồn tại và hợp lệ. Khác ``render_video_task`` (M1, một bản
    "master" duy nhất) — task này được gọi riêng (Task 7 làm API kích hoạt),
    không nằm trong chain M1.

    Từ M4-WK-05b: đọc thêm ``reframe_mode``/``hook_text`` từ ``process_config``
    (qua ``_reframe_mode``/``_hook_text``) rồi truyền cho ``render_variant`` —
    quyết định đổi khung ngang->dọc và chèn hook nằm ở tầng pipeline, tầng này
    chỉ đọc cấu hình và chuyển tiếp.

    Dùng ``PipelineStep.SHORTFORM`` (không phải ``RENDER``) cho decorator lẫn
    ``prog.progress`` — ``RENDER`` đã bị ``render_video_task`` (M1) chiếm.
    Dùng chung sẽ khiến thanh tiến trình bước "render" mà frontend đang nghe
    tụt về 0% rồi leo lại khi hai task chạy nối tiếp, trông như render lỗi
    phải chạy lại (phát hiện ở review Task 6).
    """
    vid = str(video.id)
    source = Path(video.raw_path)
    vi_cues = _load_subtitle(session, video, "vi")

    targets = _target_platforms(video)
    limits = _load_platform_limits(session, targets)
    plans = plan_variants(video.duration_sec, targets, limits, vi_cues)
    reframe_mode = _reframe_mode(video)
    hook_text = _hook_text(video)

    done_at = milestones(len(plans))
    for i, plan in enumerate(plans, start=1):
        safe = _load_safe_area(session, plan.target_platform)
        out = render_variant(
            vid,
            source,
            vi_cues,
            plan,
            safe=safe,
            video_width=video.width,
            video_height=video.height,
            reframe_mode=reframe_mode,
            hook_text=hook_text,
        )
        width, height = _probe_variant_dims(out)
        snapshot = {
            "target_platform": plan.target_platform,
            "part_index": plan.part_index,
            "part_total": plan.part_total,
            "start": plan.start,
            "end": plan.end,
            "max_duration_sec": limits[plan.target_platform],
            "safe_area": {
                "top": safe.top,
                "bottom": safe.bottom,
                "left": safe.left,
                "right": safe.right,
            },
            "process_config": video.process_config,
        }
        _upsert_render_variant(session, video, plan, out, snapshot, width, height)
        if i in done_at:
            prog.progress(vid, PipelineStep.SHORTFORM.value, percent_of(i, len(plans)))

    video.status = VideoStatus.READY
    video.current_step = None
    prog.status_changed(vid, VideoStatus.READY.value, None)
    return {"variants": len(plans), "targets": targets}


# --------------------------------------------------------------------------- #
# Điều phối
# --------------------------------------------------------------------------- #

_STEP_TASKS = {
    PipelineStep.DOWNLOAD: download_video_task,
    PipelineStep.PROBE: probe_video_task,
    PipelineStep.TRANSCRIBE: transcribe_video_task,
    PipelineStep.TRANSLATE: translate_video_task,
    PipelineStep.FORMAT_SUB: format_subtitles_task,
    PipelineStep.RENDER: render_video_task,
}


def _build_chain(video_id: str, steps):
    #: ``si`` = immutable signature: mỗi task tự đọc trạng thái từ DB, không
    #: truyền kết quả qua lại — nhờ vậy retry một bước không cần chạy lại bước trước.
    return chain(*[_STEP_TASKS[s].si(str(video_id)) for s in steps])


@app.task(name="reup.process_video")
def process_video(video_id: str) -> str:
    """Chạy toàn bộ pipeline M1 cho một video."""
    log.info("pipeline.start", video_id=video_id)
    _build_chain(video_id, M1_STEPS).apply_async()
    return video_id


@app.task(name="reup.retry_from_step")
def retry_from_step(video_id: str, step: str | None = None) -> str:
    """Chạy lại từ một bước cụ thể (mặc định: từ đầu)."""
    if step:
        try:
            start = M1_STEPS.index(PipelineStep(step))
        except (ValueError, KeyError):
            start = 0
    else:
        start = 0
    steps = M1_STEPS[start:]
    log.info("pipeline.retry", video_id=video_id, from_step=steps[0].value)
    _build_chain(video_id, steps).apply_async()
    return video_id
