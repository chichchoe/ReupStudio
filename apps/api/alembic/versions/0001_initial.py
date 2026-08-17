"""M0-BE-02: tạo bảng videos, subtitles, job_runs

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_platform", sa.String(32), nullable=False),
        sa.Column("source_video_id", sa.String(128), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_author", sa.String(255)),
        sa.Column("title_original", sa.Text()),
        sa.Column("desc_original", sa.Text()),
        sa.Column("title_vi", sa.Text()),
        sa.Column("desc_vi", sa.Text()),
        sa.Column("hashtags_vi", sa.JSON()),
        sa.Column("duration_sec", sa.Float()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("fps", sa.Float()),
        sa.Column("has_audio", sa.Boolean()),
        sa.Column("view_count_source", sa.BigInteger()),
        sa.Column("md5", sa.String(32)),
        sa.Column("phash", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("current_step", sa.String(32)),
        sa.Column("error_message", sa.Text()),
        sa.Column("flags", sa.JSON(), server_default="{}"),
        sa.Column("raw_path", sa.Text()),
        sa.Column("out_path", sa.Text()),
        sa.Column("process_config", sa.JSON(), server_default="{}"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_platform", "source_video_id", name="uq_video_source"),
    )
    op.create_index("ix_videos_status", "videos", ["status"])
    op.create_index("ix_videos_md5", "videos", ["md5"])

    op.create_table(
        "subtitles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "video_id",
            sa.Uuid(),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lang", sa.String(8), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("cues", sa.JSON(), nullable=False),
        sa.Column("edited_by_user", sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("video_id", "lang", name="uq_subtitle_video_lang"),
    )

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "video_id",
            sa.Uuid(),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("celery_task_id", sa.String(64)),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_sec", sa.Float()),
        sa.Column("log", sa.Text()),
        sa.Column("meta", sa.JSON(), server_default="{}"),
    )
    op.create_index("ix_job_runs_video_step", "job_runs", ["video_id", "step"])


def downgrade() -> None:
    op.drop_table("job_runs")
    op.drop_table("subtitles")
    op.drop_table("videos")
