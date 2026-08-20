"""Dựng một giọng cho thư viện: chuẩn hoá -> gõ chữ -> cổng chất lượng -> đọc thử.

Chạy qua Celery vì cả chuỗi mất vài chục giây (riêng Whisper đã vài giây),
quá xa mức 2 giây mà endpoint được phép chờ.

Test ở đây khoá phần ĐIỀU PHỐI: gọi đúng thứ tự, hỏng thì đánh dấu HONG chứ
không để giọng treo ở DANG_XU_LY mãi. Phần ffmpeg và Whisper là đối tượng
giả — chúng thuộc diện kiểm tay bằng script theo CLAUDE.md.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.giong import CanhBao, DoAmThanh

from src.tasks.giong import chon_duong_mau, dung_giong


class DbGia:
    def __init__(self, row):
        self.row = row

    def get(self, _model, _id):
        return self.row


@pytest.fixture
def giong():
    return SimpleNamespace(
        id=uuid.uuid4(),
        ten="Giọng thử",
        nguon=NguonGiong.TU_THU.value,
        nha_cung_cap="fish_mlx",
        ma_giong=None,
        model=None,
        mau_text=None,
        trang_thai=TrangThaiGiong.DANG_XU_LY.value,
        canh_bao=[],
        cat_tu_giay=None,
        cat_den_giay=None,
    )


def test_tam_tu_may_dung_bang_edge_con_lai_dung_file_tai_len() -> None:
    assert chon_duong_mau(NguonGiong.TAM_TU_MAY.value) == "edge"
    for n in (NguonGiong.TU_THU, NguonGiong.CAT_TU_FILE, NguonGiong.THUE_DOC):
        assert chon_duong_mau(n.value) == "tai_len"


def test_chay_du_bon_buoc_va_danh_dau_san_sang(giong, monkeypatch) -> None:
    da_goi = []
    #: Giả lập luôn chỗ tìm file gốc: ``dung_giong`` tra file TRƯỚC khi gọi
    #: ``chuan_hoa``, không giả lập là nó chạm hệ thống file thật và hỏng
    #: trước khi tới phần cần test.
    monkeypatch.setattr("src.tasks.giong._nguon_am_thanh", lambda _g: Path("/tmp/gia.wav"))
    monkeypatch.setattr(
        "src.tasks.giong.chuan_hoa",
        lambda *a, **k: (da_goi.append("chuan_hoa"), DoAmThanh(11.0, 0.12, 0.6, 0.05))[1],
    )
    monkeypatch.setattr(
        "src.tasks.giong.transcribe",
        lambda *a, **k: (da_goi.append("transcribe"), [SimpleNamespace(text="Xin chào các bạn")])[
            1
        ],
    )
    monkeypatch.setattr("src.tasks.giong.doc_thu", lambda *a, **k: da_goi.append("doc_thu"))

    dung_giong(DbGia(giong), giong.id)

    assert da_goi == ["chuan_hoa", "transcribe", "doc_thu"]
    assert giong.trang_thai == TrangThaiGiong.SAN_SANG.value
    assert giong.mau_text == "Xin chào các bạn"
    assert giong.canh_bao == []
    #: Đo rồi phải LƯU. Thẻ giọng hiện độ dài để so nhanh giữa các giọng —
    #: đo mà vứt thì mọi thẻ đều trống một ô, không ai biết vì sao.
    assert giong.do_dai_giay == 11.0
    #: Nhà cung cấp THẬT SỰ đã dựng file nghe thử.
    assert giong.nghe_thu_bang == "fish_mlx"


def test_canh_bao_duoc_luu_lai_nhung_KHONG_chan(giong, monkeypatch) -> None:
    #: Cảnh báo chứ không chặn — người dùng có thể cố tình dùng mẫu lạ. Nhưng
    #: phải nói ra, không để họ phát hiện sau khi lồng tiếng cả video.
    #: Giả lập luôn chỗ tìm file gốc: ``dung_giong`` tra file TRƯỚC khi gọi
    #: ``chuan_hoa``, không giả lập là nó chạm hệ thống file thật và hỏng
    #: trước khi tới phần cần test.
    monkeypatch.setattr("src.tasks.giong._nguon_am_thanh", lambda _g: Path("/tmp/gia.wav"))
    monkeypatch.setattr("src.tasks.giong._nguon_am_thanh", lambda _g: Path("/tmp/gia.wav"))
    monkeypatch.setattr(
        "src.tasks.giong.chuan_hoa", lambda *a, **k: DoAmThanh(3.0, 0.005, 0.99, 0.6)
    )
    monkeypatch.setattr(
        "src.tasks.giong.transcribe", lambda *a, **k: [SimpleNamespace(text="ngắn")]
    )
    monkeypatch.setattr("src.tasks.giong.doc_thu", lambda *a, **k: None)

    dung_giong(DbGia(giong), giong.id)

    assert giong.trang_thai == TrangThaiGiong.SAN_SANG.value
    ma = {c["ma"] for c in giong.canh_bao}
    assert {"qua_ngan", "vo_tieng", "qua_nho", "nhieu_im_lang"} <= ma


def test_hong_thi_danh_dau_HONG_chu_khong_treo(giong, monkeypatch) -> None:
    #: Giả lập luôn chỗ tìm file gốc: ``dung_giong`` tra file TRƯỚC khi gọi
    #: ``chuan_hoa``, không giả lập là nó chạm hệ thống file thật và hỏng
    #: trước khi tới phần cần test.
    monkeypatch.setattr("src.tasks.giong._nguon_am_thanh", lambda _g: Path("/tmp/gia.wav"))
    monkeypatch.setattr(
        "src.tasks.giong.chuan_hoa",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ffmpeg chết")),
    )
    with pytest.raises(RuntimeError):
        dung_giong(DbGia(giong), giong.id)
    assert giong.trang_thai == TrangThaiGiong.HONG.value
    assert "ffmpeg chết" in giong.loi


def test_whisper_gõ_ra_rong_thi_bao_hong(giong, monkeypatch) -> None:
    #: Không có phần chữ thì nhân bản giọng không chạy được — Fish cần CẢ
    #: audio lẫn transcript khớp từng chữ.
    monkeypatch.setattr("src.tasks.giong._nguon_am_thanh", lambda _g: Path("/tmp/gia.wav"))
    monkeypatch.setattr("src.tasks.giong.chuan_hoa", lambda *a, **k: DoAmThanh(11.0, 0.1, 0.5, 0.0))
    monkeypatch.setattr("src.tasks.giong.transcribe", lambda *a, **k: [])
    monkeypatch.setattr("src.tasks.giong.doc_thu", lambda *a, **k: None)

    with pytest.raises(Exception, match="không nghe ra chữ nào"):
        dung_giong(DbGia(giong), giong.id)
    assert giong.trang_thai == TrangThaiGiong.HONG.value
