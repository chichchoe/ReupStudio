from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk


class RenderVariant(Base, TimestampMixin):
    """Một bản render của một video cho MỘT nền tảng đích (luật số 8 CLAUDE.md).

    "Một video sinh nhiều `render_variants` (một bản mỗi nền tảng đích). Không
    thiết kế 1-1." — trước M4, hệ thống chỉ ghi một file duy nhất vào
    ``videos.out_path``; từ M4, mỗi tổ hợp (nền tảng, tập) có một dòng riêng ở
    đây. ``videos.out_path`` vẫn giữ nguyên để pipeline M1 (chưa tách theo
    nền tảng) không hỏng.

    Một video dài hơn giới hạn thời lượng của một nền tảng bị chia thành nhiều
    TẬP (``part_index``/``part_total``, xem ``pipeline/shortform/split.py``) —
    mỗi tập cũng là một dòng riêng, cùng ``target_platform``.

    ``config_snapshot`` lưu lại preset + giới hạn nền tảng (``platform_limits``)
    ĐÃ DÙNG tại thời điểm render — không phải tham chiếu tới bảng preset/limit
    hiện tại, vì hai bảng đó có thể bị người dùng chỉnh sau. Nhờ vậy có thể tái
    tạo (render lại) đúng bản này về sau kể cả khi preset/limit gốc đã đổi.
    """

    __tablename__ = "render_variants"
    __table_args__ = (
        sa.UniqueConstraint(
            "video_id", "target_platform", "part_index", name="uq_render_variant"
        ),
        sa.Index("ix_render_variants_video_id", "video_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    target_platform: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    #: 1-based. Mặc định 1 cho video không bị chia tập.
    part_index: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    #: Tổng số tập của CÙNG nền tảng đích này (không phải tổng toàn bộ variant).
    part_total: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    out_path: Mapped[str | None] = mapped_column(sa.Text)
    duration_sec: Mapped[float | None] = mapped_column(sa.Float)
    width: Mapped[int | None] = mapped_column(sa.Integer)
    height: Mapped[int | None] = mapped_column(sa.Integer)
    file_size: Mapped[int | None] = mapped_column(sa.BigInteger)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(sa.JSON, nullable=False)
    qc_passed: Mapped[bool | None] = mapped_column(sa.Boolean)
    qc_report: Mapped[dict[str, Any] | None] = mapped_column(sa.JSON)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RenderVariant {self.video_id} {self.target_platform} "
            f"p{self.part_index}/{self.part_total}>"
        )
