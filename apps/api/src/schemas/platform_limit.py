from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

#: Mô tả dùng chung cho cả Out/Update để trang /docs hiện đúng ý nghĩa của 0.
_MAX_DURATION_SEC_DESC = "Số giây tối đa. 0 = KHÔNG giới hạn thời lượng (không phải dữ liệu thiếu)."


class SafeArea(BaseModel):
    """Vùng bị giao diện nền tảng che, theo PHẦN TRĂM 0–1 (luật số 2 CLAUDE.md).

    Khai thành model chứ không phải ``dict[str, float]``: dict cho ra
    ``additionalProperties`` trong OpenAPI, mất sạch tên bốn cạnh, nên frontend
    phải gõ tay lại interface — đúng thứ luật số 7 cấm.
    """

    top: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)
    left: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)


class PlatformLimitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform: str
    max_duration_sec: int = Field(description=_MAX_DURATION_SEC_DESC)
    max_title_len: int
    max_desc_len: int
    max_hashtags: int
    safe_daily_posts: int
    aspect_ratios: list[str]
    safe_area: SafeArea
    notes: str | None
    updated_at: datetime


class PlatformLimitUpdate(BaseModel):
    max_duration_sec: int | None = Field(default=None, description=_MAX_DURATION_SEC_DESC)
    max_title_len: int | None = None
    max_desc_len: int | None = None
    max_hashtags: int | None = None
    safe_daily_posts: int | None = None
    aspect_ratios: list[str] | None = None
    safe_area: SafeArea | None = None
    notes: str | None = None
