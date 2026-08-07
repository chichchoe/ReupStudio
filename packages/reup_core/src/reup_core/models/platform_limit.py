from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PlatformLimit(Base):
    """Giới hạn kỹ thuật/nghiệp vụ của từng nền tảng đăng.

    Nguồn sự thật duy nhất cho giới hạn nền tảng (luật số 5 của CLAUDE.md):
    "Giới hạn nền tảng đọc từ bảng `platform_limits`, không hardcode trong
    code". Mỗi nền tảng đúng một dòng, khoá chính là ``platform`` (chuỗi,
    giá trị của enum ``Platform``) — vì vậy KHÔNG dùng ``uuid_pk()``.

    Không kế thừa ``TimestampMixin`` vì mixin đó thêm cả ``created_at``, mà
    bảng này không cần (một dòng/nền tảng được seed sẵn, không có khái niệm
    "ngày tạo" có ý nghĩa nghiệp vụ) — chỉ cần ``updated_at`` để biết lần
    chỉnh gần nhất.

    ``safe_area`` là cột lệch có chủ ý so với bảng mô tả ở
    ``docs/02-DATABASE-VA-API.md`` (bảng đó không liệt kê cột này), nhưng
    CLAUDE.md ghi rõ "Có bảng `platform_limits` mô tả vùng an toàn". Ta thêm
    cột này để hai tài liệu khớp nhau và để bước burn phụ đề (M4 Task 2) có
    nguồn dữ liệu tránh vùng UI của nền tảng.

    Toạ độ trong ``safe_area`` là **phần trăm khung hình, 0–1** (không phải
    pixel) — ví dụ ``{"top": 0.06, "bottom": 0.18, "left": 0.05, "right": 0.20}``
    nghĩa là phụ đề không được nằm trong 6% trên, 18% dưới, 5% trái, 20% phải
    của khung hình.

    ``max_duration_sec == 0`` nghĩa là **KHÔNG giới hạn thời lượng** — không
    phải dữ liệu thiếu hay seed lỗi. Giá trị seed mặc định của cả 5 nền tảng
    là ``0`` vì người dùng tự xem lại video trước khi đăng, không muốn công cụ
    tự cắt/chặn theo con số phỏng đoán; người dùng có thể bật lại giới hạn bất
    kỳ lúc nào qua API. Đây là cột DUY NHẤT cho phép ``0``, các cột số khác
    (``max_title_len``, ``max_desc_len``, ``max_hashtags``,
    ``safe_daily_posts``) luôn phải ``> 0``.
    """

    __tablename__ = "platform_limits"

    platform: Mapped[str] = mapped_column(sa.String(16), primary_key=True)
    #: 0 = không giới hạn thời lượng. Khác 0 = số giây tối đa.
    max_duration_sec: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    max_title_len: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    max_desc_len: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    max_hashtags: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    safe_daily_posts: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    aspect_ratios: Mapped[list[str]] = mapped_column(sa.JSON, nullable=False)
    safe_area: Mapped[dict[str, Any]] = mapped_column(sa.JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PlatformLimit {self.platform}>"
