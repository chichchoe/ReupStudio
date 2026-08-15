"""Provider giọng Gemini — phần kiểm được mà không cần gọi mạng.

Chất giọng hay hay dở thì phải nghe. Nhưng hai thứ quanh nó phải đúng tuyệt đối:
khoá API không được lọt ra ngoài, và PCM thô phải được bọc thành WAV đúng chuẩn.
"""

from __future__ import annotations

import wave

import pytest

from src.errors import ReupError
from src.tts.gemini import GIONG_GEMINI, TAN_SO, GeminiTTS, _che_khoa, _ghi_wav


def test_khong_co_khoa_thi_bao_loi_ngay() -> None:
    """Thà dừng với lỗi rõ còn hơn gọi mạng rồi nhận 401 khó hiểu."""
    with pytest.raises(ReupError):
        GeminiTTS(api_key="")


def test_khoa_khong_bao_gio_lot_ra_thong_bao_loi() -> None:
    """Khoá lọt vào log là lộ khoá — log được ghi ra file và gửi đi nơi khác."""
    khoa = "AIzaSyD-khoa-that-cua-du-an-123456"
    tho = f"Lỗi 400 với key={khoa} tại endpoint /tts"

    che = _che_khoa(tho, khoa)

    assert khoa not in che
    assert "***" in che


def test_pcm_tho_duoc_boc_thanh_wav_dung_chuan(tmp_path) -> None:
    """Gemini trả về audio/L16 KHÔNG có header. Ghi thẳng ra đĩa thì ffmpeg
    không đoán được định dạng và mọi bước sau hỏng với lỗi khó hiểu."""
    dst = tmp_path / "giong.wav"
    #: Một giây im lặng: 24000 mẫu, mỗi mẫu 2 byte.
    _ghi_wav(dst, b"\x00\x00" * TAN_SO)

    with wave.open(str(dst), "rb") as f:
        assert f.getnchannels() == 1
        assert f.getsampwidth() == 2
        assert f.getframerate() == TAN_SO
        assert f.getnframes() == TAN_SO


def test_cau_rong_khong_goi_mang_va_khong_no(tmp_path) -> None:
    """Bản dịch đôi khi cho ra câu chỉ có dấu câu. Một câu như vậy không được
    tốn một lượt hạn mức, cũng không được làm hỏng cả video."""
    p = GeminiTTS(api_key="khoa-gia")
    dst = p.doc("   ", tmp_path / "rong.wav")

    assert dst.exists()
    assert dst.stat().st_size == 0


def test_du_ba_muoi_giong_va_khong_trung_ma() -> None:
    """Mã giọng trùng nhau làm ô chọn trên giao diện hiện hai dòng như nhau."""
    ma = [g.ma for g in GIONG_GEMINI]

    assert len(ma) == 30
    assert len(set(ma)) == 30


def test_moi_giong_deu_co_ten_doc_duoc_va_gioi_tinh() -> None:
    """Người dùng chọn giọng bằng tên tiếng Việt, không bằng mã thiên văn."""
    for g in GIONG_GEMINI:
        assert g.ten and g.ten != g.ma
        assert g.gioi_tinh in ("nam", "nữ")
