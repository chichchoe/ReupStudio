"""feat(giong): bảng giong_doc — thư viện giọng gộp một chỗ

Trước đây ba nhóm giọng nằm cứng trong ``video_service.cac_giong_doc`` và giao
diện bắt chọn ba tầng: nhà cung cấp → model → giọng. Thêm giọng clone của Fish
vào khuôn đó là thêm tầng thứ tư. Gộp lại thì thêm giọng chỉ là thêm một dòng.

Seed sẵn các giọng dựng sẵn từ chính danh sách đang hardcode, để bảng là nguồn
sự thật duy nhất ngay từ lần chạy đầu.

Chỉ số duy nhất trên ``mac_dinh`` là chỉ số MỘT PHẦN — chỉ ràng buộc dòng đang
là mặc định, không phải mọi dòng.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


#: Giọng dựng sẵn, chép từ ``video_service.cac_giong_doc`` lúc còn hardcode.
#: Chỉ seed hai giọng edge: Gemini và OpenRouter chỉ dùng được khi đã dán khoá,
#: mà seed sẵn thì người dùng chọn phải rồi bấm Dịch mới báo lỗi — cách chắc
#: chắn nhất làm họ tưởng hỏng.
_GIONG_EDGE = [
    ("Hoài My", "vi-VN-HoaiMyNeural", True),
    ("Nam Minh", "vi-VN-NamMinhNeural", False),
]


def upgrade() -> None:
    op.create_table(
        "giong_doc",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ten", sa.String(80), nullable=False),
        sa.Column("nha_cung_cap", sa.String(32), nullable=False),
        sa.Column("ma_giong", sa.String(64), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("ngon_ngu", sa.String(8), nullable=False, server_default="vi"),
        sa.Column("nguon", sa.String(16), nullable=False, server_default="dung_san"),
        sa.Column("mau_text", sa.Text(), nullable=True),
        sa.Column("co_ma_hoa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trang_thai", sa.String(16), nullable=False, server_default="san_sang"),
        sa.Column("loi", sa.Text(), nullable=True),
        sa.Column("canh_bao", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("do_dai_giay", sa.Float(), nullable=True),
        sa.Column("nghe_thu_bang", sa.String(32), nullable=True),
        sa.Column("mac_dinh", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    #: MỘT PHẦN — chỉ ràng buộc dòng đang là mặc định. Duy nhất toàn phần thì
    #: chỉ lưu được đúng hai giọng (một true, một false).
    op.create_index(
        "uq_giong_doc_mac_dinh",
        "giong_doc",
        ["mac_dinh"],
        unique=True,
        postgresql_where=sa.text("mac_dinh"),
        sqlite_where=sa.text("mac_dinh"),
    )

    bang = sa.table(
        "giong_doc",
        sa.column("id", sa.Uuid()),
        sa.column("ten", sa.String()),
        sa.column("nha_cung_cap", sa.String()),
        sa.column("ma_giong", sa.String()),
        sa.column("ngon_ngu", sa.String()),
        sa.column("nguon", sa.String()),
        sa.column("trang_thai", sa.String()),
        sa.column("mac_dinh", sa.Boolean()),
    )
    import uuid as _uuid

    op.bulk_insert(
        bang,
        [
            {
                "id": _uuid.uuid4(),
                "ten": ten,
                "nha_cung_cap": "edge",
                "ma_giong": ma,
                "ngon_ngu": "vi",
                "nguon": "dung_san",
                "trang_thai": "san_sang",
                "mac_dinh": mac_dinh,
            }
            for ten, ma, mac_dinh in _GIONG_EDGE
        ],
    )


def downgrade() -> None:
    op.drop_index("uq_giong_doc_mac_dinh", table_name="giong_doc")
    op.drop_table("giong_doc")
