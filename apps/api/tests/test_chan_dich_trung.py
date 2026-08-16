"""Bấm Dịch hay Duyệt hai lần không được sinh hai chuỗi task.

Quan sát ngày 2026-08-16: video đã duyệt xong bị một chuỗi dịch tới sau kéo
NGƯỢC về ``review``, người dùng thấy "dịch xong lại quay về chờ dịch". Nguyên
nhân: ``request_translate`` nhận mọi lời gọi, nên bốn lần bấm Dịch thành bốn
chuỗi đầy đủ chạy chồng lên nhau — đốt bốn lần hạn mức LLM luôn.
"""

from __future__ import annotations

import pytest
from reup_core.enums import VideoStatus
from reup_core.llm_models import chac_chan_khong_dich_duoc

from src.errors import ApiError
from src.services import video_service


class VideoGia:
    def __init__(self, status: str, flags: dict | None = None):
        self.status = status
        self.flags = flags or {}


def test_dang_chay_thi_khong_cho_dich_lai() -> None:
    with pytest.raises(ApiError, match="đang xử lý"):
        video_service._chan_dich_trung(VideoGia(VideoStatus.RUNNING.value))


def test_da_xep_hang_thi_khong_cho_dich_lai() -> None:
    with pytest.raises(ApiError, match="đang xử lý"):
        video_service._chan_dich_trung(VideoGia(VideoStatus.QUEUED.value))


def test_dich_xong_roi_thi_bao_sang_tab_cho_duyet() -> None:
    video = VideoGia(VideoStatus.REVIEW.value, {"cho_duyet_ban_dich": True})
    with pytest.raises(ApiError, match="Chờ duyệt"):
        video_service._chan_dich_trung(video)


def test_dang_cho_dich_thi_cho_qua() -> None:
    video_service._chan_dich_trung(VideoGia(VideoStatus.REVIEW.value))


def test_da_dung_xong_thi_bao_bam_thu_lai() -> None:
    with pytest.raises(ApiError, match="Thử lại"):
        video_service._chan_dich_trung(VideoGia(VideoStatus.READY.value))


def test_loi_thi_van_cho_chay_lai() -> None:
    """Đó chính là nút Thử lại."""
    video_service._chan_dich_trung(VideoGia(VideoStatus.ERROR.value))


#: Hai câu hỏi khác nhau, trước đây trả lời bằng cùng một hàm nên sinh ra lỗi:
#: danh sách chọn dựng từ `output_modalities` (397 model), còn chỗ chặn lại
#: đoán theo tên nên từ chối 68 trong số đó. Người dùng chọn xong bấm Dịch là
#: ăn "Model ... không dùng để dịch được".
KHONG_DICH_DUOC = [
    "gemini-2.5-flash-tts",
    "openai/gpt-audio",
    "google/gemini-3-pro-image",
    "google/veo-3.1-generate-preview",
    "gemini-embedding-001",
]

TEN_LA_NHUNG_VAN_PHAI_CHO_QUA = [
    "aion-labs/aion-2.0",
    "arcee-ai/virtuoso-large",
    "dots-studio/dots-3-note-preview:free",
    "cohere/north-mini-code:free",
]


@pytest.mark.parametrize("model_id", KHONG_DICH_DUOC)
def test_chan_model_chac_chan_sai(model_id: str) -> None:
    assert chac_chan_khong_dich_duoc(model_id) is True


@pytest.mark.parametrize("model_id", TEN_LA_NHUNG_VAN_PHAI_CHO_QUA)
def test_khong_chan_model_chi_vi_ten_la(model_id: str) -> None:
    """Chặn nhầm = mời người dùng chọn rồi từ chối chính cái vừa mời."""
    assert chac_chan_khong_dich_duoc(model_id) is False
