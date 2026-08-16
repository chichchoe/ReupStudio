"""Giọng đọc qua OpenRouter (``openai/gpt-audio``).

Ba chỗ dễ sai, và cả ba đều chỉ lộ ra khi đã tốn tiền gọi API thật, nên khoá
lại bằng test chạy offline:

1. Thiếu ``stream: true`` — OpenRouter KHÔNG trả audio, chỉ trả chữ.
2. Lấy mẩu base64 đầu tiên thay vì nối hết — ra file cụt vài trăm mili giây.
3. Không nhận ra luồng chẳng có mẩu audio nào — ghi ra file rỗng rồi lặng lẽ
   dựng một dải tiếng toàn số 0, đúng kiểu hỏng vừa làm mất trắng một video.
"""

from __future__ import annotations

import base64
import io
import json
import urllib.error
import wave

import pytest

from src.errors import ReupError
from src.tts import lay_provider
from src.tts.openrouter import OpenRouterTTS, _gop_audio_tu_sse


def _sse(*goi: dict) -> list[bytes]:
    dong = [f"data: {json.dumps(g)}".encode() for g in goi]
    return [b": giu ket noi", b"", *dong, b"data: [DONE]"]


def _mau_audio(du_lieu: bytes) -> dict:
    return {"choices": [{"delta": {"audio": {"data": base64.b64encode(du_lieu).decode()}}}]}


def test_noi_het_cac_mau_chu_khong_lay_mau_dau() -> None:
    """Lấy mẩu đầu là ra file cụt — lỗi chỉ nghe mới biết."""
    luong = _sse(_mau_audio(b"AAAA"), _mau_audio(b"BBBB"), _mau_audio(b"CCCC"))

    assert _gop_audio_tu_sse(luong) == b"AAAABBBBCCCC"


def test_bo_qua_dong_khong_phai_json_va_dung_o_DONE() -> None:
    luong = [
        b": comment",
        b"",
        b"data: khong-phai-json",
        f"data: {json.dumps(_mau_audio(b'XY'))}".encode(),
        b"data: [DONE]",
        f"data: {json.dumps(_mau_audio(b'SAU-DONE'))}".encode(),
    ]

    assert _gop_audio_tu_sse(luong) == b"XY"


def test_luong_khong_co_audio_thi_bao_loi() -> None:
    """Chỉ có chữ, không có tiếng — phải kêu, không được ghi file rỗng."""
    luong = _sse({"choices": [{"delta": {"content": "Xin chào"}}]})

    with pytest.raises(ReupError, match="không trả về mẩu audio"):
        _gop_audio_tu_sse(luong)


def test_than_yeu_cau_phai_bat_stream(monkeypatch, tmp_path) -> None:
    """Thiếu `stream: true` là OpenRouter không trả audio."""
    da_gui: dict = {}

    class TraLoiGia:
        def __enter__(self):
            return _sse(_mau_audio(b"tieng123"))

        def __exit__(self, *a):
            return False

    def gia_lap(req, timeout=0):
        da_gui.update(json.loads(req.data))
        da_gui["_headers"] = req.headers
        return TraLoiGia()

    monkeypatch.setattr("urllib.request.urlopen", gia_lap)
    OpenRouterTTS(api_key="khoa-gia").doc("Xin chào", tmp_path / "a.wav", giong="nova")

    assert da_gui["stream"] is True
    assert da_gui["modalities"] == ["text", "audio"]
    assert da_gui["audio"] == {"voice": "nova", "format": "pcm16"}

    #: Đọc lại bằng `wave`: file phải là WAV hợp lệ, không phải PCM thô.
    #: Mẫu thử dài CHẴN byte — PCM 16-bit là 2 byte một mẫu, số lẻ thì byte
    #: cuối bị bỏ, và test sẽ đỏ vì lý do chẳng liên quan gì tới cái đang kiểm.
    with wave.open(str(tmp_path / "a.wav"), "rb") as f:
        assert f.getnchannels() == 1
        assert f.getsampwidth() == 2
        assert f.getframerate() == 24000
        assert f.readframes(f.getnframes()) == b"tieng123"


def test_cau_rong_khong_goi_mang(monkeypatch, tmp_path) -> None:
    """Một câu rỗng không được làm hỏng cả video, cũng không tốn một lượt gọi."""

    def cam_goi(*a, **k):
        raise AssertionError("không được gọi mạng cho câu rỗng")

    monkeypatch.setattr("urllib.request.urlopen", cam_goi)
    dst = OpenRouterTTS(api_key="khoa-gia").doc("   ", tmp_path / "b.wav", giong="nova")

    assert dst.read_bytes() == b""


def test_thieu_khoa_thi_bao_ngay() -> None:
    with pytest.raises(ReupError, match="Chưa dán khoá OpenRouter"):
        OpenRouterTTS(api_key="")


def test_lay_provider_biet_ten_openrouter() -> None:
    provider = lay_provider("openrouter", api_key="khoa-gia")

    assert provider.ten == "openrouter"
    assert [g.ma for g in provider.cac_giong()][:2] == ["alloy", "echo"]


#: Nguyên văn thân lỗi OpenRouter trả về ngày 2026-08-16 (đã rút gọn phần
#: message, giữ nguyên hình dạng `metadata`).
_THAN_404 = (
    b'{"error":{"message":"No allowed providers are available for the selected model. '
    b"Providers serving openai/gpt-audio: openai, but your account's allowed-providers "
    b"setting permits only: minimax, fish-audio, google-ai-studio. To change your allowed "
    b'providers, visit: https://openrouter.ai/settings/privacy.","code":404,'
    b'"metadata":{"available_providers":["openai"],'
    b'"requested_providers":["minimax","fish-audio","google-ai-studio"]}}}'
)


def _chan_404(*a, **k):
    raise urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(_THAN_404))


def test_404_noi_ro_phai_cho_phep_ben_nao(monkeypatch, tmp_path) -> None:
    """404 ở đây là thiết lập TÀI KHOẢN, không phải model không tồn tại.

    OpenRouter nói sẵn trong `metadata` bên nào phục vụ model và tài khoản cho
    phép bên nào. Đọc ra và nói thẳng, đừng bắt người dùng mò trong JSON.
    """
    monkeypatch.setattr("urllib.request.urlopen", _chan_404)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    with pytest.raises(ReupError) as loi:
        OpenRouterTTS(api_key="khoa-gia").doc("Xin chào", tmp_path / "c.wav", giong="nova")

    tin = str(loi.value)
    assert "openai" in tin  # bên PHỤC VỤ model, tức bên cần thêm vào
    assert "minimax" in tin  # bên tài khoản đang cho phép
    assert "settings/privacy" in tin


def test_404_khong_thu_lai_ba_lan(monkeypatch, tmp_path) -> None:
    """Thử lại một lỗi thiết lập chỉ tốn thời gian, kết quả y hệt."""
    so_lan = {"n": 0}

    def dem(*a, **k):
        so_lan["n"] += 1
        _chan_404()

    monkeypatch.setattr("urllib.request.urlopen", dem)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    with pytest.raises(ReupError):
        OpenRouterTTS(api_key="khoa-gia").doc("Xin chào", tmp_path / "d.wav", giong="nova")

    assert so_lan["n"] == 1


def test_than_loi_dai_van_doc_duoc_metadata(monkeypatch, tmp_path) -> None:
    """Cắt thân lỗi TRƯỚC khi đọc là mất khối `metadata` nằm cuối.

    Lỗi thật dài hơn 300 ký tự; bản đầu cắt ở 300 nên rơi về câu chung chung.
    """
    monkeypatch.setattr("urllib.request.urlopen", _chan_404)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    assert len(_THAN_404) > 300

    with pytest.raises(ReupError, match="chỉ cho phép"):
        OpenRouterTTS(api_key="khoa-gia").doc("Xin chào", tmp_path / "e.wav", giong="nova")
