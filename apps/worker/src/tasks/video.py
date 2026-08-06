"""Chuỗi task xử lý một video (chặng M1).

Mỗi task nhận ``video_id``, đọc trạng thái từ DB, ghi output ra ``media/work/``
và trả lại ``video_id`` cho bước sau. Mọi bước đều IDEMPOTENT: chạy lại lần hai
với cùng input phải cho cùng kết quả và không hỏng gì.
"""

from __future__ import annotations

from pathlib import Path

from celery import chain
from reup_core.enums import M1_STEPS, PipelineStep, VideoStatus
from reup_core.logging import get_logger
from reup_core.models import Subtitle, Video
from reup_core.paths import audio_path, raw_video, subtitle_path
from sqlalchemy import select

from .. import progress as prog
from ..celery_app import app
from ..config import get_settings
from ..errors import VideoTooLongError
from ..ffmpeg.burn import extract_audio
from ..ffmpeg.probe import probe
from ..pipeline.cues import Cue, cues_from_dicts, cues_to_dicts
from ..pipeline.dedup import fingerprint, is_similar_phash
from ..pipeline.download import download_video
from ..pipeline.render import build_proxy, render_with_subtitles
from ..pipeline.subtitle_format import FormatOptions, format_cues
from ..pipeline.transcribe import transcribe
from ..pipeline.translate import translate_cues
from .base import pipeline_step

log = get_logger(__name__)


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


def _find_duplicate(session, video) -> tuple[Video, str] | None:
    """Tìm video đã có trùng với ``video``. Trả về ``(video_cũ, lý_do)``.

    Chỉ đối chiếu với video còn sống và chưa bị đánh dấu trùng — nhờ vậy bản
    trùng luôn trỏ về bản gốc, không tạo chuỗi trùng-của-trùng.
    """
    settings = get_settings()
    alive = (
        select(Video)
        .where(
            Video.id != video.id,
            Video.deleted_at.is_(None),
            Video.status != VideoStatus.SKIPPED.value,
        )
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


@app.task(name="reup.download_video", bind=True, max_retries=2, default_retry_delay=30)
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
    source = Path(video.raw_path) if video.raw_path else raw_video(
        video.source_platform, video.source_video_id
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

    build_proxy(str(video.id), source)
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

    config = video.process_config or {}
    vi_cues = translate_cues(
        zh_cues,
        tone=config.get("tone", "doi_thuong"),
        glossary=config.get("glossary"),
        progress_cb=lambda p: prog.progress(vid, PipelineStep.TRANSLATE.value, p),
    )
    _save_subtitle(session, video, "vi", "llm", vi_cues)
    return {"cues": len(vi_cues), "provider": get_settings().llm_provider}


@app.task(name="reup.format_subtitles")
@pipeline_step(PipelineStep.FORMAT_SUB)
def format_subtitles_task(session, video) -> dict:
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
    )
    _save_subtitle(session, video, "vi", "llm", formatted)
    return {"cues_before": len(vi_cues), "cues_after": len(formatted)}


@app.task(name="reup.render_video")
@pipeline_step(PipelineStep.RENDER)
def render_video_task(session, video) -> dict:
    vid = str(video.id)
    source = Path(video.raw_path)
    vi_cues = _load_subtitle(session, video, "vi")

    if not vi_cues:
        # Không có lời thoại: giữ nguyên video, chỉ copy sang thư mục out.
        from shutil import copyfile

        from reup_core.paths import out_video

        dst = out_video(vid)
        if not dst.exists():
            copyfile(source, dst)
        video.out_path = str(dst)
        video.status = VideoStatus.READY
        prog.status_changed(vid, VideoStatus.READY.value, None)
        return {"subtitles": 0, "note": "không có lời thoại, giữ nguyên video"}

    out = render_with_subtitles(vid, source, vi_cues)
    video.out_path = str(out)
    video.status = VideoStatus.READY
    video.current_step = None
    prog.status_changed(vid, VideoStatus.READY.value, None)
    return {
        "subtitles": len(vi_cues),
        "out_size": out.stat().st_size,
        "srt": str(subtitle_path(vid, "vi")),
    }


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
