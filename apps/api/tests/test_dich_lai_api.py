"""Dịch lại: chỉ cho phép khi video đang ở chỗ dừng duyệt.

Cho dịch lại lúc pipeline đang chạy là hai tiến trình cùng ghi vào một dòng
phụ đề — bên nào ghi sau thắng, và không ai biết mình mất bản nào.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from reup_core.enums import VideoStatus

from src.errors import ApiError
from src.services import video_service


class DbGia:
    def __init__(self, video):
        self._video = video

    def get(self, _model, _id):
        return self._video


def _video(status=VideoStatus.REVIEW.value, cho_duyet=True):
    return SimpleNamespace(
        id=uuid.uuid4(),
        deleted_at=None,
        status=status,
        flags={"cho_duyet_ban_dich": cho_duyet},
        process_config={},
    )


def test_dat_chi_so_vao_process_config() -> None:
    v = _video()
    video_service.kiem_truoc_khi_dich_lai(DbGia(v), v.id, [3, 7], "openrouter", "model-x")
    assert v.process_config["dich_lai_chi_so"] == [3, 7]
    assert v.process_config["llm_model"] == "model-x"
    assert v.process_config["llm_provider_ma"] == "openrouter"


def test_khong_truyen_chi_so_nghia_la_toan_bo() -> None:
    v = _video()
    video_service.kiem_truoc_khi_dich_lai(DbGia(v), v.id, None, None, None)
    assert v.process_config["dich_lai_chi_so"] == []


def test_giu_model_cu_khi_khong_chon_lai() -> None:
    #: Bấm "dịch lại mấy câu này" thường là muốn đúng model cũ, không phải
    #: rơi về mặc định.
    v = _video()
    v.process_config = {"llm_model": "model-cu", "llm_provider_ma": "gemini"}
    video_service.kiem_truoc_khi_dich_lai(DbGia(v), v.id, None, None, None)
    assert v.process_config["llm_model"] == "model-cu"
    assert v.process_config["llm_provider_ma"] == "gemini"


def test_tu_choi_khi_video_dang_chay() -> None:
    v = _video(status=VideoStatus.RUNNING.value)
    with pytest.raises(ApiError, match="đang chờ duyệt"):
        video_service.kiem_truoc_khi_dich_lai(DbGia(v), v.id, None, None, None)


def test_tu_choi_khi_chua_toi_cho_duyet_ban_dich() -> None:
    #: Trạng thái review nhưng chưa dịch lần nào — chưa có gì để dịch LẠI.
    v = _video(cho_duyet=False)
    with pytest.raises(ApiError, match="chưa dịch"):
        video_service.kiem_truoc_khi_dich_lai(DbGia(v), v.id, None, None, None)
