"""feat(m3): bảng mask_regions — vùng chữ cứng và watermark sẽ bị xoá

Lưu mask vào DB thay vì tính lại mỗi lần render, vì ba lý do:

1. Dò lại tốn 0,11 giây mỗi khung — video một tiếng mất hàng chục phút chỉ để
   ra đúng kết quả cũ.
2. Người dùng phải sửa được bằng tay, và bản sửa tay không được mất khi chạy
   lại (cột ``source`` phân biệt ``auto`` với ``manual``).
3. Phải xem lại được máy đã xoá những gì, sau khi video đã đăng.

Toạ độ theo PHẦN TRĂM 0–1 chứ không theo pixel (luật số 2 CLAUDE.md): cùng một
mask phải dùng được cho cả bản gốc lẫn bản đã đổi khung sang 9:16.

Cột ``reason`` là phần thêm so với mô tả trong ``docs/02-DATABASE-VA-API.md``.
Bộ lọc cộng điểm từ năm tín hiệu; không ghi lại tín hiệu nào đã cộng thì giao
diện không giải thích được vì sao máy định xoá một vùng, và người dùng không
duyệt được.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mask_regions",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "video_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("w", sa.Float(), nullable=False),
        sa.Column("h", sa.Float(), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False),
        sa.Column("end_sec", sa.Float(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="auto"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=True),
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
    #: Truy vấn nóng duy nhất: lấy mọi mask của MỘT video, sắp theo thời gian.
    op.create_index("ix_mask_regions_video", "mask_regions", ["video_id", "start_sec"])


def downgrade() -> None:
    op.drop_index("ix_mask_regions_video", table_name="mask_regions")
    op.drop_table("mask_regions")
