"""Ghép các mẩu giọng đọc thành một dải tiếng, rồi trộn vào video (M8).

Tách khỏi ``pipeline/dubbing.py`` vì file kia là hàm THUẦN — nó chỉ tính lịch
phát, không chạm ffmpeg. Ở đây mới là chỗ đụng file thật.

Cách dựng dải tiếng: giải mã từng mẩu ra PCM rồi ĐẶT vào một mảng numpy dài
bằng video, thay vì dựng một filtergraph ``adelay``+``amix`` khổng lồ. Video 34
phút có 672 câu; một filtergraph 672 nhánh vừa dài quá giới hạn dòng lệnh vừa
ngốn bộ nhớ, mà lỗi thì báo ra một chuỗi không ai đọc nổi.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from reup_core.logging import get_logger
from reup_core.paths import tmp_sibling

from ..errors import FFmpegError
from ..pipeline.dubbing import DoanTiengNoi

log = get_logger(__name__)

#: Tần số lấy mẫu của dải tiếng dựng ra. 24 kHz là đúng tần số edge-tts trả về,
#: nên không phải resample lần nào.
TAN_SO = 24000

#: Âm gốc bị hạ xuống mức này khi trộn. Không tắt hẳn: nhạc nền và tiếng động
#: hiện trường là một phần nội dung, tắt đi thì video nghe như đọc chính tả.
MUC_AM_GOC = 0.18


def _giai_ma_pcm(src: Path, he_so_toc_do: float) -> Any:
    """Giải mã một mẩu giọng ra PCM float32 một kênh, có ép tốc độ.

    ``atempo`` của ffmpeg chỉ nhận 0,5–2,0 mỗi lần. Hệ số ngoài khoảng đó phải
    xâu chuỗi nhiều bộ lọc — ở đây kẹp lại vì bước xếp lịch đã giới hạn 1,0–1,5
    rồi, ra ngoài khoảng đó là có lỗi ở chỗ khác.
    """
    import numpy as np

    he_so = max(0.5, min(2.0, he_so_toc_do))
    loc = [] if abs(he_so - 1.0) < 0.01 else ["-filter:a", f"atempo={he_so:.4f}"]

    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(src),
        *loc,
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(TAN_SO),
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.decode("utf-8", "replace")[-2000:])

    return np.frombuffer(proc.stdout, dtype=np.float32)


def dung_dai_tieng(
    doan: list[DoanTiengNoi], files: dict[int, Path], tong_giay: float, dst: Path
) -> Path:
    """Đặt từng mẩu giọng vào đúng mốc thời gian, ghi ra một file WAV.

    Các mẩu chồng nhau được CỘNG chứ không đè: bước xếp lịch cố ý chấp nhận
    tràn khi câu quá dài (xem ``pipeline/dubbing.py``), và đè lên nhau sẽ cắt
    cụt câu trước giữa chừng.
    """
    import numpy as np

    tong_mau = max(1, int(tong_giay * TAN_SO))
    dai = np.zeros(tong_mau, dtype=np.float32)

    for d in doan:
        f = files.get(d.cue_index)
        if f is None or not f.exists() or f.stat().st_size == 0:
            continue

        mau = _giai_ma_pcm(f, d.he_so_toc_do)
        bat_dau = int(d.bat_dau * TAN_SO)
        if bat_dau >= tong_mau:
            continue

        het = min(tong_mau, bat_dau + len(mau))
        dai[bat_dau:het] += mau[: het - bat_dau]

    #: Chống vỡ tiếng sau khi cộng các đoạn chồng nhau. Chuẩn hoá cả dải theo
    #: đỉnh chứ không cắt ngọn từng mẫu — cắt ngọn nghe rè.
    dinh = float(np.abs(dai).max())
    if dinh > 0.99:
        dai *= 0.99 / dinh

    dst.parent.mkdir(parents=True, exist_ok=True)
    tam = tmp_sibling(dst)
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "f32le",
        "-ar",
        str(TAN_SO),
        "-ac",
        "1",
        "-i",
        "pipe:0",
        "-c:a",
        "pcm_s16le",
        str(tam),
    ]
    proc = subprocess.run(cmd, input=dai.tobytes(), capture_output=True, timeout=600, check=False)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.decode("utf-8", "replace")[-2000:])

    tam.rename(dst)
    log.info("dub.dai_tieng", path=str(dst), doan=len(doan), giay=tong_giay)
    return dst


def tron_tieng_vao_video(
    video: Path, tieng: Path, dst: Path, *, muc_am_goc: float = MUC_AM_GOC, timeout: int = 3600
) -> Path:
    """Trộn dải tiếng Việt lên trên âm gốc đã hạ nhỏ, giữ nguyên hình.

    ``-c:v copy``: không encode lại hình. Video đã qua xoá chữ và burn phụ đề
    rồi, encode thêm một lần nữa chỉ để đổi tiếng là mất chất lượng không công.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tam = tmp_sibling(dst)

    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(video),
        "-i",
        str(tieng),
        "-filter_complex",
        f"[0:a]volume={muc_am_goc}[goc];[goc][1:a]amix=inputs=2:duration=first:dropout_transition=0[a]",
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(tam),
    ]
    log.debug("dub.tron", cmd=" ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        #: Video câm thì không có [0:a] và filtergraph hỏng. Khi đó chỉ cần gắn
        #: thẳng dải tiếng vào, không trộn với gì cả.
        log.info("dub.tron_khong_co_am_goc", video=str(video))
        cmd_cam = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-i",
            str(tieng),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(tam),
        ]
        proc = subprocess.run(cmd_cam, capture_output=True, timeout=timeout, check=False)
        if proc.returncode != 0:
            raise FFmpegError(proc.stderr.decode("utf-8", "replace")[-2000:])

    tam.rename(dst)
    log.info("dub.xong", path=str(dst), size=dst.stat().st_size)
    return dst
