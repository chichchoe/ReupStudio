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

import numpy as np
import pytest

from src.errors import ReupError
from src.tts import lay_provider
from src.tts.openrouter import (
    MODEL_MAC_DINH,
    TAN_SO,
    TOKEN_TOI_DA,
    TOKEN_TOI_THIEU,
    OpenRouterTTS,
    _canh_bao_neu_doc_sai,
    _gop_audio_tu_sse,
    _loi_nhac_doc,
    _tran_token,
    cat_im_lang,
)


def _sse(*goi: dict) -> list[bytes]:
    dong = [f"data: {json.dumps(g)}".encode() for g in goi]
    return [b": giu ket noi", b"", *dong, b"data: [DONE]"]


def _mau_audio(du_lieu: bytes) -> dict:
    return {"choices": [{"delta": {"audio": {"data": base64.b64encode(du_lieu).decode()}}}]}


def test_noi_het_cac_mau_chu_khong_lay_mau_dau() -> None:
    """Lấy mẩu đầu là ra file cụt — lỗi chỉ nghe mới biết."""
    luong = _sse(_mau_audio(b"AAAA"), _mau_audio(b"BBBB"), _mau_audio(b"CCCC"))

    assert _gop_audio_tu_sse(luong)[0] == b"AAAABBBBCCCC"


def test_bo_qua_dong_khong_phai_json_va_dung_o_DONE() -> None:
    luong = [
        b": comment",
        b"",
        b"data: khong-phai-json",
        f"data: {json.dumps(_mau_audio(b'XY'))}".encode(),
        b"data: [DONE]",
        f"data: {json.dumps(_mau_audio(b'SAU-DONE'))}".encode(),
    ]

    assert _gop_audio_tu_sse(luong)[0] == b"XY"


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


def test_cat_duoi_im_lang_cua_gpt_audio() -> None:
    """`gpt-audio` nói vài giây rồi ĐỆM THÊM rất nhiều im lặng.

    Đo thật ngày 2026-08-16: câu "Bạn định nấu món gì hôm nay?" nói 2 giây rồi
    im lặng **816 giây** (file 38 MB). Không cắt thì `do_dai_am_thanh` đo ra
    818 giây cho một câu 2 giây, `lap_lich_long_tieng` ép tốc độ và đẩy lệch
    mọi câu sau — chính là "lồng tiếng không khớp lời nói".
    """
    im_dau = np.zeros(int(0.5 * TAN_SO), np.int16)
    tieng = (np.sin(np.arange(TAN_SO) * 0.05) * 8000).astype(np.int16)
    im_duoi = np.zeros(int(8 * TAN_SO), np.int16)

    ra = cat_im_lang(np.concatenate([im_dau, tieng, im_duoi]).tobytes())

    giay = len(ra) / 2 / TAN_SO
    assert 1.1 < giay < 1.2, f"cắt xong còn {giay:.2f}s, mong đợi ~1,15s"


def test_giu_lai_duoi_ngan_de_chu_khong_cut() -> None:
    """Cắt sát tiếng cuối là chữ nghe cụt đuôi."""
    tieng = (np.sin(np.arange(TAN_SO) * 0.05) * 8000).astype(np.int16)

    ra = cat_im_lang(np.concatenate([tieng, np.zeros(TAN_SO, np.int16)]).tobytes())

    assert len(ra) / 2 / TAN_SO > 1.0


def test_ca_doan_im_lang_thi_tra_ve_rong() -> None:
    """Rỗng để bước xếp lịch bỏ qua, thay vì cắm một khoảng câm vào dải tiếng."""
    assert cat_im_lang(np.zeros(TAN_SO, np.int16).tobytes()) == b""


def test_model_tra_loi_thay_vi_doc_thi_bao_loi() -> None:
    """Gửi một câu, model đọc ra cả đoạn tán gẫu — phải dừng, đừng ghép vào video."""
    with pytest.raises(ReupError, match="TRẢ LỜI thay vì"):
        _canh_bao_neu_doc_sai(
            "Hôm nay trời rất đẹp.",
            "Chào bạn! Nghe có vẻ thú vị đấy. Hôm nay trời quả là rất đẹp, và nấu ăn "
            "cùng nhau chắc chắn sẽ rất vui. Bạn muốn thử nấu món gì hôm nay?",
        )


def test_doc_dung_cau_thi_khong_bao_gi() -> None:
    """Máy đọc hay đọc số thành chữ nên dài ra chút là bình thường."""
    _canh_bao_neu_doc_sai("Tiêu hết 2000 tệ.", "Tiêu hết hai nghìn tệ.")


def test_loi_nhac_boc_cau_vao_menh_lenh() -> None:
    """Gửi câu trần thì model coi đó là lượt trò chuyện và trả lời.

    Đo thật: lời nhắc hệ thống mạnh THÔI không đủ; phải bọc vào mệnh lệnh ngay
    trong lượt của người dùng.
    """
    ra = _loi_nhac_doc("Đi thôi!")

    assert "nguyên văn" in ra
    assert '"Đi thôi!"' in ra


def _mau_pcm(du_lieu: np.ndarray) -> dict:
    return {
        "choices": [{"delta": {"audio": {"data": base64.b64encode(du_lieu.tobytes()).decode()}}}]
    }


def test_dung_luong_ngay_khi_da_im_du_lau() -> None:
    """Không tải hết 816 giây im lặng rồi mới cắt.

    Đo ngày 2026-08-16: một câu 2 giây kéo theo 816 giây im lặng — 38 MB tải về
    chỉ để vứt đi. Cắt sau khi tải sửa được độ dài nhưng không lấy lại được
    thời gian; đóng luồng sớm thì lấy lại được cả hai.
    """
    tieng = (np.sin(np.arange(TAN_SO) * 0.05) * 8000).astype(np.int16)
    im_mot_giay = np.zeros(TAN_SO, np.int16)
    #: 1 giây tiếng, rồi 60 giây im — luồng thật còn dài hơn nhiều.
    goi = [_mau_pcm(tieng)] + [_mau_pcm(im_mot_giay) for _ in range(60)]

    da_doc = {"n": 0}

    def luong():
        for g in goi:
            da_doc["n"] += 1
            yield f"data: {json.dumps(g)}".encode()
        yield b"data: [DONE]"

    _gop_audio_tu_sse(luong())

    #: 1 mẩu tiếng + đủ mẩu im để vượt 1,5s, KHÔNG đọc hết 61 mẩu.
    assert da_doc["n"] < 6, f"đã đọc {da_doc['n']}/61 mẩu, đáng lẽ dừng sớm"


def test_khong_dung_som_khi_chua_co_tieng_nao() -> None:
    """Model im vài mẩu đầu rồi mới nói — dừng lúc đó là mất cả câu."""
    im = np.zeros(TAN_SO * 2, np.int16)
    tieng = (np.sin(np.arange(TAN_SO) * 0.05) * 8000).astype(np.int16)
    luong = [
        f"data: {json.dumps(_mau_pcm(im))}".encode(),
        f"data: {json.dumps(_mau_pcm(tieng))}".encode(),
        b"data: [DONE]",
    ]

    pcm, _ = _gop_audio_tu_sse(luong)

    assert len(pcm) / 2 / TAN_SO > 2.5  # giữ cả phần im đầu lẫn tiếng


def test_khoang_lang_giua_cau_khong_lam_dung_som() -> None:
    """Nghỉ lấy hơi giữa hai vế câu thường dưới 0,5s — không được cắt ngang."""
    tieng = (np.sin(np.arange(TAN_SO // 2) * 0.05) * 8000).astype(np.int16)
    nghi = np.zeros(TAN_SO // 2, np.int16)  # 0,5s
    luong = [
        f"data: {json.dumps(_mau_pcm(tieng))}".encode(),
        f"data: {json.dumps(_mau_pcm(nghi))}".encode(),
        f"data: {json.dumps(_mau_pcm(tieng))}".encode(),
        b"data: [DONE]",
    ]

    pcm, _ = _gop_audio_tu_sse(luong)

    assert len(pcm) / 2 / TAN_SO > 1.4  # cả hai vế còn nguyên


def test_luon_dat_tran_token(monkeypatch, tmp_path) -> None:
    """Thiếu trần là mỗi câu chạy tới 16.384 token — hoá đơn nở ra hàng chục lần.

    Đo ngày 2026-08-16, câu 57 ký tự: không trần → 16.355 token audio, 817,8
    giây tiếng, $0,0394 MỘT CÂU trên bản rẻ. Đặt trần → 250 token, $0,0007.
    Trên `gpt-audio` (đắt gấp 53 lần) thì một video 133 câu tốn cỡ 70 đô.
    """
    da_gui: dict = {}

    class TraLoiGia:
        def __enter__(self):
            return _sse(_mau_audio(b"tieng123"))

        def __exit__(self, *a):
            return False

    def gia_lap(req, timeout=0):
        da_gui.update(json.loads(req.data))
        return TraLoiGia()

    monkeypatch.setattr("urllib.request.urlopen", gia_lap)
    OpenRouterTTS(api_key="khoa-gia").doc("Đi thôi!", tmp_path / "tran.wav", giong="nova")

    assert da_gui["max_tokens"] == TOKEN_TOI_THIEU
    assert da_gui["temperature"] == 0


def test_tran_token_co_gian_theo_do_dai_cau() -> None:
    ngan, dai = _tran_token("Đi thôi!"), _tran_token("x" * 300)

    assert ngan == TOKEN_TOI_THIEU  # câu ngắn vẫn đủ chỗ
    assert dai == TOKEN_TOI_DA  # câu bất thường không kéo cả hoá đơn
    assert _tran_token("y" * 60) > ngan  # ở giữa thì co giãn


def test_mac_dinh_dung_ban_re() -> None:
    """`gpt-audio` tính $32/1M token audio, `gpt-audio-mini` $0,60/1M."""
    assert MODEL_MAC_DINH == "openai/gpt-audio-mini"
