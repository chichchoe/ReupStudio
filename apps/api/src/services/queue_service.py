"""Đếm số video theo trạng thái hàng chờ, dùng cho sự kiện WebSocket `queue`.

KHÔNG biết gì về HTTP/FastAPI hay Redis — chỉ nhận Session và trả dict.
"""

from __future__ import annotations

import sqlalchemy as sa
from reup_core.enums import VideoStatus
from reup_core.models import Video
from sqlalchemy.orm import Session


def queue_counts(db: Session) -> dict[str, int]:
    """{"active": số video status=running, "pending": số video status=queued}.

    Chỉ đếm video chưa bị xoá mềm (``deleted_at IS NULL``).
    """
    rows = db.execute(
        sa.select(Video.status, sa.func.count())
        .where(Video.deleted_at.is_(None))
        .where(Video.status.in_([VideoStatus.RUNNING, VideoStatus.QUEUED]))
        .group_by(Video.status)
    ).all()

    counts = {VideoStatus.RUNNING.value: 0, VideoStatus.QUEUED.value: 0}
    for status, count in rows:
        counts[str(status)] = count

    return {
        "active": counts[VideoStatus.RUNNING.value],
        "pending": counts[VideoStatus.QUEUED.value],
    }
