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
        if existing is not None:
            duplicates.append(existing)
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

    for video_id in ids:
        video = db.get(Video, video_id)
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
            task_bridge.retry_from(video_id, None)
        elif action == "apply_preset":
            assert preset is not None  # đã được lấy trước vòng lặp
            video.process_config = {**video.process_config, **preset.config}
        elif action == "assign_channels":
            video.process_config = {
                **video.process_config,
                "target_channel_ids": channel_ids,
            }
        affected += 1

    log.info(
        "video.bulk_action",
        action=action,
        affected=affected,
        skipped=len(skipped),
        total=len(ids),
    )
    return {"affected": affected, "action": action, "skipped": skipped}
