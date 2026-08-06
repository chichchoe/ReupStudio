from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..enums import VideoStatus
from .base import Base, TimestampMixin, uuid_pk


class Video(Base, TimestampMixin):
    __tablename__ = "videos"
    __table_args__ = (
        sa.UniqueConstraint(
            "source_platform", "source_video_id", name="uq_video_source"
        ),
        sa.Index("ix_videos_status", "status"),
        sa.Index("ix_videos_md5", "md5"),
        sa.Index("ix_videos_phash", "phash"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()

    # --- nguồn ---
    source_platform: Mapped[str] = mapped_column(
        sa.String(32), nullable=False
    )
    source_video_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    source_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_author: Mapped[str | None] = mapped_column(sa.String(255))

    # --- nội dung ---
    title_original: Mapped[str | None] = mapped_column(sa.Text)
    desc_original: Mapped[str | None] = mapped_column(sa.Text)
    title_vi: Mapped[str | None] = mapped_column(sa.Text)
    desc_vi: Mapped[str | None] = mapped_column(sa.Text)
    hashtags_vi: Mapped[list[str] | None] = mapped_column(sa.JSON)

    # --- thông số kỹ thuật (điền ở bước probe) ---
    duration_sec: Mapped[float | None] = mapped_column(sa.Float)
    width: Mapped[int | None] = mapped_column(sa.Integer)
    height: Mapped[int | None] = mapped_column(sa.Integer)
    fps: Mapped[float | None] = mapped_column(sa.Float)
    has_audio: Mapped[bool | None] = mapped_column(sa.Boolean)
    view_count_source: Mapped[int | None] = mapped_column(sa.BigInteger)

    # --- chống trùng ---
    md5: Mapped[str | None] = mapped_column(sa.String(32))
    phash: Mapped[str | None] = mapped_column(sa.String(64))

    # --- trạng thái ---
    status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, default=VideoStatus.QUEUED.value,
    )
    current_step: Mapped[str | None] = mapped_column(
        sa.String(32))
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    flags: Mapped[dict[str, Any]] = mapped_column(sa.JSON, default=dict)

    # --- đường dẫn ---
    raw_path: Mapped[str | None] = mapped_column(sa.Text)
    out_path: Mapped[str | None] = mapped_column(sa.Text)

    # --- cấu hình xử lý (preset snapshot) ---
    process_config: Mapped[dict[str, Any]] = mapped_column(sa.JSON, default=dict)

    deleted_at: Mapped[Any | None] = mapped_column(sa.DateTime(timezone=True))

    subtitles = relationship(
        "Subtitle", back_populates="video", cascade="all, delete-orphan"
    )
    job_runs = relationship(
        "JobRun", back_populates="video", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Video {self.id} {self.status} {self.title_original!r}>"
