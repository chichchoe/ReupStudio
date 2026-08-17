"""Sửa bản dịch tay: chỉ nhận CHỮ, và không được làm hụt câu.

Người dùng đọc bảng đối chiếu Trung–Việt, thấy chỗ dịch chưa sát thì sửa thẳng
vào ô. Ba thứ phải giữ:

- Mốc thời gian KHÔNG cho đổi: giờ giấc do bước nhận dạng và bước chuẩn hoá
  phụ đề tính ra; cho sửa là mở đường cho phụ đề chồng lên nhau.
- Câu không gửi lên thì giữ nguyên — giao diện chỉ gửi phần đã sửa.
- `edited_by_user` phải bật, nếu không worker chạy lại sẽ ghi đè công vừa sửa.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from reup_core.enums import VideoStatus

from src.errors import ApiError
from src.services import video_service

#: Không có fixture database trong bộ test này — cả apps/api chạy bằng hàm
#: thuần và đối tượng giả. Dựng một session giả đủ ba thứ ``sua_ban_dich``
#: dùng: ``get`` lấy video, ``scalar`` lấy dòng phụ đề, ``flush`` không làm gì.


class DbGia:
    def __init__(self, video, phu_de):
        self._video = video
        self._phu_de = phu_de

    def get(self, _model, _id):
        return self._video

    def scalar(self, _stmt):
        return self._phu_de

    def flush(self):
        pass


@pytest.fixture
def video_cho_duyet():
    video = SimpleNamespace(
        id=uuid.uuid4(),
        deleted_at=None,
        status=VideoStatus.REVIEW.value,
        flags={"cho_duyet_ban_dich": True},
    )
    phu_de = SimpleNamespace(
        lang="vi",
        edited_by_user=False,
        cues=[
            {"i": 0, "start": 0.0, "end": 1.3, "text": "Câu một"},
            {"i": 1, "start": 1.3, "end": 2.6, "text": "Câu hai"},
            {"i": 2, "start": 2.6, "end": 4.1, "text": "Câu ba"},
        ],
    )
    return video, DbGia(video, phu_de)


def test_sua_mot_cau_giu_nguyen_cac_cau_khac(video_cho_duyet) -> None:
    video, db = video_cho_duyet
    row = video_service.sua_ban_dich(db, video.id, [{"i": 1, "text": "Câu hai đã sửa"}])

    assert [c["text"] for c in row.cues] == ["Câu một", "Câu hai đã sửa", "Câu ba"]


def test_moc_thoi_gian_khong_doi(video_cho_duyet) -> None:
    video, db = video_cho_duyet
    """Người dùng sửa CHỮ, không nắn nhịp."""
    row = video_service.sua_ban_dich(
        db, video.id, [{"i": 0, "text": "Chữ mới", "start": 99.0, "end": 100.0}]
    )

    assert row.cues[0]["start"] == 0.0
    assert row.cues[0]["end"] == 1.3


def test_bat_co_da_sua_de_worker_khong_ghi_de(video_cho_duyet) -> None:
    video, db = video_cho_duyet
    row = video_service.sua_ban_dich(db, video.id, [{"i": 0, "text": "x"}])

    assert row.edited_by_user is True


def test_de_trong_mot_cau_thi_tu_choi(video_cho_duyet) -> None:
    video, db = video_cho_duyet
    """Xoá câu thì phụ đề hụt một đoạn mà không ai thấy cho tới lúc xem lại."""
    with pytest.raises(ApiError, match="để trống"):
        video_service.sua_ban_dich(db, video.id, [{"i": 0, "text": "   "}])


def test_cau_khong_co_that_thi_tu_choi(video_cho_duyet) -> None:
    video, db = video_cho_duyet
    with pytest.raises(ApiError, match="câu số 99"):
        video_service.sua_ban_dich(db, video.id, [{"i": 99, "text": "x"}])


def test_video_dang_chay_thi_khong_cho_sua(video_cho_duyet) -> None:
    video, db = video_cho_duyet
    """Sửa giữa lúc worker đang đọc là hai bên giẫm lên nhau."""
    video.status = VideoStatus.RUNNING.value

    with pytest.raises(ApiError, match="chờ duyệt"):
        video_service.sua_ban_dich(db, video.id, [{"i": 0, "text": "x"}])
