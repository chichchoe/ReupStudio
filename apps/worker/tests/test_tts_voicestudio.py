"""Giọng đọc qua VoiceStudio chạy tại máy.

Dễ hơn hẳn OpenRouter vì nó mở đúng endpoint TTS chuẩn của OpenAI
(``POST /v1/audio/speech``, trả thẳng khối audio). Ba chỗ vẫn phải khoá:

1. Container chưa bật là chuyện thường ngày — lúc liệt kê giọng thì im lặng bỏ
   qua, nhưng lúc ĐỌC thì phải nói rõ cách bật, đừng ném ra `URLError`.
2. Máy chủ trả 200 kèm thân rỗng cũng là hỏng, chỉ là hỏng lặng lẽ hơn.
3. Lỗi 4xx (giọng không có, model sai tên) thì thử lại y hệt cũng hỏng y hệt.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from src.errors import ReupError
from src.tts import lay_provider
from src.tts.voicestudio import BASE_URL_MAC_DINH, VoiceStudioTTS


class TraLoiGia:
    def __init__(self, than: bytes) -> None:
        self._than = than

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self) -> bytes:
        return self._than


def test_gui_dung_hop_dong_openai(monkeypatch, tmp_path) -> None:
    """`/v1/audio/speech` với model, input, voice, response_format."""
    da_gui: dict = {}

    def gia_lap(req, timeout=0):
        da_gui["url"] = req.full_url
        da_gui["body"] = json.loads(req.data)
        return TraLoiGia(b"RIFFxxxxWAVE")

    monkeypatch.setattr("urllib.request.urlopen", gia_lap)
    VoiceStudioTTS().doc("Xin chào", tmp_path / "a.wav", giong="co-lan")

    assert da_gui["url"] == f"{BASE_URL_MAC_DINH}/audio/speech"
    assert da_gui["body"]["input"] == "Xin chào"
    assert da_gui["body"]["voice"] == "co-lan"
    assert da_gui["body"]["response_format"] == "wav"
    assert (tmp_path / "a.wav").read_bytes() == b"RIFFxxxxWAVE"


def test_chua_bat_container_thi_chi_cach_bat(monkeypatch, tmp_path) -> None:
    """Ném `URLError` trần ra thì người dùng chỉ thấy "Connection refused"."""

    def tu_choi(*a, **k):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", tu_choi)

    with pytest.raises(ReupError, match="docker compose"):
        VoiceStudioTTS().doc("Xin chào", tmp_path / "b.wav", giong="x")


def test_than_rong_van_la_hong(monkeypatch, tmp_path) -> None:
    """200 kèm 0 byte thì bước sau âm thầm bỏ qua câu này — phải kêu."""
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: TraLoiGia(b""))
    monkeypatch.setattr("time.sleep", lambda _s: None)

    with pytest.raises(ReupError, match="audio rỗng"):
        VoiceStudioTTS().doc("Xin chào", tmp_path / "c.wav", giong="x")


def test_loi_4xx_khong_thu_lai(monkeypatch, tmp_path) -> None:
    """Giọng không có hay model sai tên — thử lại y hệt cũng hỏng y hệt."""
    so_lan = {"n": 0}

    def sai_yeu_cau(*a, **k):
        so_lan["n"] += 1
        raise urllib.error.HTTPError("u", 422, "unprocessable", {}, io.BytesIO(b"khong co giong"))

    monkeypatch.setattr("urllib.request.urlopen", sai_yeu_cau)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    with pytest.raises(ReupError, match="từ chối"):
        VoiceStudioTTS().doc("Xin chào", tmp_path / "d.wav", giong="khong-co")

    assert so_lan["n"] == 1


def test_cau_rong_khong_goi_mang(monkeypatch, tmp_path) -> None:
    def cam_goi(*a, **k):
        raise AssertionError("không được gọi mạng cho câu rỗng")

    monkeypatch.setattr("urllib.request.urlopen", cam_goi)

    assert VoiceStudioTTS().doc("   ", tmp_path / "e.wav", giong="x").read_bytes() == b""


def test_liet_ke_giong_khi_chua_bat_thi_khong_lam_sap(monkeypatch) -> None:
    """Liệt kê giọng chỉ để hiện lên giao diện — làm sập cả trang vì một
    container chưa chạy là quá tay."""

    def tu_choi(*a, **k):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", tu_choi)
    giong = VoiceStudioTTS().cac_giong()

    assert len(giong) >= 1  # danh sách dự phòng, không phải ngoại lệ


def test_doc_duoc_danh_sach_giong_that(monkeypatch) -> None:
    than = json.dumps(
        {"voices": [{"id": "lan", "name": "Cô Lan", "gender": "nữ"}, {"id": "nam"}]}
    ).encode()
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: TraLoiGia(than))

    giong = VoiceStudioTTS().cac_giong()

    assert [g.ma for g in giong] == ["lan", "nam"]
    assert giong[0].ten == "Cô Lan"
    #: Thiếu `name` thì lấy `id` làm tên, đừng để ô chọn hiện chữ "None".
    assert giong[1].ten == "nam"


def test_dia_chi_doi_duoc(monkeypatch, tmp_path) -> None:
    """VoiceStudio chạy trên máy khác trong mạng thì chỉ đổi địa chỉ."""
    da_gui: dict = {}

    def gia_lap(req, timeout=0):
        da_gui["url"] = req.full_url
        return TraLoiGia(b"wav")

    monkeypatch.setattr("urllib.request.urlopen", gia_lap)
    VoiceStudioTTS(base_url="http://192.168.1.50:3900/v1/").doc(
        "Xin chào", tmp_path / "f.wav", giong="x"
    )

    assert da_gui["url"] == "http://192.168.1.50:3900/v1/audio/speech"


def test_lay_provider_biet_ten_voicestudio() -> None:
    assert lay_provider("voicestudio").ten == "voicestudio"
