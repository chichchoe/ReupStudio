"""M2-BE-05: tạo bảng source_channels

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_channels",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("handle", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("scan_interval_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_video_id", sa.String(128), nullable=True),
        # Không đặt khoá ngoại cứng ở M2 — bảng preset có thể đổi trước khi liên kết chốt.
        sa.Column("filter_preset_id", sa.Uuid(), nullable=True),
        sa.Column("process_preset_id", sa.Uuid(), nullable=True),
        sa.Column(
            "license_status", sa.String(16), nullable=False, server_default="unknown"
        ),
        sa.Column("license_note", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "platform", "external_id", name="uq_source_channel_platform_external"
        ),
    )
    op.create_index(
        "ix_source_channels_enabled_last_scanned",
        "source_channels",
        ["enabled", "last_scanned_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_channels_enabled_last_scanned", table_name="source_channels")
    op.drop_table("source_channels")
