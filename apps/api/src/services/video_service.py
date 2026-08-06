"""Logic nghiệp vụ cho video. KHÔNG biết gì về HTTP/FastAPI."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from reup_core.enums import VideoStatus
from reup_core.models import JobRun, Subtitle, Video
from reup_core.source_url import parse_source_url
from sqlalchemy.orm import Session

from ..errors import NotFound


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

    Idempotent: link đã có trong DB thì trả lại bản ghi cũ, không tạo mới.
    """
    created: list[Video] = []
    skipped = 0
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
            skipped += 1
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
        "skipped_duplicate": skipped,
        "invalid": invalid,
        "video_ids": [v.id for v in created],
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
