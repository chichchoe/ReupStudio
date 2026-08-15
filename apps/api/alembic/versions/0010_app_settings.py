"""feat(settings): bảng app_settings — cấu hình chuyển từ .env vào DB

Vì sao: file ``.env`` nằm cạnh mã nguồn nên chỉ cần một lần ``git add -A`` bất
cẩn là khoá API lên GitHub. Chuyện đó suýt xảy ra ngày 2026-08-16 và chỉ được
chặn lại nhờ bộ quét bí mật của GitHub.

Bí mật lưu ở ``value_encrypted`` (Fernet), giá trị thường ở ``value_plain``.
Hai cột riêng chứ không dùng chung: nhìn vào bảng là biết ngay dòng nào đã mã
hoá, không phải đoán theo tên khoá.

BA BIẾN KHÔNG CHUYỂN ĐƯỢC vào đây vì cần TRƯỚC khi chạm được DB:
``DATABASE_URL`` (dùng để tới chính bảng này), ``REDIS_URL`` (worker cần lúc
khởi động), ``SETTINGS_KEY`` (khoá giải mã chính cột value_encrypted).

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value_plain", sa.Text(), nullable=True),
        sa.Column("value_encrypted", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
