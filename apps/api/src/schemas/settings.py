from __future__ import annotations

from pydantic import BaseModel, Field


class MucCauHinhOut(BaseModel):
    key: str
    mo_ta: str
    #: ``select`` · ``number`` · ``text``. Ô nào chỉ có vài giá trị hợp lệ thì
    #: phải cho CHỌN, không cho gõ tay — gõ "smal" thay vì "small" là hỏng bước
    #: nhận dạng, mà lỗi chỉ hiện ra sau khi đã tải xong video.
    kieu: str = "text"
    #: Chỉ có nghĩa khi ``kieu == "select"``.
    lua_chon: list[str] = Field(default_factory=list)
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


class MucKiemTraOut(BaseModel):
    ma: str
    ten: str
    ok: bool
    chi_tiet: str = ""
    cach_sua: str = ""
    tu_sua_duoc: bool = False


class ThongTinMayOut(BaseModel):
    """Tình trạng máy đang chạy — dùng cho mục "Cài đặt" ở trang Cấu hình."""

    ten_may: str
    he_dieu_hanh: str
    kien_truc: str
    python: str
    thu_muc_du_an: str
    thu_muc_media: str
    dung_luong_trong_gb: float
    muc: list[MucKiemTraOut]


class KetQuaCaiDatOut(BaseModel):
    da_lam: list[str]
