from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, uuid_pk


class MaskRegion(Base, TimestampMixin):
    """Một vùng chữ cứng hoặc watermark sẽ bị xoá khỏi khung hình (M3).

    Lưu vào DB thay vì tính lại mỗi lần render vì ba lý do:

    1. Dò lại tốn 0,11 giây mỗi khung — video một tiếng mất hàng chục phút chỉ
       để ra đúng kết quả cũ.
    2. Người dùng phải sửa được bằng tay, và bản sửa tay không được mất khi
       chạy lại.
    3. Phải xem lại được máy đã xoá những gì, sau khi video đã đăng.
    """

    __tablename__ = "mask_regions"

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: Toạ độ PHẦN TRĂM 0–1 (luật số 2 CLAUDE.md), không bao giờ pixel: cùng
    #: một mask phải dùng được cho cả bản gốc lẫn bản đã đổi khung 9:16.
    x: Mapped[float] = mapped_column(sa.Float, nullable=False)
    y: Mapped[float] = mapped_column(sa.Float, nullable=False)
    w: Mapped[float] = mapped_column(sa.Float, nullable=False)
    h: Mapped[float] = mapped_column(sa.Float, nullable=False)

    #: Khoảng thời gian mask tồn tại, tính bằng giây từ đầu video. Áp cả video
    #: sẽ vá cả những đoạn vốn sạch.
    start_sec: Mapped[float] = mapped_column(sa.Float, nullable=False)
    end_sec: Mapped[float] = mapped_column(sa.Float, nullable=False)

    #: ``auto`` máy dò · ``manual`` người sửa. Lần dò lại chỉ được xoá dòng
    #: ``auto``, nếu không thì chỉnh tay của người dùng biến mất.
    source: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="auto")

    #: Điểm của bộ lọc, giữ nguyên để giao diện xếp hạng vùng đáng ngờ.
    confidence: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)

    #: Các tín hiệu đã cộng điểm, viết cho người đọc. Không giải thích được vì
    #: sao máy định xoá thì người dùng không duyệt được.
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    video = relationship("Video", back_populates="mask_regions")
