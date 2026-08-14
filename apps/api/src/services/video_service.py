"""Logic nghiệp vụ cho video. KHÔNG biết gì về HTTP/FastAPI."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from reup_core.enums import PresetKind, VideoStatus
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
            sa.select(JobRun)
            .where(JobRun.video_id == video_id)
            .order_by(JobRun.started_at.asc())
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
