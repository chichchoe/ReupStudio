"""Logic nghiệp vụ cho video. KHÔNG biết gì về HTTP/FastAPI."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from reup_core.enums import PresetKind, VideoStatus
from reup_core.llm_models import chac_chan_khong_dich_duoc
from reup_core.logging import get_logger
from reup_core.models import JobRun, Subtitle, Video
from reup_core.source_url import parse_source_url
from sqlalchemy.orm import Session

from ..errors import ApiError, NotFound
from . import preset_service, task_bridge

log = get_logger(__name__)


def list_videos(
    db: Session,
    *,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[Video], int]:
    stmt = sa.select(Video).where(Video.deleted_at.is_(None))
    if status and status != "all":
        stmt = stmt.where(Video.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            sa.or_(
                Video.title_original.ilike(like),
                Video.title_vi.ilike(like),
                Video.source_author.ilike(like),
            )
        )

    total = db.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Video.created_at.desc()).offset((page - 1) * limit).limit(limit)
    ).all()
    return list(rows), total


def get_video(db: Session, video_id: uuid.UUID) -> Video:
    video = db.get(Video, video_id)
    if video is None or video.deleted_at is not None:
        raise NotFound(f"Không tìm thấy video {video_id}")
    return video


def create_from_links(
    db: Session,
    urls: list[str],
    process_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tạo bản ghi video từ danh sách link.

    Idempotent: link đã có trong DB thì TRẢ LẠI id của bản ghi cũ trong
    ``duplicate_ids``, không tạo mới. Đây là lớp chống trùng thứ nhất (theo
    ``source_video_id``); lớp md5/pHash chạy sau khi tải xong ở worker.
    """
    created: list[Video] = []
    duplicates: list[Video] = []
    invalid: list[str] = []

    for raw_url in urls:
        parsed = parse_source_url(raw_url)
        if parsed is None:
            invalid.append(raw_url)
            continue

        existing = db.scalar(
            sa.select(Video).where(
                Video.source_platform == parsed.platform.value,
                Video.source_video_id == parsed.video_id,
            )
        )
        if existing is not None and existing.deleted_at is None:
            duplicates.append(existing)
            continue

        if existing is not None:
            #: Dòng đã xoá mềm — HỒI SINH chứ không tạo dòng thứ hai: ràng buộc
            #: UNIQUE(source_platform, source_video_id) không cho hai dòng cùng
            #: một video, và giữ dòng cũ thì lịch sử ``job_runs`` còn nguyên.
            #: Không có nhánh này thì video đã xoá chặn vĩnh viễn việc dán lại
            #: chính link đó — người dùng kẹt, không còn đường nào thêm lại.
            existing.deleted_at = None
            existing.status = VideoStatus.QUEUED
            existing.current_step = None
            #: Xoá dấu vết lần hỏng trước, nếu không người dùng dán lại xong
            #: vẫn thấy lỗi cũ và tưởng chưa sửa được gì.
            existing.error_message = None
            existing.source_url = parsed.url
            existing.process_config = process_config or {}
            existing.flags = {
                **(existing.flags or {}),
                "provisional_id": parsed.provisional,
            }
            created.append(existing)
            continue

        video = Video(
            source_platform=parsed.platform.value,
            source_video_id=parsed.video_id,
            source_url=parsed.url,
            status=VideoStatus.QUEUED,
            flags={"provisional_id": parsed.provisional},
            process_config=process_config or {},
        )
        db.add(video)
        created.append(video)

    db.flush()
    return {
        "created": len(created),
        "skipped_duplicate": len(duplicates),
        "invalid": invalid,
        "video_ids": [v.id for v in created],
        "duplicate_ids": [v.id for v in duplicates],
    }


def approve(db: Session, video_id: uuid.UUID) -> Video:
    video = get_video(db, video_id)
    if video.status == VideoStatus.REVIEW:
        video.status = VideoStatus.READY
        video.flags = {**video.flags, "approved": True}
    return video


#: Trạng thái mà "xử lý lại" phải reset trước khi dispatch, nếu không chuỗi
#: task Celery sẽ tự bỏ qua toàn bộ (xem worker/tasks/base.py — video ở
#: SKIPPED short-circuit mọi bước; ERROR thì error_message/flags cũ còn sót).
_TRANG_THAI_CAN_RESET_KHI_RETRY = (VideoStatus.SKIPPED, VideoStatus.ERROR)


def _reset_video_de_retry(video: Video) -> None:
    """Đưa video treo (SKIPPED/ERROR) về QUEUED để "xử lý lại" không còn là
    no-op im lặng. Gỡ luôn cờ trùng lặp (``duplicate_of``/``duplicate_reason``)
    vì video sắp được xử lý lại từ đầu, không còn "trùng" theo nghĩa cũ.

    Video ở trạng thái khác (queued/running/review/ready/posted) thì không
    làm gì — "xử lý lại" một video đang bình thường vẫn dispatch như cũ, chỉ
    không cần reset.

    KHÔNG gửi task Celery và KHÔNG commit — caller PHẢI commit trước khi gọi
    ``task_bridge``, nếu không worker chạy gần như ngay lập tức có thể đọc
    phải trạng thái cũ trong DB.
    """
    if video.status not in _TRANG_THAI_CAN_RESET_KHI_RETRY:
        return
    video.status = VideoStatus.QUEUED
    video.error_message = None
    video.flags = {
        k: v for k, v in video.flags.items() if k not in ("duplicate_of", "duplicate_reason")
    }


def prepare_retry(db: Session, video_id: uuid.UUID) -> Video:
    """Chuẩn bị một video để xử lý lại: reset trạng thái nếu đang SKIPPED/ERROR.

    Router phải ``db.commit()`` NGAY SAU khi gọi hàm này, rồi mới gọi
    ``task_bridge.retry_from`` — bắt chước thứ tự commit-trước-dispatch của
    ``create_from_links``.
    """
    video = get_video(db, video_id)
    _reset_video_de_retry(video)
    return video


def _chan_dich_trung(video: Video) -> None:
    """Chỉ cho bấm Dịch khi video ĐANG đứng ở chỗ dừng thứ nhất.

    Trước đây hàm này nhận mọi lời gọi. Bấm Dịch hai lần — hoặc bấm lại vì lần
    đầu tưởng không ăn — là gửi đi hai chuỗi task đầy đủ: đốt hai lần hạn mức
    LLM, rồi hai chuỗi giẫm lên nhau. Quan sát ngày 16.08.2026: bốn chuỗi cùng
    chạy, chuỗi tới sau kéo video đã duyệt xong QUAY NGƯỢC về ``review``, nên
    người dùng thấy "dịch xong lại về chờ dịch".

    Video ``error`` vẫn cho chạy lại — đó chính là nút Thử lại.
    """
    if video.status == VideoStatus.ERROR.value:
        return
    if video.status in (VideoStatus.READY.value, VideoStatus.POSTED.value):
        raise ApiError("Video này đã dựng xong rồi. Muốn làm lại thì bấm Thử lại.")
    if video.status != VideoStatus.REVIEW.value:
        raise ApiError("Video đang xử lý, không bấm Dịch lại được. Đợi bước hiện tại xong đã.")
    if (video.flags or {}).get("cho_duyet_ban_dich"):
        raise ApiError("Video này đã dịch xong rồi — sang tab Chờ duyệt để đọc lại bản dịch.")


def request_translate(db: Session, video_id: uuid.UUID, llm_model: str | None) -> Video:
    """Ghi model đã chọn rồi đưa video trở lại hàng đợi để chạy nửa sau pipeline.

    Pipeline dừng ở trạng thái ``review`` sau bước nhận dạng; đây là chỗ khởi
    động lại. Model ghi vào ``process_config["llm_model"]`` TRƯỚC khi gửi task,
    vì chuỗi task Celery dùng ``si()`` — mỗi bước tự đọc trạng thái từ DB chứ
    không nhận tham số truyền tay.

    Đưa về ``QUEUED`` ngay: còn ở ``review`` thì giao diện vẫn hiện video trong
    tab "Chờ dịch" dù người dùng đã bấm, trông như nút không ăn.

    Router PHẢI ``db.commit()`` trước khi gọi ``task_bridge`` — worker chạy gần
    như tức thì, chậm một nhịp là nó đọc phải ``process_config`` cũ.
    """
    video = get_video(db, video_id)
    _chan_dich_trung(video)

    if llm_model:
        #: Chỉ chặn thứ CHẮC CHẮN sai, không chặn thứ chỉ vì tên lạ. Danh sách
        #: model hiện ra dựng từ khai báo khả năng của nhà cung cấp, còn chỗ
        #: này chỉ biết cái tên — chặt hơn ở đây là từ chối đúng thứ vừa mời
        #: người dùng chọn.
        if chac_chan_khong_dich_duoc(llm_model):
            raise ApiError(
                f"Model '{llm_model}' không dùng để dịch được — nó là model đọc "
                "thành tiếng hoặc sinh ảnh/video. Chọn model trong danh sách "
                "'translate' ở ô chọn AI."
            )
        video.process_config = {**(video.process_config or {}), "llm_model": llm_model}

    video.status = VideoStatus.QUEUED
    video.error_message = None
    return video


def soft_delete(db: Session, video_id: uuid.UUID) -> None:
    video = get_video(db, video_id)
    video.deleted_at = sa.func.now()


def get_subtitles(db: Session, video_id: uuid.UUID, lang: str | None = None) -> list[Subtitle]:
    stmt = sa.select(Subtitle).where(Subtitle.video_id == video_id)
    if lang:
        stmt = stmt.where(Subtitle.lang == lang)
    return list(db.scalars(stmt).all())


def get_job_runs(db: Session, video_id: uuid.UUID) -> list[JobRun]:
    return list(
        db.scalars(
            sa.select(JobRun).where(JobRun.video_id == video_id).order_by(JobRun.started_at.asc())
        ).all()
    )


def counts_by_status(db: Session) -> dict[str, int]:
    rows = db.execute(
        sa.select(Video.status, sa.func.count())
        .where(Video.deleted_at.is_(None))
        .group_by(Video.status)
    ).all()
    result = {s.value: 0 for s in VideoStatus}
    for status, count in rows:
        result[str(status)] = count
    result["all"] = sum(result[s.value] for s in VideoStatus)
    return result


def _preset_id_tu_payload(payload: dict[str, Any]) -> uuid.UUID:
    """Đọc và kiểm tra ``payload["preset_id"]`` cho action ``apply_preset``."""
    raw = payload.get("preset_id")
    if not raw:
        raise ApiError("Thiếu preset_id trong payload")
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ApiError(f"preset_id không hợp lệ: {raw!r}") from exc


def _channel_ids_tu_payload(payload: dict[str, Any]) -> list[str]:
    """Đọc và kiểm tra ``payload["channel_ids"]`` cho action ``assign_channels``."""
    raw = payload.get("channel_ids")
    if not isinstance(raw, list) or not raw:
        raise ApiError("Thiếu channel_ids (danh sách) trong payload")
    try:
        return [str(uuid.UUID(str(item))) for item in raw]
    except (ValueError, TypeError, AttributeError) as exc:
        raise ApiError(f"channel_ids chứa id không hợp lệ: {raw!r}") from exc


def bulk_action(
    db: Session,
    ids: list[uuid.UUID],
    action: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Áp một hành động cho nhiều video cùng lúc.

    Hỗ trợ 5 action: ``approve``, ``delete``, ``retry``, ``apply_preset``,
    ``assign_channels``. Video không áp được (không tìm thấy, đã xoá mềm, sai
    trạng thái) rơi vào ``skipped`` kèm lý do — không bao giờ bị bỏ qua âm thầm.
    Video đã xoá mềm (``deleted_at IS NOT NULL``) không bao giờ bị tác động.

    ``assign_channels``: bảng ``publish_channels`` thuộc chặng M5, CHƯA CÓ ở
    M2. Ở đây chỉ lưu danh sách id vào ``video.process_config["target_channel_ids"]``
    dưới dạng chuỗi thô, KHÔNG có khoá ngoại. M5 sẽ thay bằng khoá ngoại thật
    trỏ tới bảng ``publish_channels``.
    """
    payload = payload or {}
    skipped: list[dict[str, str]] = []
    affected = 0

    preset = None
    if action == "apply_preset":
        preset = preset_service.get_preset(db, _preset_id_tu_payload(payload))
        if preset.kind != PresetKind.PROCESS:
            raise ApiError(
                f"Preset '{preset.name}' có kind='{preset.kind}', "
                f"apply_preset chỉ chấp nhận kind='{PresetKind.PROCESS.value}'"
            )

    channel_ids: list[str] = []
    if action == "assign_channels":
        channel_ids = _channel_ids_tu_payload(payload)

    # Một truy vấn duy nhất thay vì db.get() từng id trong vòng lặp — với
    # max_length=500 của BulkAction.ids, N round-trip riêng lẻ giữ một
    # connection của pool (pool_size=5) suốt thời gian xử lý, vi phạm luật
    # "endpoint không bao giờ chờ việc chạy lâu".
    tim_thay = db.scalars(sa.select(Video).where(Video.id.in_(ids))).all()
    theo_id = {v.id: v for v in tim_thay}

    #: id cần dispatch task Celery SAU KHI đã commit — không dispatch ngay
    #: trong vòng lặp vì trạng thái reset (SKIPPED/ERROR -> QUEUED) chưa chắc
    #: đã ghi xuống DB, worker chạy gần như ngay lập tức có thể đọc phải
    #: trạng thái cũ và tự bỏ qua (xem worker/tasks/base.py).
    can_dispatch: list[uuid.UUID] = []

    for video_id in ids:
        video = theo_id.get(video_id)
        if video is None:
            skipped.append({"id": str(video_id), "reason": "Không tìm thấy video"})
            continue
        if video.deleted_at is not None:
            skipped.append({"id": str(video_id), "reason": "Video đã bị xoá mềm"})
            continue

        if action == "approve":
            if video.status != VideoStatus.REVIEW:
                skipped.append(
                    {
                        "id": str(video_id),
                        "reason": f"Sai trạng thái để duyệt: đang ở '{video.status}'",
                    }
                )
                continue
            video.status = VideoStatus.READY
            video.flags = {**video.flags, "approved": True}
        elif action == "delete":
            video.deleted_at = sa.func.now()
        elif action == "retry":
            _reset_video_de_retry(video)
            can_dispatch.append(video_id)
        elif action == "apply_preset":
            assert preset is not None  # đã được lấy trước vòng lặp
            video.process_config = {**video.process_config, **preset.config}
        elif action == "assign_channels":
            video.process_config = {
                **video.process_config,
                "target_channel_ids": channel_ids,
            }
        affected += 1

    if can_dispatch:
        db.commit()
        for video_id in can_dispatch:
            task_bridge.retry_from(video_id, None)

    log.info(
        "video.bulk_action",
        action=action,
        affected=affected,
        skipped=len(skipped),
        total=len(ids),
    )
    return {"affected": affected, "action": action, "skipped": skipped}


def luu_tuy_chon_xu_ly(
    db: Session,
    video_id: uuid.UUID,
    *,
    xoa_chu_cung: bool,
    tts_provider: str,
    llm_provider: str | None = None,
    giong_doc: str | None,
    tts_model: str | None,
) -> Video:
    """Ghi các lựa chọn xử lý của RIÊNG video này vào ``process_config``.

    Gọi ngay sau ``request_translate`` và TRƯỚC khi router commit — worker chạy
    gần như tức thì, chậm một nhịp là nó đọc phải cấu hình cũ.

    Ghi cả khi giá trị trùng mặc định: người dùng bỏ tích "xoá chữ cứng" phải
    có tác dụng, mà mặc định lại là bật, nên không thể chỉ ghi khi khác mặc
    định.
    """
    video = get_video(db, video_id)
    config = dict(video.process_config or {})

    if llm_provider:
        config["llm_provider_ma"] = llm_provider
    config["xoa_chu_cung"] = bool(xoa_chu_cung)
    config["tts_provider"] = tts_provider
    if giong_doc:
        config["giong_doc"] = giong_doc
    if tts_model:
        config["tts_model"] = tts_model

    video.process_config = config
    db.flush()
    return video


def duyet_ban_dich(db: Session, video_id: uuid.UUID) -> Video:
    """Người dùng đã đọc bản dịch và nghe thử giọng — cho chạy tiếp chặng cuối.

    Xoá cờ ``cho_duyet_ban_dich`` và đưa về ``QUEUED`` ngay: còn cờ thì giao
    diện vẫn hiện video ở tab chờ duyệt dù đã bấm, trông như nút không ăn.
    """
    video = get_video(db, video_id)
    #: Chỉ duyệt được thứ ĐANG chờ duyệt. Bấm hai lần là chạy hai lần bước xoá
    #: chữ cứng — bước nặng nhất pipeline, video một tiếng mất hàng tiếng.
    if not (video.flags or {}).get("cho_duyet_ban_dich"):
        raise ApiError("Video này không ở chỗ chờ duyệt bản dịch.")

    flags = dict(video.flags or {})
    flags.pop("cho_duyet_ban_dich", None)
    video.flags = flags
    video.status = VideoStatus.QUEUED.value
    video.current_step = None
    db.flush()
    return video


#: Danh sách giọng khai ở tầng API chứ không import từ worker: `apps/api` không
#: phụ thuộc `apps/worker`, và kéo `tts/gemini.py` vào đây sẽ kéo theo cả nhánh
#: phụ thuộc của worker.
_GIONG_EDGE = [
    {"ma": "vi-VN-HoaiMyNeural", "ten": "Hoài My", "gioi_tinh": "nữ"},
    {"ma": "vi-VN-NamMinhNeural", "ten": "Nam Minh", "gioi_tinh": "nam"},
]

_GIONG_GEMINI = [
    {"ma": "Kore", "ten": "Kore — chắc chắn", "gioi_tinh": "nữ"},
    {"ma": "Aoede", "ten": "Aoede — nhẹ nhàng", "gioi_tinh": "nữ"},
    {"ma": "Leda", "ten": "Leda — trẻ trung", "gioi_tinh": "nữ"},
    {"ma": "Callirrhoe", "ten": "Callirrhoe — thong thả", "gioi_tinh": "nữ"},
    {"ma": "Autonoe", "ten": "Autonoe — tươi sáng", "gioi_tinh": "nữ"},
    {"ma": "Despina", "ten": "Despina — mượt", "gioi_tinh": "nữ"},
    {"ma": "Erinome", "ten": "Erinome — rõ ràng", "gioi_tinh": "nữ"},
    {"ma": "Laomedeia", "ten": "Laomedeia — sôi nổi", "gioi_tinh": "nữ"},
    {"ma": "Achernar", "ten": "Achernar — êm", "gioi_tinh": "nữ"},
    {"ma": "Gacrux", "ten": "Gacrux — chững chạc", "gioi_tinh": "nữ"},
    {"ma": "Pulcherrima", "ten": "Pulcherrima — dẫn chuyện", "gioi_tinh": "nữ"},
    {"ma": "Vindemiatrix", "ten": "Vindemiatrix — dịu", "gioi_tinh": "nữ"},
    {"ma": "Sulafat", "ten": "Sulafat — ấm", "gioi_tinh": "nữ"},
    {"ma": "Zephyr", "ten": "Zephyr — sáng", "gioi_tinh": "nữ"},
    {"ma": "Puck", "ten": "Puck — hoạt bát", "gioi_tinh": "nam"},
    {"ma": "Charon", "ten": "Charon — trầm, kể chuyện", "gioi_tinh": "nam"},
    {"ma": "Fenrir", "ten": "Fenrir — mạnh", "gioi_tinh": "nam"},
    {"ma": "Orus", "ten": "Orus — chắc", "gioi_tinh": "nam"},
    {"ma": "Enceladus", "ten": "Enceladus — thì thầm", "gioi_tinh": "nam"},
    {"ma": "Iapetus", "ten": "Iapetus — rõ", "gioi_tinh": "nam"},
    {"ma": "Umbriel", "ten": "Umbriel — thư thái", "gioi_tinh": "nam"},
    {"ma": "Algieba", "ten": "Algieba — mượt", "gioi_tinh": "nam"},
    {"ma": "Algenib", "ten": "Algenib — khàn", "gioi_tinh": "nam"},
    {"ma": "Rasalgethi", "ten": "Rasalgethi — giàu thông tin", "gioi_tinh": "nam"},
    {"ma": "Alnilam", "ten": "Alnilam — dứt khoát", "gioi_tinh": "nam"},
    {"ma": "Schedar", "ten": "Schedar — điềm đạm", "gioi_tinh": "nam"},
    {"ma": "Achird", "ten": "Achird — thân thiện", "gioi_tinh": "nam"},
    {"ma": "Zubenelgenubi", "ten": "Zubenelgenubi — đời thường", "gioi_tinh": "nam"},
    {"ma": "Sadachbia", "ten": "Sadachbia — sống động", "gioi_tinh": "nam"},
    {"ma": "Sadaltager", "ten": "Sadaltager — hiểu biết", "gioi_tinh": "nam"},
]


#: Giọng của ``openai/gpt-audio`` — khai đúng bằng danh sách bên worker
#: (``tts/openrouter.py::GIONG_GPT_AUDIO``). Không import từ worker: `apps/api`
#: không phụ thuộc `apps/worker`, kéo sang là kéo cả nhánh phụ thuộc của nó.
_GIONG_OPENROUTER = [
    {"ma": "nova", "ten": "Nova — sáng, nhanh", "gioi_tinh": "nữ"},
    {"ma": "shimmer", "ten": "Shimmer — nhẹ, ấm", "gioi_tinh": "nữ"},
    {"ma": "alloy", "ten": "Alloy — trung tính, đều", "gioi_tinh": "trung tính"},
    {"ma": "fable", "ten": "Fable — kể chuyện", "gioi_tinh": "trung tính"},
    {"ma": "echo", "ten": "Echo — trầm, chắc", "gioi_tinh": "nam"},
    {"ma": "onyx", "ten": "Onyx — trầm, dày", "gioi_tinh": "nam"},
]


def cac_giong_doc(db: Session | None = None) -> list[dict[str, Any]]:
    """Giọng đọc chọn được, nhóm theo nhà cung cấp, kèm đánh đổi."""
    from ..config import get_settings

    settings = get_settings()

    ra: list[dict[str, Any]] = [
        {
            "provider": "edge",
            "ghi_chu": "Miễn phí, không tính lượt. Hợp video dài.",
            "models": [],
            "giong": _GIONG_EDGE,
        }
    ]

    #: Không có khoá thì KHÔNG liệt kê Gemini: hiện ra rồi bấm vào mới báo lỗi
    #: là cách chắc chắn nhất làm người dùng tưởng hỏng.
    if settings.llm_api_key:
        ra.append(
            {
                "provider": "gemini",
                "ghi_chu": "Giọng tự nhiên hơn, NHƯNG mỗi câu tốn một lượt hạn mức.",
                "models": [
                    "gemini-2.5-flash-preview-tts",
                    "gemini-2.5-pro-preview-tts",
                    "gemini-3.1-flash-tts-preview",
                ],
                "giong": _GIONG_GEMINI,
            }
        )

    #: OpenRouter chỉ hiện khi ĐÃ dán khoá — cùng lý do với Gemini. Nó là
    #: đường lui khi Gemini hết hạn mức, nhưng tính TIỀN chứ không có bậc miễn
    #: phí, nên phải nói rõ ngay trên nhãn.
    if db is not None:
        from . import ai_provider_service

        if ai_provider_service.lay_khoa(db, "openrouter"):
            ra.append(
                {
                    "provider": "openrouter",
                    "ghi_chu": "Trả tiền theo lượt (bản mini ~0,7 xu mỗi câu), "
                    "KHÔNG có bậc miễn phí.",
                    #: Bản rẻ ĐỨNG TRƯỚC — token audio $0,60/1M so với $32/1M,
                    #: đắt gấp 53 lần. Ai bấm nhanh cũng phải rơi vào bản rẻ.
                    "models": ["openai/gpt-audio-mini", "openai/gpt-audio"],
                    "giong": _GIONG_OPENROUTER,
                }
            )

    #: Bên nào được chọn sẵn — do BACKEND quyết (``TTS_PROVIDER`` trong Cấu
    #: hình), không nhét cứng trong React. Bên mặc định mà chưa dán khoá thì
    #: không có trong danh sách này, lúc đó giao diện tự rơi về mục đầu.
    for nhom in ra:
        nhom["mac_dinh"] = nhom["provider"] == settings.tts_provider
        nhom["giong_mac_dinh"] = (
            settings.tts_giong if nhom["provider"] == settings.tts_provider else ""
        )
    return ra
