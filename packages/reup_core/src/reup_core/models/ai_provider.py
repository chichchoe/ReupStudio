from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AiProvider(Base, TimestampMixin):
    """Một nhà cung cấp AI đã cấu hình khoá — Gemini, OpenRouter, Claude, DeepSeek.

    Vì sao là BẢNG chứ không phải vài dòng trong ``app_settings``: người dùng
    cấu hình NHIỀU bên cùng lúc rồi chọn bên nào cho từng video. Nhét nhiều bên
    vào một tập biến phẳng (``LLM_API_KEY``, ``LLM_BASE_URL``…) buộc phải sửa
    cấu hình mỗi lần đổi nhà cung cấp, và chỉ giữ được đúng một khoá.

    ``base_url`` để trống thì dùng địa chỉ mặc định của nhà cung cấp đó — chỉ
    cần điền khi chạy qua proxy hoặc bản tự dựng.
    """

    __tablename__ = "ai_providers"

    #: gemini · openrouter · anthropic · deepseek · openai · ollama
    ma: Mapped[str] = mapped_column(sa.String(32), primary_key=True)

    #: Khoá API đã mã hoá Fernet (luật số 6 CLAUDE.md). Không bao giờ trả ra API.
    api_key_encrypted: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    #: Ghi đè địa chỉ gốc. Rỗng = dùng mặc định của nhà cung cấp.
    base_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
