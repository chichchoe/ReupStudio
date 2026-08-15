from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk

#: Chu kỳ quét (phút) hợp lệ — không cho giá trị tuỳ ý để tránh spam nền tảng nguồn.
VALID_SCAN_INTERVAL_MIN: frozenset[int] = frozenset({15, 60, 360, 1440})


class SourceChannel(Base, TimestampMixin):
    """Kênh nguồn (Trung Quốc) được theo dõi để quét video mới tự động.

    ``license_status`` mặc định là ``unknown`` — nguồn ``unknown`` KHÔNG BAO GIỜ
    được xử lý tự động, đây là chốt an toàn pháp lý (xem
    ``services/source_channel_service.can_auto_process``). Không được nới lỏng
    ràng buộc này ở tầng model hay migration.
    """

    __tablename__ = "source_channels"
    __table_args__ = (
        sa.UniqueConstraint(
            "platform", "external_id", name="uq_source_channel_platform_external"
        ),
        sa.Index(
            "ix_source_channels_enabled_last_scanned", "enabled", "last_scanned_at"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    platform: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    handle: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    scan_interval_min: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=60
    )
    last_scanned_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_seen_video_id: Mapped[str | None] = mapped_column(
        sa.String(128), nullable=True
    )
    # Không đặt khoá ngoại cứng ở M2 — bảng preset có thể đổi trước khi liên kết chốt.
    filter_preset_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    process_preset_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    license_status: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default="unknown"
    )
    license_note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SourceChannel {self.id} {self.platform} {self.external_id!r}>"
