"""Chuỗi task xử lý một video (chặng M1).

Mỗi task nhận ``video_id``, đọc trạng thái từ DB, ghi output ra ``media/work/``
và trả lại ``video_id`` cho bước sau. Mọi bước đều IDEMPOTENT: chạy lại lần hai
với cùng input phải cho cùng kết quả và không hỏng gì.
"""

from __future__ import annotations

from pathlib import Path

from celery import chain
from reup_core.db import session_scope
from reup_core.enums import (
    M1_STEPS,
    M1_STEPS_SAU_DICH,
    M1_STEPS_SAU_DUYET,
    M1_STEPS_TRUOC_DICH,
    PipelineStep,
    VideoStatus,
)
from reup_core.logging import get_logger
from reup_core.models import MaskRegion, PlatformLimit, RenderVariant, Subtitle, Video
from reup_core.paths import (
    audio_path,
    cleaned_video,
    raw_video,
    subtitle_path,
    voice_parts_dir,
    voice_track,
)
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from .. import progress as prog
from ..celery_app import app
from ..config import get_settings
from ..errors import PlatformLimitNotFoundError, TtsError, VideoTooLongError
from ..ffmpeg.burn import extract_audio
from ..ffmpeg.dub import dung_dai_tieng, tron_tieng_vao_video
from ..ffmpeg.probe import do_dai_am_thanh, probe
from ..milestones import milestones, percent_of
from ..pipeline.cues import Cue, cues_from_dicts, cues_to_dicts
from ..pipeline.dedup import fingerprint, is_similar_phash
from ..pipeline.download import download_video
from ..pipeline.dubbing import lap_lich_long_tieng
from ..pipeline.masking.loc import loc_vung_can_xoa
from ..pipeline.masking.ocr import doc_video
from ..pipeline.masking.timeline import MaskRegion as MaskRegionPipeline
from ..pipeline.masking.timeline import dung_mask
from ..pipeline.masking.vaa import va_video
from ..pipeline.render import (
    VariantPlan,
    ban_cu_con_dung,
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
from ..tts import lay_provider
from ..tts.edge import GIONG_MAC_DINH
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


def _llm_model(video) -> str | None:
    """Model AI người dùng chọn cho riêng video này, đọc từ ``process_config``.

    ``None`` nghĩa là chưa chọn — dùng ``LLM_MODEL`` mặc định trong cấu hình.
    Đúng khuôn ``tone``/``reframe_mode``/``hook_text`` đã có.
    """
    config = video.process_config or {}
    model = config.get("llm_model")
    return str(model) if model else None


def _dung_cho_chon_ai(session, video) -> bool:
    """Dừng pipeline sau bước nhận dạng, chờ người dùng chọn AI dịch.

    Trả ``True`` nếu ĐÃ dừng (đặt trạng thái ``REVIEW``), ``False`` nếu chạy
    thẳng. Dừng ở đây chứ không sớm hơn vì tới lúc này mới biết video có bao
    nhiêu câu thoại — thông tin quyết định chọn model nào.

    ``auto_translate`` trong ``process_config`` bật thì KHÔNG dừng: lối dành
    cho chặng M7 (luồng tự động quét kênh nguồn rồi chạy một mạch), lúc đó
    không có ai ngồi bấm nút. Mặc định là DỪNG — chọn AI là đường chính, chạy
    thẳng là ngoại lệ phải khai báo.
    """
    config = video.process_config or {}
    if config.get("auto_translate"):
        return False

    video.status = VideoStatus.REVIEW.value
    video.current_step = None
    prog.status_changed(str(video.id), VideoStatus.REVIEW.value, None)
    log.info("pipeline.dung_cho_chon_ai", video_id=str(video.id))
    return True


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

    #: Chỗ pipeline DỪNG LẠI chờ người dùng chọn AI (xem ``_dung_cho_chon_ai``).
    #: Đặt ở cuối bước nhận dạng vì tới đây mới biết video có bao nhiêu câu —
    #: con số quyết định nên chọn model hạn mức cao hay model chất lượng cao.
    da_dung = _dung_cho_chon_ai(session, video)
    if not da_dung:
        #: ``auto_translate`` bật (chặng M7): nối tiếp nửa sau ngay, không chờ
        #: ai bấm. Gửi task chứ không gọi thẳng — mỗi bước vẫn phải là một task
        #: riêng để retry được từng bước và ghi ``job_runs`` đầy đủ.
        translate_video_chain.delay(vid)

    return {
        "cues": len(cues),
        "model": get_settings().whisper_model,
        "cho_chon_ai": da_dung,
    }


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
        model=_llm_model(video),
        **_khoa_llm_cho_translate(video),
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


#: Bật/tắt toàn bộ M3 bằng một cờ trong ``process_config`` (tiêu chí nghiệm thu
#: số 4 của spec). M3 là bước nặng và có rủi ro xoá nhầm, phải tắt được — tắt
#: thì pipeline chạy đúng như trước khi có M3.
_M3_MAC_DINH_BAT = True


def _dung_cho_duyet_ban_dich(session, video) -> bool:
    """Dừng sau bước lồng tiếng, chờ người dùng duyệt bản dịch và giọng đọc.

    Trả ``True`` nếu ĐÃ dừng. ``auto_duyet`` trong ``process_config`` bật thì
    chạy thẳng — lối cho luồng tự động, lúc đó không có ai ngồi nghe.
    """
    config = video.process_config or {}
    if config.get("auto_duyet"):
        tts_video_chain_sau_duyet.delay(str(video.id))
        return False

    video.status = VideoStatus.REVIEW.value
    video.current_step = None
    #: Phân biệt với chỗ dừng thứ nhất (chờ chọn AI) — giao diện phải đưa video
    #: vào đúng tab, và cả hai đều mang trạng thái REVIEW.
    video.flags = {**(video.flags or {}), "cho_duyet_ban_dich": True}
    prog.status_changed(str(video.id), VideoStatus.REVIEW.value, None)
    log.info("pipeline.dung_cho_duyet_ban_dich", video_id=str(video.id))
    return True


#: Hỏng liên tiếp quá số này thì dừng đọc. Quan sát ngày 16.08.2026: Gemini
#: TTS hết hạn mức trả 429 cho CÂU ĐẦU rồi trả tiếp cho cả 183 câu sau — mỗi
#: câu một lượt gọi mạng, chờ vài phút để nhận đúng một câu trả lời đã biết
#: từ câu thứ nhất.
SO_LAN_HONG_LIEN_TIEP_THI_DUNG = 5


def _doc_tuan_tu(provider, vi_cues, vid: str, giong: str) -> dict[int, Path]:
    """Đọc từng câu một cho các provider không có đường song song."""
    thu_muc = voice_parts_dir(vid)
    ra: dict[int, Path] = {}
    hong_lien_tiep = 0
    loi_cuoi = ""
    for i, cue in enumerate(vi_cues):
        dst = thu_muc / f"cau_{i:05d}.wav"
        try:
            provider.doc(cue.text.replace("\n", " "), dst, giong=giong)
            if dst.exists() and dst.stat().st_size > 0:
                ra[i] = dst
                hong_lien_tiep = 0
            else:
                hong_lien_tiep += 1
                loi_cuoi = "nhà cung cấp trả file rỗng"
        except Exception as exc:
            hong_lien_tiep += 1
            loi_cuoi = str(exc)[:200]
            log.warning("tts.cau_hong", chi_so=i, error=loi_cuoi[:120])

        if hong_lien_tiep >= SO_LAN_HONG_LIEN_TIEP_THI_DUNG:
            log.error("tts.dung_som", da_doc=len(ra), tong=len(vi_cues), error=loi_cuoi)
            raise TtsError(
                f"Dừng sau {hong_lien_tiep} câu hỏng liên tiếp "
                f"(đọc được {len(ra)}/{len(vi_cues)} câu). {loi_cuoi}"
            )

        if vi_cues:
            prog.progress(vid, PipelineStep.TTS.value, int((i + 1) * 90 / len(vi_cues)))
    return ra


def _bat_m3(video) -> bool:
    config = video.process_config or {}
    return bool(config.get("xoa_chu_cung", _M3_MAC_DINH_BAT))


def _khoa_llm_theo_video(video) -> tuple[str, str, str]:
    """``(khoá API, địa chỉ gốc, mã nhà cung cấp)`` cho việc dịch video này.

    Đọc từ bảng ``ai_providers`` theo bên người dùng đã chọn ở tab Chờ dịch.
    Không chọn bên nào thì rơi về cấu hình chung — giữ cho các video cũ (lưu
    trước khi có nhiều nhà cung cấp) vẫn chạy được.
    """
    from reup_core.ai_providers import DANH_MUC
    from reup_core.models import AiProvider
    from reup_core.settings_store import fernet

    ma = (video.process_config or {}).get("llm_provider_ma") or ""
    if not ma or ma not in DANH_MUC:
        return ("", "", "")

    with session_scope() as db:
        row = db.get(AiProvider, ma)
        if row is None or not row.api_key_encrypted:
            return ("", "", ma)
        try:
            khoa = fernet().decrypt(row.api_key_encrypted.encode()).decode()
        except Exception:
            #: Đổi SETTINGS_KEY mà quên nhập lại khoá — coi như chưa cấu hình
            #: và rơi về cấu hình chung, chứ không làm hỏng cả job.
            log.warning("llm.khoa_khong_giai_ma_duoc", provider=ma)
            return ("", "", ma)
        goc = (row.base_url or "").strip() or DANH_MUC[ma].base_url
    return (khoa, goc, ma)


def _khoa_llm_cho_translate(video) -> dict[str, str]:
    """Tham số khoá/địa chỉ/nhà cung cấp truyền cho ``translate_cues``."""
    khoa, goc, ma = _khoa_llm_theo_video(video)
    if not khoa:
        return {}
    #: Mọi bên trừ Anthropic đều tương thích OpenAI — xem ``get_translator``.
    return {
        "api_key": khoa,
        "base_url": goc,
        "provider": "anthropic" if ma == "anthropic" else "openai",
    }


def _cau_hinh_tts(video) -> tuple[str, str, str]:
    """``(nhà cung cấp, giọng, model)`` cho bước lồng tiếng, đọc từ preset.

    Video chưa chọn riêng thì rơi về cấu hình chung (``TTS_PROVIDER``,
        ``TTS_GIONG``, ``TTS_MODEL``) — sửa được ở trang Cấu hình, mục Lồng tiếng.

        edge-tts miễn phí và không tính lượt; Gemini và OpenRouter cho giọng hay
        hơn nhưng tính hạn mức/tiền MỖI CÂU — một video 672 câu đủ vượt trần ngày.
    """
    settings = get_settings()
    config = video.process_config or {}
    nha = str(config.get("tts_provider") or settings.tts_provider or "edge")
    if nha == "gemini":
        from ..tts.gemini import GIONG_MAC_DINH as GIONG_GEMINI_MD
        from ..tts.gemini import MODEL_MAC_DINH

        return (
            nha,
            str(config.get("giong_doc") or settings.tts_giong or GIONG_GEMINI_MD),
            str(config.get("tts_model") or settings.tts_model or MODEL_MAC_DINH),
        )
    if nha == "openrouter":
        from ..tts.openrouter import GIONG_MAC_DINH as GIONG_OR
        from ..tts.openrouter import MODEL_MAC_DINH as MODEL_OR

        return (
            nha,
            str(config.get("giong_doc") or settings.tts_giong or GIONG_OR),
            str(config.get("tts_model") or settings.tts_model or MODEL_OR),
        )
    return (nha, str(config.get("giong_doc") or settings.tts_giong or GIONG_MAC_DINH), "")


def _khoa_tts(nha: str) -> str:
    """Khoá API cho nhà cung cấp giọng đọc.

    KHÔNG dùng chung ``LLM_API_KEY`` cho mọi bên: khoá Gemini không gọi được
    OpenRouter, mà lỗi thì hiện ra dưới dạng "HTTP 401" giữa chừng video.
    edge-tts không cần khoá nào.
    """
    if nha == "edge":
        return ""
    if nha == "openrouter":
        from reup_core.models import AiProvider
        from reup_core.settings_store import fernet

        with session_scope() as db:
            row = db.get(AiProvider, "openrouter")
            if row is None or not row.api_key_encrypted:
                return ""
            try:
                return fernet().decrypt(row.api_key_encrypted.encode()).decode()
            except Exception as exc:  # noqa: BLE001 - đổi SETTINGS_KEY là hỏng giải mã
                log.warning("tts.khoa_khong_giai_ma_duoc", nha=nha, error=str(exc)[:120])
                return ""
    return get_settings().llm_api_key


def _bat_long_tieng(video) -> bool:
    """Lồng tiếng bật/tắt được như M3 — bước nặng thì phải tắt được."""
    config = video.process_config or {}
    return bool(config.get("long_tieng", True))


def _nguon_de_render(video) -> Path:
    """Bản đã xoá chữ cứng nếu có, ngược lại bản gốc.

    Rơi về bản gốc chứ KHÔNG báo lỗi khi thiếu file sạch: video không có chữ
    cứng nào là chuyện bình thường, và M3 tắt được bằng cờ.
    """
    sach = cleaned_video(str(video.id))
    if sach.exists() and sach.stat().st_size > 0:
        return sach
    return Path(video.raw_path)


@app.task(name="reup.detect_masks")
@pipeline_step(PipelineStep.DETECT)
def detect_masks_task(session, video) -> dict:
    """Dò vùng chữ cứng và watermark, ghi vào bảng ``mask_regions`` (M3).

    Tách khỏi bước vá vì hai lý do: dò tốn 0,11 giây mỗi khung còn lọc thì tức
    thì, nên chỉnh ngưỡng lọc không phải dò lại; và người dùng phải xem/sửa
    được mask trước khi máy xoá thật.

    Chỉ xoá lại các dòng ``source="auto"`` — bản chỉnh tay của người dùng phải
    sống sót qua mọi lần dò lại.
    """
    vid = str(video.id)
    if not _bat_m3(video):
        return {"skipped": "M3 tắt trong preset"}

    boxes = doc_video(Path(video.raw_path))
    prog.progress(vid, PipelineStep.DETECT.value, 80)
    masks = dung_mask(loc_vung_can_xoa(boxes))

    session.execute(
        sa_delete(MaskRegion).where(MaskRegion.video_id == video.id, MaskRegion.source == "auto")
    )
    for m in masks:
        session.add(
            MaskRegion(
                video_id=video.id,
                x=m.x,
                y=m.y,
                w=m.w,
                h=m.h,
                start_sec=m.bat_dau,
                end_sec=m.ket_thuc,
                source="auto",
                confidence=m.diem,
                reason=" · ".join(m.ly_do),
            )
        )

    return {"vung_chu": len(boxes), "mask": len(masks)}


@app.task(name="reup.inpaint_video")
@pipeline_step(PipelineStep.INPAINT)
def inpaint_video_task(session, video) -> dict:
    """Xoá chữ khỏi khung hình, ghi ra ``work/<id>/cleaned.mp4`` (M3).

    Các bước render phía sau đọc file này thay cho bản gốc. Không có mask nào
    thì KHÔNG sinh file — ``_nguon_de_render`` sẽ tự rơi về bản gốc.
    """
    vid = str(video.id)
    if not _bat_m3(video):
        return {"skipped": "M3 tắt trong preset"}

    rows = list(
        session.scalars(
            select(MaskRegion).where(MaskRegion.video_id == video.id).order_by(MaskRegion.start_sec)
        )
    )
    if not rows:
        return {"mask": 0, "skipped": "không có vùng nào cần xoá"}

    masks = [
        MaskRegionPipeline(
            x=r.x,
            y=r.y,
            w=r.w,
            h=r.h,
            bat_dau=r.start_sec,
            ket_thuc=r.end_sec,
            diem=r.confidence,
            ly_do=tuple((r.reason or "").split(" · ")),
        )
        for r in rows
    ]

    src = Path(video.raw_path)
    dst = cleaned_video(vid)
    if ban_cu_con_dung(dst, src):
        log.info("inpaint.skip_existing", path=str(dst))
        return {"mask": len(masks), "skipped": "bản sạch đã có và mới hơn nguồn"}

    va_video(
        src, dst, masks, progress_cb=lambda p: prog.progress(vid, PipelineStep.INPAINT.value, p)
    )
    return {"mask": len(masks), "out": str(dst), "size": dst.stat().st_size}


@app.task(name="reup.tts_video")
@pipeline_step(PipelineStep.TTS)
def tts_video_task(session, video) -> dict:
    """Sinh giọng đọc tiếng Việt và dựng dải tiếng khớp thời gian (M8).

    Chỉ tạo ``work/<id>/loitieng.wav``, KHÔNG đụng vào video. Bước render sau
    đó trộn dải tiếng này vào bản dựng cuối — giữ cho render là nơi duy nhất
    sinh ra file đầu ra, nhờ vậy chạy lại vẫn ra đúng một kết quả (luật số 4).
    Trộn ngay tại đây sẽ chồng giọng lên bản đã lồng tiếng ở lần chạy thứ hai.
    """
    vid = str(video.id)
    if not _bat_long_tieng(video):
        return {"skipped": "lồng tiếng tắt trong preset"}

    vi_cues = _load_subtitle(session, video, "vi")
    if not vi_cues:
        return {"cues": 0, "skipped": "không có phụ đề tiếng Việt để đọc"}

    nha, giong, model = _cau_hinh_tts(video)
    provider = lay_provider(nha, api_key=_khoa_tts(nha), model=model)

    #: Gemini TTS chưa có đường đọc nhiều câu song song (mỗi câu một lượt hạn
    #: mức, dội song song là cách nhanh nhất để ăn 429), nên đi đường tuần tự.
    if not hasattr(provider, "doc_nhieu"):
        files = _doc_tuan_tu(provider, vi_cues, vid, giong)
    else:
        files = provider.doc_nhieu(
            [c.text.replace("\n", " ") for c in vi_cues],
            voice_parts_dir(vid),
            giong=giong,
            progress_cb=lambda p: prog.progress(vid, PipelineStep.TTS.value, int(p * 0.9)),
        )

    #: Không đọc được câu nào thì DỪNG, đừng dựng một dải tiếng toàn số 0.
    #: Video vẫn ra bình thường, chỉ là câm phần lồng tiếng — người dùng chỉ
    #: phát hiện khi mở lên nghe, sau khi đã tốn cả bước xoá chữ cứng.
    if not files:
        raise TtsError(
            f"Không đọc được câu nào trong {len(vi_cues)} câu. "
            "Kiểm tra hạn mức của nhà cung cấp giọng đọc, hoặc đổi sang edge-tts (miễn phí)."
        )

    #: Đo độ dài THẬT của từng file thay vì ước theo số chữ: tốc độ đọc của
    #: edge-tts đổi theo dấu câu và chữ số, ước sai thì cả lịch phát lệch theo.
    do_dai = [do_dai_am_thanh(files[i]) if i in files else 0.0 for i in range(len(vi_cues))]
    lich = lap_lich_long_tieng(vi_cues, do_dai)

    tong_giay = video.duration_sec or (max(c.end for c in vi_cues) + 2.0)
    dung_dai_tieng(lich, files, tong_giay, voice_track(vid))
    prog.progress(vid, PipelineStep.TTS.value, 100)

    ep_nhanh = sum(1 for d in lich if d.he_so_toc_do > 1.01)

    #: Chỗ pipeline DỪNG LẠI lần hai: người dùng đọc lại bản dịch và nghe thử
    #: giọng trước khi ghép vào video. Đặt SAU bước lồng tiếng vì tới đây mới có
    #: giọng để nghe, và TRƯỚC các bước nặng (xoá chữ cứng) vì không ưng thì
    #: không nên đốt hàng chục phút máy vào bản sẽ bỏ đi.
    _dung_cho_duyet_ban_dich(session, video)

    return {
        "cues": len(vi_cues),
        "giong_sinh_duoc": len(files),
        "doan": len(lich),
        "phai_ep_nhanh": ep_nhanh,
        "giong": giong,
    }


@app.task(name="reup.render_video")
@pipeline_step(PipelineStep.RENDER)
def render_video_task(session, video) -> dict:
    vid = str(video.id)
    #: Bản đã xoá chữ cứng nếu bước INPAINT đã chạy — không thì bản gốc.
    source = _nguon_de_render(video)
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
        reframe_mode=_reframe_mode(video),
    )
    out = _tron_long_tieng_neu_co(vid, out)
    video.out_path = str(out)
    video.status = VideoStatus.READY
    video.current_step = None
    prog.status_changed(vid, VideoStatus.READY.value, None)
    return {
        "subtitles": len(vi_cues),
        "out_size": out.stat().st_size,
        "srt": str(subtitle_path(vid, "vi")),
    }


def _tron_long_tieng_neu_co(vid: str, out: Path) -> Path:
    """Trộn dải tiếng Việt vào bản vừa dựng, nếu bước TTS đã tạo ra nó.

    Không có dải tiếng thì trả về nguyên bản vừa dựng — lồng tiếng tắt được, và
    video không có lời thoại thì cũng không có gì để đọc.
    """
    tieng = voice_track(vid)
    if not tieng.exists() or tieng.stat().st_size == 0:
        return out
    return tron_tieng_vao_video(out, tieng, out)


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
    PipelineStep.DETECT: detect_masks_task,
    PipelineStep.INPAINT: inpaint_video_task,
    PipelineStep.TTS: tts_video_task,
    PipelineStep.RENDER: render_video_task,
}


def _build_chain(video_id: str, steps):
    #: ``si`` = immutable signature: mỗi task tự đọc trạng thái từ DB, không
    #: truyền kết quả qua lại — nhờ vậy retry một bước không cần chạy lại bước trước.
    return chain(*[_STEP_TASKS[s].si(str(video_id)) for s in steps])


@app.task(name="reup.process_video")
def process_video(video_id: str) -> str:
    """Chạy NỬA ĐẦU pipeline M1: tải, probe, nhận dạng — rồi dừng.

    Dừng lại để người dùng chọn model AI trước khi dịch (chốt 2026-08-14).
    Nửa sau chạy khi bấm nút Dịch, qua ``translate_video_chain``. Bật cờ
    ``auto_translate`` trong ``process_config`` thì bước nhận dạng tự nối tiếp
    nửa sau — xem ``_dung_cho_chon_ai``.
    """
    log.info("pipeline.start", video_id=video_id)
    _build_chain(video_id, M1_STEPS_TRUOC_DICH).apply_async()
    return video_id


@app.task(name="reup.tts_video_chain_sau_duyet")
def tts_video_chain_sau_duyet(video_id: str) -> str:
    """Chạy CHẶNG 3: xoá chữ cứng rồi render, sau khi người dùng đã duyệt.

    Tách riêng khỏi chặng 2 vì đây là phần NẶNG nhất — dò rồi xoá chữ trên video
    một tiếng mất hàng tiếng. Chỉ chạy khi người dùng đã đọc bản dịch và nghe
    thử giọng, để không đốt ngần ấy thời gian máy vào bản sẽ bỏ đi.
    """
    log.info("pipeline.sau_duyet_start", video_id=video_id)
    _build_chain(video_id, M1_STEPS_SAU_DUYET).apply_async()
    return video_id


@app.task(name="reup.translate_video_chain")
def translate_video_chain(video_id: str) -> str:
    """Chạy NỬA SAU: dịch, chuẩn hoá phụ đề, render.

    Gọi khi người dùng đã chọn model AI và bấm Dịch. Model đã được API ghi vào
    ``process_config["llm_model"]`` TRƯỚC khi gửi task này, nên ở đây không cần
    truyền thêm tham số — mỗi bước tự đọc trạng thái từ DB, đúng nguyên tắc
    ``si()`` của chuỗi task.
    """
    log.info("pipeline.translate_start", video_id=video_id)
    _build_chain(video_id, M1_STEPS_SAU_DICH).apply_async()
    return video_id


def _cac_buoc_retry(step, *, tu_dong_dich: bool) -> tuple[PipelineStep, ...]:
    """Danh sách bước cho lần "xử lý lại", TÔN TRỌNG chỗ dừng chờ chọn AI.

    Phát hiện khi thử tay: sau khi tách chain, hàm này vẫn dựng nguyên sáu bước
    cũ. Bước nhận dạng vẫn đặt trạng thái ``review``, nhưng chain đã xếp sẵn các
    task phía sau nên chúng cứ chạy — video đi thẳng tới ``ready`` và không bao
    giờ xuất hiện ở tab "Chờ dịch". Đặt trạng thái KHÔNG dừng được chain
    (``pipeline_step`` chỉ bỏ qua khi video ở ``SKIPPED``); muốn dừng thì phải
    không xếp task vào chain ngay từ đầu.

    Chạy lại từ một bước nằm ở nửa SAU (dịch/chuẩn hoá/render) thì chạy nốt nửa
    sau — người dùng đã chọn AI rồi, bắt họ quay lại tab chờ là vô lý.
    """
    if tu_dong_dich:
        #: M7 (luồng tự động): giữ nguyên hành vi chạy một mạch.
        nguon = M1_STEPS
    else:
        nguon = M1_STEPS_TRUOC_DICH

    if not step:
        return nguon

    buoc = step if isinstance(step, PipelineStep) else None
    if buoc is None:
        try:
            buoc = PipelineStep(step)
        except (ValueError, KeyError):
            #: Tên bước lạ không được làm hỏng job — chạy lại từ đầu như cũ.
            return nguon

    #: Chạy lại từ một bước ở CHẶNG 3 (xoá chữ, render) thì chỉ chạy chặng 3 —
    #: người dùng đã duyệt bản dịch rồi, dựng lại giọng là vô ích và tốn hạn mức.
    if buoc in M1_STEPS_SAU_DUYET:
        return M1_STEPS_SAU_DUYET[M1_STEPS_SAU_DUYET.index(buoc) :]
    if buoc in M1_STEPS_SAU_DICH:
        return M1_STEPS_SAU_DICH[M1_STEPS_SAU_DICH.index(buoc) :]
    if buoc in nguon:
        return nguon[nguon.index(buoc) :]
    return nguon


@app.task(name="reup.retry_from_step")
def retry_from_step(video_id: str, step: str | None = None) -> str:
    """Chạy lại từ một bước cụ thể (mặc định: từ đầu)."""
    steps = _cac_buoc_retry(step, tu_dong_dich=False)
    log.info("pipeline.retry", video_id=video_id, from_step=steps[0].value)
    _build_chain(video_id, steps).apply_async()
    return video_id
