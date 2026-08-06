"""M2-BE-04: tạo bảng presets + seed 4 preset mặc định

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# UUID cố định (không phải uuid4 ngẫu nhiên) để migration seed cùng id preset
# mặc định ở mọi môi trường dev/test.
PRESET_FILTER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
PRESET_PROCESS_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
PRESET_ANTIDUP_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
PRESET_SUBTITLE_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")

presets_table = sa.table(
    "presets",
    sa.column("id", sa.Uuid()),
    sa.column("kind", sa.String()),
    sa.column("name", sa.String()),
    sa.column("config", sa.JSON()),
    sa.column("is_default", sa.Boolean()),
)


def upgrade() -> None:
    op.create_table(
        "presets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("kind", "name", name="uq_preset_kind_name"),
    )
    op.create_index("ix_presets_kind", "presets", ["kind"])

    op.bulk_insert(
        presets_table,
        [
            {
                "id": PRESET_FILTER_ID,
                "kind": "filter",
                "name": "Lọc mặc định",
                "config": {
                    "min_duration_sec": 15,
                    "max_duration_sec": 180,
                    "min_views": 10000,
                    "vertical_only": True,
                },
                "is_default": True,
            },
            {
                "id": PRESET_PROCESS_ID,
                "kind": "process",
                "name": "Xử lý mặc định",
                "config": {
                    "tone": "doi_thuong",
                    "burn_subtitle": True,
                    "sub_max_chars_per_line": 42,
                    "sub_max_lines": 2,
                },
                "is_default": True,
            },
            {
                "id": PRESET_ANTIDUP_ID,
                "kind": "antidup",
                "name": "Chống trùng mặc định",
                "config": {
                    "md5": True,
                    "phash": True,
                    "phash_max_distance": 20,
                },
                "is_default": True,
            },
            {
                "id": PRESET_SUBTITLE_ID,
                "kind": "subtitle",
                "name": "Phụ đề mặc định",
                "config": {
                    "font": "Be Vietnam Pro",
                    "font_size": 54,
                    "margin_v": 120,
                    "outline": 3,
                },
                "is_default": True,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("presets")
