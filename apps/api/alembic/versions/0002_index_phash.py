"""M2-WK-02: index cho cột phash (chống trùng)

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Không so được khoảng cách Hamming trong SQL, nhưng index vẫn có ích cho
    # truy vấn "video nào đã có pHash" và cho bản trùng y hệt.
    op.create_index("ix_videos_phash", "videos", ["phash"])


def downgrade() -> None:
    op.drop_index("ix_videos_phash", table_name="videos")
