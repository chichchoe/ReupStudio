from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, uuid_pk


class CostLog(Base):
    """Mỗi lượt gọi dịch vụ ngoài tốn tiền hoặc tốn hạn mức = một dòng ở đây.

    CLAUDE.md yêu cầu thẳng cho mọi lời gọi API bên ngoài: "Luôn có: timeout,
    retry với backoff, giới hạn số lần, ghi ``cost_logs``".

    Bảng này phục vụ HAI việc, và đó là lý do nó tồn tại thay vì chỉ ghi log:

    1. **Biết đã tiêu bao nhiêu** — cộng ``cost_usd`` theo tháng.
    2. **Biết đã chạm trần hạn mức chưa** — đếm số dòng trong 60 giây gần nhất
       và trong ngày. Đo ngày 2026-08-14: Gemini KHÔNG trả về header hạn mức
       nào (không có ``x-ratelimit-*``), nên không hỏi được nhà cung cấp còn
       bao nhiêu lượt — phải tự đếm tại máy. Cùng bộ đếm này vừa dùng để hiển
       thị, vừa dùng để giãn nhịp chủ động và chặn khi vượt trần: một nguồn sự
       thật duy nhất, không có hai bộ đếm lệch nhau.

    ``quantity`` tính theo ``unit`` (``token`` cho LLM, ``giây`` cho TTS...).
    Với Gemini phải lấy ``total_tokens``, KHÔNG cộng
    ``prompt_tokens + completion_tokens``: đo thật thấy 9 + 0 ≠ 26 vì token
    suy luận không nằm trong hai ô đó, cộng tay sẽ đếm hụt.

    ``model`` là cột thêm so với bảng mô tả trong ``docs/02-DATABASE-VA-API.md``
    — thiếu nó thì không tái dựng được chi phí, vì mỗi model một đơn giá.

    ``video_id`` cho phép NULL: có lượt gọi không thuộc video nào (thử kết nối,
    sinh tiêu đề hàng loạt). Xoá video thì đặt về NULL chứ không xoá dòng —
    tiền đã tiêu rồi, xoá đi là sổ sách sai.
    """

    __tablename__ = "cost_logs"
    __table_args__ = (
        sa.Index("ix_cost_logs_created_at", "created_at"),
        sa.Index("ix_cost_logs_service_created", "service", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("videos.id", ondelete="SET NULL"), nullable=True
    )
    #: llm_translate | llm_title | tts | gpu_inpaint | bandwidth
    service: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(sa.String(128))
    #: token | giây | byte
    unit: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    quantity: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    cost_usd: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CostLog {self.service} {self.quantity}{self.unit} ${self.cost_usd}>"
