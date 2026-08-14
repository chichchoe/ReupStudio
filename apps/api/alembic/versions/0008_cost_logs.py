"""feat(cost): bảng cost_logs — đo hạn mức và chi phí gọi API ngoài

CLAUDE.md yêu cầu cho mọi lời gọi API bên ngoài: "Luôn có: timeout, retry với
backoff, giới hạn số lần, ghi `cost_logs`". Backlog xếp việc này ở M8-BE-04
nhưng phải kéo lên sớm vì một lý do đo được: dịch một video 34 phút (672 câu)
mất 3 TIẾNG do liên tục đụng 429 của bậc miễn phí, mà không có chỗ nào cho biết
đã dùng bao nhiêu lượt hay còn bao nhiêu.

Đo ngày 2026-08-14: Gemini KHÔNG trả về header hạn mức nào (`x-ratelimit-*`),
nên không hỏi được nhà cung cấp còn bao nhiêu lượt. Bảng này là cách duy nhất
biết được — đếm số dòng trong 60 giây gần nhất và trong ngày.

Cột `model` là phần thêm so với bảng mô tả trong `docs/02-DATABASE-VA-API.md`:
thiếu nó thì không tái dựng được chi phí vì mỗi model một đơn giá.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_logs",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # SET NULL chứ không CASCADE: xoá video không được xoá dấu vết tiền đã
        # tiêu, xoá đi là sổ sách sai.
        sa.Column(
            "video_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("videos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("service", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Hai truy vấn nóng: đếm theo thời gian (hạn mức phút/ngày) và cộng tiền
    # theo dịch vụ trong tháng.
    op.create_index("ix_cost_logs_created_at", "cost_logs", ["created_at"])
    op.create_index("ix_cost_logs_service_created", "cost_logs", ["service", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_cost_logs_service_created", table_name="cost_logs")
    op.drop_index("ix_cost_logs_created_at", table_name="cost_logs")
    op.drop_table("cost_logs")
