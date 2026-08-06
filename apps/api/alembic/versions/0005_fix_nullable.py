"""fix(db): dọn drift nullable giữa model và migration cũ

Model khai ``Mapped[...]`` không Optional (NOT NULL) cho 13 cột nhưng các
migration ``0001``/``0003``/``0004`` tạo cột đó ở dạng nullable. Không gây lỗi
runtime (đều có ``server_default``), nhưng làm mọi ``alembic revision
--autogenerate`` sau này sinh ra đống ``alter_column ... nullable`` rác. Dọn
một thể ở đây; KHÔNG sửa các migration đã áp dụng.

4 cột thuộc bảng mới của M2 (``presets``, ``source_channels``), 9 cột còn lại
là nợ có sẵn từ ``0001`` (``videos``, ``subtitles``, ``job_runs``).

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "job_runs",
        "started_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "job_runs",
        "meta",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        nullable=False,
        existing_server_default=sa.text("'{}'::json"),
    )
    op.alter_column(
        "presets",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "presets",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "source_channels",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "source_channels",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "subtitles",
        "edited_by_user",
        existing_type=sa.BOOLEAN(),
        nullable=False,
        existing_server_default=sa.text("false"),
    )
    op.alter_column(
        "subtitles",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "subtitles",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "videos",
        "flags",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        nullable=False,
        existing_server_default=sa.text("'{}'::json"),
    )
    op.alter_column(
        "videos",
        "process_config",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        nullable=False,
        existing_server_default=sa.text("'{}'::json"),
    )
    op.alter_column(
        "videos",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "videos",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )


def downgrade() -> None:
    op.alter_column(
        "videos",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "videos",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "videos",
        "process_config",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        nullable=True,
        existing_server_default=sa.text("'{}'::json"),
    )
    op.alter_column(
        "videos",
        "flags",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        nullable=True,
        existing_server_default=sa.text("'{}'::json"),
    )
    op.alter_column(
        "subtitles",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "subtitles",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "subtitles",
        "edited_by_user",
        existing_type=sa.BOOLEAN(),
        nullable=True,
        existing_server_default=sa.text("false"),
    )
    op.alter_column(
        "source_channels",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "source_channels",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "presets",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "presets",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "job_runs",
        "meta",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        nullable=True,
        existing_server_default=sa.text("'{}'::json"),
    )
    op.alter_column(
        "job_runs",
        "started_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
