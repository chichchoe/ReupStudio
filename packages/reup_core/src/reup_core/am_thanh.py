"""Đọc thông tin âm thanh rẻ tiền — dùng chung cho API và worker.

Chỉ đọc phần ĐẦU file, không giải mã và không gọi tiến trình con. Bảng đối
chiếu của một video có tới 672 câu; gọi ``ffprobe`` cho từng câu là 672 tiến
trình con và trang mất hàng phút mới mở.

Cần số liệu đầy đủ hơn (mp3, video, số kênh) thì dùng ``ffmpeg/probe.py`` bên
worker — chỗ đó chấp nhận được vì chỉ chạy một lần mỗi video.
"""

from __future__ import annotations

import contextlib
import wave
from pathlib import Path


def do_dai_wav(path: Path) -> float | None:
    """Độ dài file WAV theo giây, hoặc ``None`` nếu không đọc được.

    Trả ``None`` chứ không ném lỗi cho MỌI trường hợp hỏng — thiếu file, file
    rỗng, header hỏng. Một câu thiếu giọng không được làm hỏng cả bảng đối
    chiếu: nhà cung cấp giọng đôi khi báo "thành công" mà không ghi byte nào,
    và đó là chuyện của riêng câu đó.
    """
    if not path.exists() or path.stat().st_size == 0:
        return None

    with contextlib.suppress(Exception):
        with contextlib.closing(wave.open(str(path))) as w:
            tan_so = w.getframerate()
            if tan_so > 0:
                return w.getnframes() / tan_so

    return None
