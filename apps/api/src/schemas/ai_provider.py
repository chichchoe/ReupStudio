from __future__ import annotations

from pydantic import BaseModel, Field


class NhaCungCapOut(BaseModel):
    ma: str
    ten: str
    ghi_chu: str
    #: Nơi lấy khoá — hiện lên để người dùng khỏi đi tìm.
    trang_lay_khoa: str
    base_url_mac_dinh: str
    #: Ghi đè địa chỉ gốc. Rỗng = dùng mặc định.
    base_url: str
    #: Ollama chạy tại máy nên không cần khoá.
    can_khoa: bool
    #: Đã dán khoá chưa. KHÔNG bao giờ trả chính khoá (luật số 6).
    da_dat_khoa: bool
    enabled: bool
    model_goi_y: list[str] = Field(default_factory=list)
    #: Bên được chọn sẵn ở tab Chờ dịch, theo ``LLM_PROVIDER`` trong Cấu hình.
    mac_dinh: bool = False
    #: Model chọn sẵn — CHỈ điền cho bên mặc định, bên khác luôn rỗng.
    model_mac_dinh: str = ""


class SuaNhaCungCapIn(BaseModel):
    """Ô khoá để trống = giữ nguyên, không phải xoá."""

    api_key: str | None = None
    base_url: str | None = None
    enabled: bool = True
