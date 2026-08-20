"""Bảng đối chiếu Trung–Việt cho màn duyệt.

Ghép ở BACKEND chứ không để React tự ghép: đây là logic nghiệp vụ đã có test,
và giao diện không nên phải biết vì sao không ghép được theo chỉ số.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.errors import NotFound
from src.services import video_service


class DbGia:
    def __init__(self, video, rows):
        self._video = video
        self._rows = rows

    def get(self, _model, _id):
        return self._video

    def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: self._rows)


@pytest.fixture
def video():
    return SimpleNamespace(id=uuid.uuid4(), deleted_at=None)


def _sub(lang, cues):
    return SimpleNamespace(lang=lang, cues=cues)


def test_ghep_dung_cau_khi_lech_so_dong(video) -> None:
    #: 1 câu Trung dài -> 2 câu Việt sau khi tách. Ghép theo chỉ số sẽ để câu
    #: Việt thứ hai không có gốc.
    vi = _sub(
        "vi",
        [
            {"i": 0, "start": 0.0, "end": 1.5, "text": "Nửa đầu"},
            {"i": 1, "start": 1.5, "end": 3.0, "text": "nửa sau"},
        ],
    )
    zh = _sub("zh", [{"i": 0, "start": 0.0, "end": 3.0, "text": "一句很长的话"}])
    ra = video_service.doi_chieu(DbGia(video, [vi, zh]), video.id)
    assert [r["goc"] for r in ra] == ["一句很长的话", "一句很长的话"]


def test_bao_co_sua_tay(video) -> None:
    vi = _sub(
        "vi",
        [
            {"i": 0, "start": 0.0, "end": 1.0, "text": "Đã sửa", "sua_tay": True},
            {"i": 1, "start": 1.0, "end": 2.0, "text": "Chưa sửa"},
        ],
    )
    ra = video_service.doi_chieu(DbGia(video, [vi, _sub("zh", [])]), video.id)
    assert [r["sua_tay"] for r in ra] == [True, False]


def test_chua_dich_thi_tra_cau_GOC_de_xem_truoc(video) -> None:
    """Chỗ dừng thứ nhất chưa có bản dịch, nhưng vẫn phải xem được bản gốc.

    Đó chính là điểm của chỗ dừng này: xem rồi mới quyết định có dịch không và
    chọn model nào. Ném lỗi ở đây là bắt người dùng bấm Dịch mù.
    """
    zh = _sub(
        "zh",
        [
            {"i": 0, "start": 0.0, "end": 1.0, "text": "你好"},
            {"i": 1, "start": 1.0, "end": 2.0, "text": "再见"},
        ],
    )
    ra = video_service.doi_chieu(DbGia(video, [zh]), video.id)
    assert [r["goc"] for r in ra] == ["你好", "再见"]
    assert [r["dich"] for r in ra] == ["", ""]


def test_khong_co_phu_de_nao_thi_bao_ro(video) -> None:
    with pytest.raises(NotFound, match="chưa có phụ đề"):
        video_service.doi_chieu(DbGia(video, []), video.id)


def test_khong_co_phu_de_goc_van_tra_ban_dich(video) -> None:
    #: Thiếu tiếng Trung không được làm hỏng cả bảng — vẫn đọc được bản dịch.
    vi = _sub("vi", [{"i": 0, "start": 0.0, "end": 1.0, "text": "Một mình"}])
    ra = video_service.doi_chieu(DbGia(video, [vi]), video.id)
    assert len(ra) == 1 and ra[0]["goc"] == "" and ra[0]["dich"] == "Một mình"
