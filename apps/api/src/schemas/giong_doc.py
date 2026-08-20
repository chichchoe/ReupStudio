"""Kiểu vào/ra cho thư viện giọng."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CanhBaoOut(BaseModel):
    ma: str
    thong_diep: str


class GiongThuVienOut(BaseModel):
    """Một giọng trong thư viện.

    Tên KHÁC ``video.GiongDocOut`` (giọng lồng trong danh sách của một nhà
    cung cấp, dùng cho ``/tts-options``) — trùng tên thì OpenAPI phải sinh ra
    ``src__schemas__video__GiongDocOut`` và giao diện phải gõ cái tên đó.
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    ten: str
    nha_cung_cap: str
    ma_giong: str | None = None
    model: str | None = None
    ngon_ngu: str = "vi"
    nguon: str
    mau_text: str | None = None
    trang_thai: str
    mac_dinh: bool = False
    ghi_chu: str | None = None
    loi: str | None = None
    canh_bao: list[CanhBaoOut] = Field(default_factory=list)
    #: Đã có file nghe thử trên đĩa chưa. Giọng seed sẵn có ``trang_thai`` là
    #: ``san_sang`` nhưng CHƯA dựng câu đọc thử — không có cờ này thì giao
    #: diện hiện nút ▶ rồi trả 404, trông như hỏng.
    co_nghe_thu: bool = False
    #: Độ dài đoạn mẫu đã chuẩn hoá, giây. Thẻ giọng hiện số này để so nhanh
    #: giữa các giọng. ``None`` với giọng dựng sẵn (không có đoạn mẫu).
    do_dai_giay: float | None = None
    #: Nhà cung cấp THẬT SỰ đã dựng file nghe thử — khác ``nha_cung_cap`` khi
    #: đã phải rơi về đường lui.
    nghe_thu_bang: str | None = None
    created_at: datetime


class TaoGiongIn(BaseModel):
    """Tạo giọng. File âm thanh gửi kèm dạng multipart, không nằm trong body này."""

    ten: str = Field(min_length=1, max_length=80)
    nguon: str
    nha_cung_cap: str = "fish_mlx"
    ghi_chu: str = ""
    #: Chỉ dùng khi ``nguon="cat_tu_file"`` — cắt đoạn nào trong file dài.
    cat_tu_giay: float | None = None
    cat_den_giay: float | None = None


class SuaGiongIn(BaseModel):
    ten: str | None = Field(default=None, min_length=1, max_length=80)
    ghi_chu: str | None = None
    mac_dinh: bool | None = None
    #: Sửa lại phần chữ Whisper gõ chưa khớp. Lệch chữ là méo giọng.
    mau_text: str | None = None
