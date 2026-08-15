from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AppSetting(Base, TimestampMixin):
    """Một dòng cấu hình của ứng dụng, thay cho biến trong ``.env``.

    Vì sao chuyển vào DB: file ``.env`` nằm cạnh mã nguồn nên chỉ cần một lần
    ``git add -A`` bất cẩn là khoá API lên GitHub. Chuyện đó đã suýt xảy ra
    ngày 2026-08-16 — GitHub chặn lại được, nhưng chỉ vì họ có quét bí mật.

    Bí mật lưu ở ``value_encrypted`` (Fernet), giá trị thường lưu ở
    ``value_plain``. Hai cột riêng chứ không dùng chung một cột: nhìn vào bảng
    là biết ngay dòng nào đã mã hoá, không phải đoán theo tên khoá.

    KHÔNG chuyển được vào đây: ``DATABASE_URL`` (dùng để tới chính bảng này),
    ``REDIS_URL`` (worker cần lúc khởi động, trước khi có DB), và
    ``SETTINGS_KEY`` (khoá giải mã chính cột ``value_encrypted``).
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)

    value_plain: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    #: Chuỗi Fernet đã mã hoá. Không bao giờ trả ra qua API (luật số 6).
    value_encrypted: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    is_secret: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
