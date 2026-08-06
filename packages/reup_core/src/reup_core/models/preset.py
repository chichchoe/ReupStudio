from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk


class Preset(Base, TimestampMixin):
    """Cấu hình chỉnh được từ giao diện — đổi preset không cần sửa code.

    ``kind`` là một trong các giá trị của ``PresetKind`` (filter/process/antidup/
    subtitle). Mỗi kind chỉ nên có đúng một preset ``is_default=True`` tại một
    thời điểm — ràng buộc này do ``preset_service`` đảm bảo, không ép ở DB.
    """

    __tablename__ = "presets"
    __table_args__ = (
        sa.UniqueConstraint("kind", "name", name="uq_preset_kind_name"),
        sa.Index("ix_presets_kind", "kind"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(sa.JSON, nullable=False, default=dict)
    is_default: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Preset {self.id} {self.kind} {self.name!r}>"
