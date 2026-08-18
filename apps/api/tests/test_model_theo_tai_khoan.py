"""Ô chọn model chỉ được mời model TÀI KHOẢN dùng được, không phải cả danh mục.

Quan sát ngày 17.08.2026 — lý do bài test này tồn tại. Tab "Chờ dịch" mời chọn
model, chọn cái nào bấm Dịch cũng ăn 404:

    No endpoints available matching your guardrail restrictions and data policy

Gọi thật bằng đúng khoá đang lưu thì thấy rõ:

======================== ========== =========================
model                    gọi thật   có trong ``/models/user``
======================== ========== =========================
google/gemini-3.7-flash  200 OK     có
openai/gpt-4.1-nano      404        không
deepseek/deepseek-v4-pro 404        không
======================== ========== =========================

``GET /api/v1/models`` của OpenRouter trả **cả danh mục công khai** — 414 model,
không xét khoá nào. ``GET /api/v1/models/user`` trả **56** model mà thiết lập
quyền riêng tư của tài khoản cho phép. Hỏi đường thứ nhất thì 86% lựa chọn
trong ô chắc chắn hỏng, và người dùng chỉ biết SAU khi đã tải + nhận dạng xong
cả video rồi bấm Dịch.

Đây đúng thứ ``ai_provider_service.models`` sinh ra để tránh: "hỏi thẳng nhà
cung cấp xem khoá NÀY dùng được model nào".
"""

from __future__ import annotations

from reup_core.ai_providers import DANH_MUC


def test_openrouter_hoi_danh_sach_theo_tai_khoan() -> None:
    """OpenRouter phải hỏi ``/models/user``, không phải ``/models``."""
    assert DANH_MUC["openrouter"].duong_dan_models == "/models/user"


def test_ben_khac_van_hoi_models_nhu_cu() -> None:
    """Chỉ OpenRouter có đường riêng — đừng đổi bên khác theo.

    ``/models/user`` là đường của OpenRouter; Gemini và Anthropic không có nó,
    đổi theo là mọi bên khác ăn 404 ngay ở chỗ đổ ô chọn.
    """
    for ma, nha in DANH_MUC.items():
        if ma != "openrouter":
            assert nha.duong_dan_models == "/models", ma
