from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ..enums import NguonGiong, TrangThaiGiong
from .base import Base, TimestampMixin, uuid_pk


class GiongDoc(Base, TimestampMixin):
    """Một giọng đọc trong thư viện — dựng sẵn của nhà cung cấp, hoặc clone.

    Vì sao gộp cả hai loại vào MỘT bảng: trước đây ba nhóm giọng nằm cứng
    trong ``video_service.cac_giong_doc`` và giao diện bắt chọn ba tầng (nhà
    cung cấp → model → giọng). Thêm giọng clone vào khuôn đó là thêm tầng thứ
    tư. Gộp lại thì thêm giọng chỉ là thêm một dòng.

    Giọng ``dung_san`` không có đoạn mẫu (``mau_text``, ``co_ma_hoa`` để rỗng);
    giọng clone không có ``ma_giong`` — Fish S2-Pro không có trường ``voice``,
    giọng đến từ đoạn mẫu.
    """

    __tablename__ = "giong_doc"
    __table_args__ = (
        #: Chỉ số duy nhất MỘT PHẦN: chỉ ràng buộc những dòng đang là mặc định.
        #: Thiếu ``sqlite_where`` bên cạnh ``postgresql_where`` thì trên SQLite
        #: nó thành duy nhất TOÀN PHẦN và giọng thứ hai (mac_dinh=false) bị từ
        #: chối — hỏng chỉ trong test, không hỏng khi chạy thật.
        sa.Index(
            "uq_giong_doc_mac_dinh",
            "mac_dinh",
            unique=True,
            postgresql_where=sa.text("mac_dinh"),
            sqlite_where=sa.text("mac_dinh"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()

    #: Tên người dùng đặt: "Giọng tôi", "Chị Lan thuê".
    ten: Mapped[str] = mapped_column(sa.String(80), nullable=False)

    #: edge · gemini · openrouter · fish_mlx
    nha_cung_cap: Mapped[str] = mapped_column(sa.String(32), nullable=False)

    #: Mã giọng dựng sẵn (``vi-VN-HoaiMyNeural``). NULL với giọng clone.
    ma_giong: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    #: Model TTS đi kèm, nếu nhà cung cấp cần. NULL với edge và fish_mlx.
    model: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    ngon_ngu: Mapped[str] = mapped_column(sa.String(8), nullable=False, default="vi")

    #: nam · nữ · rỗng. Chỉ để người dùng lọc nhanh trong danh sách; giọng
    #: clone thường để rỗng vì mẫu là của chính họ.
    gioi_tinh: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="")

    #: dung_san · tu_thu · cat_tu_file · thue_doc · tam_tu_may
    nguon: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default=NguonGiong.DUNG_SAN.value
    )

    #: Phần chữ của đoạn mẫu. Nhân bản giọng cần CẢ âm thanh lẫn chữ khớp từng
    #: chữ — lệch chữ là méo giọng.
    mau_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    #: Đã mã hoá xong ``reference_codes`` chưa. Mã hoá một lần, mọi câu dùng lại.
    co_ma_hoa: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    #: dang_xu_ly · san_sang · hong. Dựng một giọng mất vài chục giây (ffmpeg +
    #: Whisper + đọc thử) nên chạy nền; giao diện cần biết đang tới đâu.
    trang_thai: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default=TrangThaiGiong.SAN_SANG.value
    )

    #: Lý do dựng hỏng. Không có thì giọng treo ở "đang xử lý" mà không ai biết vì sao.
    loi: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    #: Cảnh báo của cổng chất lượng: ``[{"ma": ..., "thong_diep": ...}]``.
    #: Cảnh báo chứ không chặn — nhưng phải hiện được trên thẻ giọng.
    canh_bao: Mapped[list[dict[str, Any]]] = mapped_column(
        sa.JSON, nullable=False, default=list
    )

    #: Độ dài đoạn mẫu đã chuẩn hoá, giây. Hiện trên thẻ để so nhanh giữa các giọng.
    do_dai_giay: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    #: Nhà cung cấp đã dựng câu đọc thử — để biết file nghe-thu.wav là của bên
    #: nào khi đổi nhà cung cấp giữa chừng.
    nghe_thu_bang: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)

    #: Mốc cắt của nguồn ``cat_tu_file`` (giây). Lưu lại để cắt lại được mà
    #: không phải tải file lên lần nữa.
    cat_tu_giay: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    cat_den_giay: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    mac_dinh: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    ghi_chu: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
