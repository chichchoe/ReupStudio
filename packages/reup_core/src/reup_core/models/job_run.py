from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, uuid_pk


class JobRun(Base):
    """Nhật ký từng bước pipeline.

    Bảng quan trọng nhất khi debug: cho biết bước nào chạy bao lâu, lỗi gì,
    dùng model nào. Đừng bỏ.
    """

    __tablename__ = "job_runs"
    __table_args__ = (sa.Index("ix_job_runs_video_step", "video_id", "step"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    step: Mapped[str] = mapped_column(
        sa.String(32), nullable=False
    )
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)  # running|success|failed
    celery_task_id: Mapped[str | None] = mapped_column(sa.String(64))
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    duration_sec: Mapped[float | None] = mapped_column(sa.Float)
    log: Mapped[str | None] = mapped_column(sa.Text)
    meta: Mapped[dict[str, Any]] = mapped_column(sa.JSON, default=dict)

    video = relationship("Video", back_populates="job_runs")
