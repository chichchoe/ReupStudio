"""feat(limits): M4-BE-01 tạo bảng platform_limits + seed 5 nền tảng

Nguồn sự thật cho giới hạn nền tảng (luật số 5 CLAUDE.md): "Giới hạn nền tảng
đọc từ bảng `platform_limits`, không hardcode trong code". Giá trị seed dưới
đây chỉ là GIÁ TRỊ KHỞI ĐẦU để người dùng chỉnh qua API — không phải chân lý,
vì các nền tảng đổi giới hạn (độ dài caption, số hashtag, ...) thường xuyên.

``max_duration_sec`` seed bằng ``0`` cho cả 5 nền tảng — nghĩa là KHÔNG giới
hạn thời lượng, không phải dữ liệu thiếu/lỗi. Người dùng tự xem lại video
trước khi đăng nên không muốn công cụ tự cắt/chặn theo con số phỏng đoán;
người dùng có thể bật lại giới hạn bất kỳ lúc nào qua API mà không cần
deploy — đó chính là mục đích của bảng này.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

platform_limits_table = sa.table(
    "platform_limits",
    sa.column("platform", sa.String()),
    sa.column("max_duration_sec", sa.Integer()),
    sa.column("max_title_len", sa.Integer()),
    sa.column("max_desc_len", sa.Integer()),
    sa.column("max_hashtags", sa.Integer()),
    sa.column("safe_daily_posts", sa.Integer()),
    sa.column("aspect_ratios", sa.JSON()),
    sa.column("safe_area", sa.JSON()),
)


def upgrade() -> None:
    op.create_table(
        "platform_limits",
        sa.Column("platform", sa.String(16), primary_key=True),
        sa.Column("max_duration_sec", sa.Integer(), nullable=False),
        sa.Column("max_title_len", sa.Integer(), nullable=False),
        sa.Column("max_desc_len", sa.Integer(), nullable=False),
        sa.Column("max_hashtags", sa.Integer(), nullable=False),
        sa.Column("safe_daily_posts", sa.Integer(), nullable=False),
        sa.Column("aspect_ratios", sa.JSON(), nullable=False),
        sa.Column("safe_area", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.bulk_insert(
        platform_limits_table,
        [
            {
                "platform": "tiktok",
                "max_duration_sec": 0,  # 0 = không giới hạn
                "max_title_len": 150,
                "max_desc_len": 2200,
                "max_hashtags": 30,
                "safe_daily_posts": 3,
                "aspect_ratios": ["9:16"],
                "safe_area": {"top": 0.06, "bottom": 0.18, "left": 0.05, "right": 0.20},
            },
            {
                "platform": "youtube",
                "max_duration_sec": 0,  # 0 = không giới hạn
                "max_title_len": 100,
                "max_desc_len": 5000,
                "max_hashtags": 15,
                "safe_daily_posts": 5,
                "aspect_ratios": ["9:16"],
                "safe_area": {"top": 0.06, "bottom": 0.14, "left": 0.05, "right": 0.12},
            },
            {
                "platform": "facebook",
                "max_duration_sec": 0,  # 0 = không giới hạn
                "max_title_len": 255,
                "max_desc_len": 2200,
                "max_hashtags": 30,
                "safe_daily_posts": 3,
                "aspect_ratios": ["9:16"],
                "safe_area": {"top": 0.08, "bottom": 0.20, "left": 0.05, "right": 0.18},
            },
            {
                "platform": "instagram",
                "max_duration_sec": 0,  # 0 = không giới hạn
                "max_title_len": 125,
                "max_desc_len": 2200,
                "max_hashtags": 30,
                "safe_daily_posts": 3,
                "aspect_ratios": ["9:16"],
                "safe_area": {"top": 0.08, "bottom": 0.22, "left": 0.05, "right": 0.20},
            },
            {
                "platform": "zalo",
                "max_duration_sec": 0,  # 0 = không giới hạn
                "max_title_len": 120,
                "max_desc_len": 1500,
                "max_hashtags": 20,
                "safe_daily_posts": 3,
                "aspect_ratios": ["9:16"],
                "safe_area": {"top": 0.06, "bottom": 0.16, "left": 0.05, "right": 0.15},
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("platform_limits")
