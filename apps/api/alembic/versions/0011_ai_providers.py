"""feat(settings): bảng ai_providers — cấu hình nhiều nhà cung cấp AI cùng lúc

Chủ dự án muốn dán khoá của Gemini, OpenRouter, Claude, DeepSeek rồi chọn bên
nào cho từng video, thay vì phải sửa cấu hình mỗi lần đổi.

Là BẢNG chứ không phải vài dòng trong ``app_settings``: tập biến phẳng
(``LLM_API_KEY``, ``LLM_BASE_URL``…) chỉ giữ được đúng MỘT khoá.

``api_key_encrypted`` mã hoá Fernet như mọi bí mật khác (luật số 6).

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_providers",
        sa.Column("ma", sa.String(32), primary_key=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_providers")
