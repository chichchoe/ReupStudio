from __future__ import annotations

from pydantic import BaseModel, Field


class MucCauHinhOut(BaseModel):
    key: str
    mo_ta: str
    #: Với bí mật, đây LUÔN là chuỗi che — giá trị thật không bao giờ ra khỏi API.
    value: str
    is_secret: bool
    #: Bí mật đã có giá trị chưa. Giao diện cần phân biệt "đã đặt" với "chưa
    #: đặt" mà không được biết giá trị.
    da_dat: bool


class NhomCauHinhOut(BaseModel):
    ten: str
    muc: list[MucCauHinhOut]


class CauHinhOut(BaseModel):
    nhom: list[NhomCauHinhOut]
    #: Các biến BẮT BUỘC vẫn nằm trong .env — hiện ra để người dùng biết vì sao
    #: không tìm thấy chúng trên trang này.
    khoa_bootstrap: list[str]


class SuaCauHinhIn(BaseModel):
    """Chỉ gửi những khoá thật sự đổi.

    Ô bí mật để trống = giữ nguyên, không phải xoá.
    """

    gia_tri: dict[str, str] = Field(default_factory=dict)


class KhoaMoiOut(BaseModel):
    khoa: str
    huong_dan: str
