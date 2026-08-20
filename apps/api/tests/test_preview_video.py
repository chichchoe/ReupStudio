"""Video nguồn để xem TRƯỚC khi render.

Tách khỏi ``/file`` chứ không dùng chung: ``/file`` mang nghĩa "bản render
cuối". Trộn hai thứ vào một đường là mở cửa cho lỗi xem nhầm bản — người dùng
tưởng đang xem bản đã dựng trong khi đó là bản gốc.

Ưu tiên proxy 540p (tua nhanh, 6–22 MB) và chỉ rơi về bản gốc khi thiếu.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.errors import NotFound
from src.services import video_service


@pytest.fixture
def video():
    return SimpleNamespace(
        id=uuid.uuid4(),
        deleted_at=None,
        source_platform="douyin",
        source_video_id="7300000000000000000",
    )


class DbGia:
    def __init__(self, video):
        self._video = video

    def get(self, _model, _id):
        return self._video


def test_uu_tien_proxy_khi_co(monkeypatch, tmp_path, video) -> None:
    proxy = tmp_path / "proxy.mp4"
    proxy.write_bytes(b"x" * 100)
    monkeypatch.setattr(video_service, "proxy_path", lambda _vid: proxy)
    monkeypatch.setattr(video_service, "raw_video", lambda _p, _s: tmp_path / "khong-dung.mp4")

    assert video_service.duong_dan_xem_truoc(DbGia(video), video.id) == proxy


def test_roi_ve_ban_goc_khi_thieu_proxy(monkeypatch, tmp_path, video) -> None:
    goc = tmp_path / "source.mp4"
    goc.write_bytes(b"x" * 100)
    monkeypatch.setattr(video_service, "proxy_path", lambda _vid: tmp_path / "khong-ton-tai.mp4")
    monkeypatch.setattr(video_service, "raw_video", lambda _p, _s: goc)

    assert video_service.duong_dan_xem_truoc(DbGia(video), video.id) == goc


def test_proxy_RONG_tinh_la_khong_co(monkeypatch, tmp_path, video) -> None:
    #: Ghi dở rồi crash để lại file 0 byte. Coi là hợp lệ thì trình duyệt
    #: nhận về video trắng và không ai biết vì sao.
    rong = tmp_path / "proxy.mp4"
    rong.write_bytes(b"")
    goc = tmp_path / "source.mp4"
    goc.write_bytes(b"x" * 100)
    monkeypatch.setattr(video_service, "proxy_path", lambda _vid: rong)
    monkeypatch.setattr(video_service, "raw_video", lambda _p, _s: goc)

    assert video_service.duong_dan_xem_truoc(DbGia(video), video.id) == goc


def test_khong_con_file_nao_thi_bao_ro(monkeypatch, tmp_path, video) -> None:
    monkeypatch.setattr(video_service, "proxy_path", lambda _vid: tmp_path / "a.mp4")
    monkeypatch.setattr(video_service, "raw_video", lambda _p, _s: tmp_path / "b.mp4")

    with pytest.raises(NotFound, match="chưa tải xong"):
        video_service.duong_dan_xem_truoc(DbGia(video), video.id)
