"""Lọc model theo mục đích — không phải model nào cũng dùng để dịch.

Key Gemini của dự án trả về hơn 50 model gồm cả sinh ảnh, sinh video, nhúng
vector, điều khiển máy tính. Đổ hết vào ô chọn "AI dịch" thì người dùng chọn
nhầm `veo-3.1-generate` rồi ngồi đoán vì sao hỏng.

Hạn mức thật của dự án (đọc ở aistudio.google.com/rate-limit, ngày 2026-08-14)
cho thấy vì sao việc lọc quan trọng tới mức đó:

- `gemini-3.6-flash`      —  5 lượt/phút ·  20 lượt/NGÀY
- `gemini-3.5-flash-lite` — 15 lượt/phút · 500 lượt/ngày
- `gemini-2.5-flash-tts`  —  3 lượt/phút ·  10 lượt/ngày

Dịch một video 34 phút cần 7 lượt (lô 100 câu). Chọn nhầm bản `flash` thay vì
`flash-lite` là mất 25 lần hạn mức ngày.
"""

from __future__ import annotations

import pytest
from reup_core.llm_models import ModelPurpose, loc_theo_muc_dich, phan_loai

# ID thật lấy từ API bằng key của dự án, không phải bịa.
DICH = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemma-4-31b",
]
TTS = [
    "gemini-2.5-flash-tts",
    "gemini-3.1-flash-tts",
    "gemini-2.5-pro-tts",
]
KHAC = [
    "imagen-4.0-generate-001",
    "gemini-3.1-flash-image-preview",
    "veo-3.1-generate-preview",
    "lyria-3-pro-preview",
    "gemini-embedding-001",
    "gemini-2.5-computer-use-preview-10-2025",
    "deep-research-pro-preview-12-2025",
    "gemini-2.5-flash-native-audio-latest",
    "gemini-3.5-live-translate-preview",
]


@pytest.mark.parametrize("model_id", DICH)
def test_nhan_dien_model_dich(model_id: str) -> None:
    assert phan_loai(model_id) is ModelPurpose.TRANSLATE


@pytest.mark.parametrize("model_id", TTS)
def test_nhan_dien_model_giong_noi(model_id: str) -> None:
    assert phan_loai(model_id) is ModelPurpose.TTS


@pytest.mark.parametrize("model_id", KHAC)
def test_loai_bo_model_khong_dung_de_dich(model_id: str) -> None:
    assert phan_loai(model_id) is ModelPurpose.OTHER


def test_tts_khong_bi_nham_thanh_dich() -> None:
    """``gemini-2.5-flash-tts`` chứa cả chữ "flash" — thứ tự kiểm phải đặt TTS
    TRƯỚC, nếu không nó lọt vào danh sách dịch và người dùng chọn phải model
    chỉ có 10 lượt/ngày."""
    assert phan_loai("gemini-2.5-flash-tts") is not ModelPurpose.TRANSLATE


def test_live_translate_khong_phai_model_dich_theo_lo() -> None:
    """``gemini-3.5-live-translate`` nghe như để dịch nhưng là Live API —
    dịch thời gian thực theo luồng, không nhận lô văn bản như ta cần."""
    assert phan_loai("gemini-3.5-live-translate-preview") is ModelPurpose.OTHER


def test_loc_giu_nguyen_thu_tu_dau_vao() -> None:
    ids = ["veo-3.1-generate-preview", "gemini-3.5-flash-lite", "gemini-2.5-flash-tts"]
    assert loc_theo_muc_dich(ids, ModelPurpose.TRANSLATE) == ["gemini-3.5-flash-lite"]
    assert loc_theo_muc_dich(ids, ModelPurpose.TTS) == ["gemini-2.5-flash-tts"]


def test_bo_tien_to_models_cua_gemini() -> None:
    """API Gemini trả ``models/gemini-...``; phần đầu đó không phải tên model."""
    assert phan_loai("models/gemini-3.5-flash-lite") is ModelPurpose.TRANSLATE


def test_model_la_hoan_toan_thi_xep_vao_khac() -> None:
    """Không đoán bừa: tên lạ thì KHÔNG mời người dùng chọn để dịch."""
    assert phan_loai("mo-hinh-la-hoac-toan") is ModelPurpose.OTHER


def test_model_hieu_video_khong_phai_model_dich() -> None:
    """``gemini-3.7-flash-video-understanding`` có chữ "flash" nhưng nhận VIDEO
    làm đầu vào, không phải mô hình dịch văn bản theo lô.

    Lọt lưới lần đầu, phát hiện khi đối chiếu bộ lọc với danh sách thật do API
    trả về — đó là lý do phải kiểm bằng dữ liệu thật chứ không chỉ bằng ví dụ
    tự nghĩ ra.
    """
    assert phan_loai("gemini-3.7-flash-video-understanding-eap") is ModelPurpose.OTHER


#: OpenRouter đặt tên theo ``hãng/model``. Mã cũ neo ``^`` vào cả chuỗi nên
#: 319 trên 413 model bị giấu đi (đếm ngày 2026-08-16) — kể cả ``google/gemini``
#: và toàn bộ model miễn phí. Người dùng chọn OpenRouter chỉ thấy một phần tư
#: danh mục mà không hiểu vì sao.
OPENROUTER_DICH = [
    "google/gemini-3.7-flash",
    "google/gemma-4-31b-it:free",
    "anthropic/claude-sonnet-5",
    "meta-llama/llama-4-maverick",
    "openai/gpt-oss-20b:free",
    "x-ai/grok-4.6",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "deepseek/deepseek-v3.2",
    "qwen/qwen3-max",
    "mistralai/mistral-large-2512",
]

OPENROUTER_KHAC = [
    "google/gemini-3-pro-image",
    "google/lyria-3-pro-preview",
    "openai/gpt-5.4-image-2",
]


@pytest.mark.parametrize("model_id", OPENROUTER_DICH)
def test_bo_tien_to_hang_cua_openrouter(model_id: str) -> None:
    assert phan_loai(model_id) is ModelPurpose.TRANSLATE


@pytest.mark.parametrize("model_id", OPENROUTER_KHAC)
def test_model_sinh_anh_cua_openrouter_van_bi_loai(model_id: str) -> None:
    """Bỏ tiền tố hãng KHÔNG được làm lọt model sinh ảnh vào danh sách dịch."""
    assert phan_loai(model_id) is ModelPurpose.OTHER


def test_ten_la_van_khong_duoc_doan_bua() -> None:
    """Bỏ tiền tố hãng không có nghĩa là nhận bừa mọi thứ có dấu gạch chéo."""
    assert phan_loai("hang-la/mo-hinh-khong-ai-biet") is ModelPurpose.OTHER
