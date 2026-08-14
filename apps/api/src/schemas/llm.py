from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

#: Dùng chung cho cả ba trần để trang /docs nói rõ ý nghĩa của số 0 — frontend
#: phải phân biệt "chưa khai trần" với "trần bằng không lượt".
_KHONG_GIOI_HAN = "0 = KHÔNG giới hạn (chưa khai trần), không phải cấm gọi."


class LlmModelsOut(BaseModel):
    """Model dùng được với khoá hiện tại, đã lọc theo mục đích.

    Chia sẵn hai nhóm thay vì trả danh sách phẳng kèm nhãn: ô chọn "AI dịch" và
    ô chọn "giọng đọc" là hai chỗ khác nhau, và nhóm sai thì người dùng chọn
    phải model chỉ có 10 lượt/ngày.
    """

    #: Id đã bỏ tiền tố ``models/``, giữ nguyên thứ tự nhà cung cấp trả về.
    translate: list[str]
    tts: list[str]


class LlmUsageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    requests_last_min: int = Field(description="Số lượt gọi LLM trong 60 giây gần nhất.")
    requests_last_day: int = Field(description="Số lượt gọi LLM trong 24 giờ gần nhất.")
    tokens_last_day: int = Field(description="Tổng token LLM trong 24 giờ gần nhất.")
    cost_usd_this_month: float = Field(description="Tiền LLM đã tiêu từ đầu tháng (UTC).")
    max_requests_per_min: int = Field(description=_KHONG_GIOI_HAN)
    max_requests_per_day: int = Field(description=_KHONG_GIOI_HAN)
    monthly_budget_usd: float = Field(description=_KHONG_GIOI_HAN)
