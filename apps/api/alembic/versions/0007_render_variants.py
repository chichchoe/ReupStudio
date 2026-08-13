"""feat(shortform): M4-WK-05 tạo bảng render_variants

Luật số 8 CLAUDE.md: "Một video sinh nhiều `render_variants` (một bản mỗi nền
tảng đích). Không thiết kế 1-1." Trước migration này, một video chỉ có đúng
MỘT file kết quả (``videos.out_path``); từ đây mỗi tổ hợp (nền tảng, tập) là
một dòng riêng ở bảng này. ``videos.out_path`` giữ nguyên, không xoá — pipeline
M1 (chưa tách theo nền tảng) vẫn dùng cột đó.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "render_variants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "video_id",
            sa.Uuid(),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_platform", sa.String(16), nullable=False),
        sa.Column("part_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("part_total", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("out_path", sa.Text(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("qc_passed", sa.Boolean(), nullable=True),
        sa.Column("qc_report", sa.JSON(), nullable=True),
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
        sa.UniqueConstraint(
            "video_id", "target_platform", "part_index", name="uq_render_variant"
        ),
    )
    op.create_index(
        "ix_render_variants_video_id", "render_variants", ["video_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_render_variants_video_id", table_name="render_variants")
    op.drop_table("render_variants")
