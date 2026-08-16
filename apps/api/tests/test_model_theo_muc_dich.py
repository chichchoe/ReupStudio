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
from reup_core.ai_providers import ModelInfo

from src.services import ai_provider_service


@pytest.fixture
def khong_goi_mang(monkeypatch):
    """Đứng ngoài mạng: chỉ kiểm phần lọc, không kiểm OpenRouter."""
    danh_sach = [
        ModelInfo(ma="google/gemini-3.7-flash", dau_ra=["text"]),
        ModelInfo(ma="anthropic/claude-sonnet-5", dau_ra=["text"]),
        ModelInfo(ma="google/gemini-3-pro-image", dau_ra=["image"]),
    ]
    monkeypatch.setattr(ai_provider_service, "hoi_model_chi_tiet", lambda *a, **k: danh_sach)
    monkeypatch.setattr(ai_provider_service, "lay_khoa", lambda db, ma: "khoa-gia")
    return danh_sach


def test_hoi_tts_ma_khong_co_thi_tra_rong(khong_goi_mang, monkeypatch) -> None:
    """KHÔNG được lấy model văn bản ra làm giọng đọc."""
    ra = ai_provider_service.models(_db_gia(monkeypatch), "openrouter", "tts")

    assert ra == []


def test_model_khai_sinh_ra_audio_thi_xep_vao_tts(monkeypatch) -> None:
    """`openai/gpt-audio` đọc thành tiếng THẬT mà trong tên không có chữ "tts".

    Chỉ soi tên thì kết luận OpenRouter có 0 model đọc tiếng — sai. Nhà cung
    cấp khai `output_modalities: [text, audio]`, phải tin cái khai đó.
    """
    ds = [
        ModelInfo(ma="openai/gpt-audio", dau_ra=["text", "audio"]),
        ModelInfo(ma="google/gemini-3.7-flash", dau_ra=["text"]),
    ]
    monkeypatch.setattr(ai_provider_service, "hoi_model_chi_tiet", lambda *a, **k: ds)
    monkeypatch.setattr(ai_provider_service, "lay_khoa", lambda db, ma: "khoa-gia")

    assert ai_provider_service.models(_db_gia(monkeypatch), "openrouter", "tts") == [
        "openai/gpt-audio"
    ]


def test_model_sinh_NHAC_khong_bi_nham_thanh_giong_doc(monkeypatch) -> None:
    """`lyria` cũng khai sinh ra audio, nhưng là NHẠC — lồng tiếng bằng nhạc
    nền thì còn tệ hơn không lồng."""
    ds = [ModelInfo(ma="google/lyria-3-pro-preview", dau_ra=["text", "audio"])]
    monkeypatch.setattr(ai_provider_service, "hoi_model_chi_tiet", lambda *a, **k: ds)
    monkeypatch.setattr(ai_provider_service, "lay_khoa", lambda db, ma: "khoa-gia")

    assert ai_provider_service.models(_db_gia(monkeypatch), "openrouter", "tts") == []


def test_hoi_dich_thi_loc_bo_model_sinh_anh(khong_goi_mang, monkeypatch) -> None:
    ra = ai_provider_service.models(_db_gia(monkeypatch), "openrouter", "translate")

    assert "google/gemini-3.7-flash" in ra
    assert "anthropic/claude-sonnet-5" in ra
    assert "google/gemini-3-pro-image" not in ra


def test_dich_khong_loc_ra_gi_thi_van_tra_nguyen_danh_sach(monkeypatch) -> None:
    """Đường lui của DỊCH phải giữ: tên lạ thường vẫn dịch được."""
    la = [
        ModelInfo(ma="hang-la/mo-hinh-khong-ai-biet", dau_ra=[]),
        ModelInfo(ma="hang-la/mo-hinh-khac", dau_ra=[]),
    ]
    monkeypatch.setattr(ai_provider_service, "hoi_model_chi_tiet", lambda *a, **k: la)
    monkeypatch.setattr(ai_provider_service, "lay_khoa", lambda db, ma: "khoa-gia")

    assert ai_provider_service.models(_db_gia(monkeypatch), "openrouter", "translate") == [
        m.ma for m in la
    ]


def _db_gia(monkeypatch):
    """Session giả: chỉ cần ``get`` trả None (chưa lưu cấu hình nhà cung cấp)."""

    class DbGia:
        def get(self, *a, **k):
            return None

    return DbGia()
