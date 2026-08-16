"""Hỏi model cho việc nào thì phải trả model làm được việc ĐÓ.

Quan sát ngày 2026-08-16: hỏi model TTS của OpenRouter, endpoint trả về đủ 413
model — trong khi OpenRouter không có model TTS nào. Nguyên nhân: đường lui
"lọc rỗng thì trả nguyên danh sách" dùng chung cho cả hai việc.

Đường lui đó ĐÚNG cho dịch (model văn bản lạ thường vẫn dịch được) nhưng SAI
cho giọng đọc: một model văn bản không bao giờ đọc thành tiếng được, nên nó
biến "bên này không có TTS" thành "đây, 413 giọng cho bạn chọn".
"""

from __future__ import annotations

import pytest

from src.services import ai_provider_service


@pytest.fixture
def khong_goi_mang(monkeypatch):
    """Đứng ngoài mạng: chỉ kiểm phần lọc, không kiểm OpenRouter."""
    danh_sach = [
        "google/gemini-3.7-flash",
        "anthropic/claude-sonnet-5",
        "google/gemini-3-pro-image",
    ]
    monkeypatch.setattr(ai_provider_service, "hoi_danh_sach_model", lambda *a, **k: danh_sach)
    monkeypatch.setattr(ai_provider_service, "lay_khoa", lambda db, ma: "khoa-gia")
    return danh_sach


def test_hoi_tts_ma_khong_co_thi_tra_rong(khong_goi_mang, monkeypatch) -> None:
    """KHÔNG được lấy model văn bản ra làm giọng đọc."""
    ra = ai_provider_service.models(_db_gia(monkeypatch), "openrouter", "tts")

    assert ra == []


def test_hoi_dich_thi_loc_bo_model_sinh_anh(khong_goi_mang, monkeypatch) -> None:
    ra = ai_provider_service.models(_db_gia(monkeypatch), "openrouter", "translate")

    assert "google/gemini-3.7-flash" in ra
    assert "anthropic/claude-sonnet-5" in ra
    assert "google/gemini-3-pro-image" not in ra


def test_dich_khong_loc_ra_gi_thi_van_tra_nguyen_danh_sach(monkeypatch) -> None:
    """Đường lui của DỊCH phải giữ: tên lạ thường vẫn dịch được."""
    la = ["hang-la/mo-hinh-khong-ai-biet", "hang-la/mo-hinh-khac"]
    monkeypatch.setattr(ai_provider_service, "hoi_danh_sach_model", lambda *a, **k: la)
    monkeypatch.setattr(ai_provider_service, "lay_khoa", lambda db, ma: "khoa-gia")

    assert ai_provider_service.models(_db_gia(monkeypatch), "openrouter", "translate") == la


def _db_gia(monkeypatch):
    """Session giả: chỉ cần ``get`` trả None (chưa lưu cấu hình nhà cung cấp)."""

    class DbGia:
        def get(self, *a, **k):
            return None

    return DbGia()
