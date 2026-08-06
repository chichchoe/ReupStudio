from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, uuid_pk


class Subtitle(Base, TimestampMixin):
    """Toàn bộ phụ đề của một ngôn ngữ lưu trong MỘT dòng, cột ``cues`` là JSON.

    Không tách mỗi dòng phụ đề thành một row: không bao giờ cần query từng dòng,
    mà lại phải join và sắp xếp mỗi lần đọc.
    """

    __tablename__ = "subtitles"
    __table_args__ = (
        sa.UniqueConstraint("video_id", "lang", name="uq_subtitle_video_lang"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    lang: Mapped[str] = mapped_column(sa.String(8), nullable=False)  # zh | vi
    source: Mapped[str] = mapped_column(sa.String(16), nullable=False)  # asr|ocr|llm|manual
    #: [{"i": 0, "start": 1.2, "end": 3.4, "text": "..."}]
    cues: Mapped[list[dict[str, Any]]] = mapped_column(sa.JSON, nullable=False)
    edited_by_user: Mapped[bool] = mapped_column(sa.Boolean, default=False)

    video = relationship("Video", back_populates="subtitles")
