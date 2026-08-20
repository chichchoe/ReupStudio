"""Độ dài THẬT của giọng từng câu — để dòng thời gian vẽ được lớp giọng.

Đây là thứ danh sách chữ không bao giờ cho thấy: tiếng Việt dài hơn tiếng
Trung, câu tràn thì đè lên câu sau. ``pipeline/dubbing.py`` đã cố ép nhanh
tới trần 1,5 rồi vẫn còn tràn — người duyệt phải nhìn thấy chỗ nào tràn.

Đọc phần đầu file WAV chứ không gọi ffprobe: 672 câu mà mỗi câu một tiến
trình con thì mở trang mất hàng phút.
"""

from __future__ import annotations

import struct
import wave

from reup_core.am_thanh import do_dai_wav


def _wav(path, giay: float, sr: int = 44100) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * int(sr * giay))


def test_doc_dung_do_dai(tmp_path) -> None:
    f = tmp_path / "cau.wav"
    _wav(f, 1.5)
    assert abs(do_dai_wav(f) - 1.5) < 0.01


def test_khong_co_file_thi_None(tmp_path) -> None:
    assert do_dai_wav(tmp_path / "khong-co.wav") is None


def test_file_rong_thi_None_chu_khong_no(tmp_path) -> None:
    #: TTS đôi khi "thành công" mà không ghi byte nào. Nổ ở đây thì cả bảng
    #: đối chiếu hỏng, trong khi chỉ một câu thiếu giọng.
    f = tmp_path / "rong.wav"
    f.write_bytes(b"")
    assert do_dai_wav(f) is None


def test_file_hong_thi_None(tmp_path) -> None:
    f = tmp_path / "hong.wav"
    f.write_bytes(b"khong phai wav")
    assert do_dai_wav(f) is None


def test_tan_so_khac_van_dung(tmp_path) -> None:
    f = tmp_path / "cau.wav"
    _wav(f, 2.0, sr=24000)
    assert abs(do_dai_wav(f) - 2.0) < 0.01
