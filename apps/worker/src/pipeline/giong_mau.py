"""Chuẩn hoá và đo đoạn giọng mẫu trước khi đưa vào thư viện giọng.

Vì sao đo kỹ: Fish S2-Pro nhân bản giọng theo ngữ cảnh — nó CHÉP LẠI đoạn
mẫu, kể cả nhiễu, tiếng vọng và mức âm lượng. Chất lượng bản lồng tiếng không
bao giờ vượt được chất lượng đoạn mẫu. Đo ngày 2026-08-20 đã dính đúng bẫy
này: lấy đầu ra của Edge TTS làm mẫu, tức bắt model chép lại một giọng máy.

Ba hàm tách bạch để test được: ``lenh_chuan_hoa`` chỉ dựng danh sách tham số,
``doc_so_do`` chỉ đọc chữ ffmpeg in ra, ``chuan_hoa`` mới thật sự chạy.
"""

from __future__ import annotations

import re
from pathlib import Path

from reup_core.giong import DoAmThanh
from reup_core.logging import get_logger

from ..ffmpeg.runner import ffmpeg_bin, run_ffmpeg, run_ffmpeg_phan_tich

log = get_logger(__name__)

#: Trần độ dài đoạn mẫu. Dài hơn chỉ tổ phí ngữ cảnh và làm chậm mỗi câu, mà
#: không thêm đặc trưng giọng nào.
DAI_NHAT_GIAY = 15.0

#: Ngưỡng coi là im lặng khi dò. -45 dB là mức phòng yên, không phải mức nhạc nhỏ.
NGUONG_IM_LANG_DB = -45


def lenh_chuan_hoa(
    src: Path,
    dst: Path,
    *,
    tu_giay: float | None = None,
    den_giay: float | None = None,
) -> list[str]:
    """Dựng lệnh ffmpeg đưa đoạn mẫu về mono 44,1kHz, cắt im lặng, cân âm lượng.

    Hàm THUẦN — chỉ trả danh sách tham số, không chạy gì. Nhờ vậy test khoá
    được từng lựa chọn mà không cần file âm thanh thật.

    ``-ss`` đặt TRƯỚC ``-i``: đứng sau thì ffmpeg giải mã từ đầu file, cắt một
    đoạn giữa video một tiếng sẽ chờ rất lâu.

    Luôn khống chế bằng ``-t``, kể cả khi người dùng chọn khoảng dài hơn
    ``DAI_NHAT_GIAY``.
    """
    dai = DAI_NHAT_GIAY
    if tu_giay is not None and den_giay is not None:
        dai = min(DAI_NHAT_GIAY, max(0.0, den_giay - tu_giay))

    cmd = [ffmpeg_bin(), "-y"]
    if tu_giay is not None:
        cmd += ["-ss", str(tu_giay)]
    cmd += ["-i", str(src), "-t", str(dai)]

    #: silenceremove cắt im lặng ở HAI đầu (stop_periods=-1 lo phần đuôi);
    #: loudnorm đưa về mức chuẩn để mọi giọng trong thư viện nghe ngang nhau.
    cmd += [
        "-af",
        (
            f"silenceremove=start_periods=1:start_threshold={NGUONG_IM_LANG_DB}dB:"
            f"start_silence=0.1,areverse,"
            f"silenceremove=start_periods=1:start_threshold={NGUONG_IM_LANG_DB}dB:"
            f"start_silence=0.1,areverse,"
            "loudnorm=I=-18:TP=-2:LRA=11"
        ),
        "-ac",
        "1",
        "-ar",
        "44100",
        "-vn",
        str(dst),
    ]
    return cmd


def _db_sang_bien_do(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def doc_so_do(volumedetect_stderr: str, do_dai_giay: float, im_lang_stderr: str) -> DoAmThanh:
    """Đọc số đo từ chữ ffmpeg in ra. Hàm THUẦN.

    Thiếu số liệu thì trả 0 chứ KHÔNG ném lỗi: ffmpeg đổi định dạng in ra là
    chuyện có thật, nổ ở đây thì thêm giọng nào cũng hỏng. Về 0 thì cổng chất
    lượng cảnh báo "quá nhỏ" và người dùng vẫn đi tiếp được.
    """

    def _lay(ten: str) -> float:
        m = re.search(rf"{ten}:\s*(-?[\d.]+) dB", volumedetect_stderr)
        return _db_sang_bien_do(float(m.group(1))) if m else 0.0

    tong_im = sum(float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", im_lang_stderr))

    return DoAmThanh(
        do_dai_giay=do_dai_giay,
        rms=_lay("mean_volume"),
        dinh=_lay("max_volume"),
        ti_le_im_lang=round(tong_im / do_dai_giay, 4) if do_dai_giay > 0 else 0.0,
    )


def chuan_hoa(
    src: Path,
    dst: Path,
    *,
    tu_giay: float | None = None,
    den_giay: float | None = None,
) -> DoAmThanh:
    """Chuẩn hoá đoạn mẫu rồi đo nó. Ghi ra file TẠM rồi đổi tên.

    Ghi thẳng vào ``dst`` thì crash giữa chừng để lại file dở dang mà bước sau
    tưởng là hợp lệ (luật CLAUDE.md về ffmpeg).
    """
    from reup_core.paths import tmp_sibling

    dst.parent.mkdir(parents=True, exist_ok=True)
    tam = tmp_sibling(dst)

    run_ffmpeg(lenh_chuan_hoa(src, tam, tu_giay=tu_giay, den_giay=den_giay)[1:])
    tam.rename(dst)

    from ..ffmpeg.probe import do_dai_am_thanh

    do_dai = do_dai_am_thanh(dst)
    #: volumedetect và silencedetect đều in ra stderr và không sinh file —
    #: xuất ra null.
    vol = run_ffmpeg_phan_tich(["-i", str(dst), "-af", "volumedetect", "-f", "null", "-"])
    im = run_ffmpeg_phan_tich(
        ["-i", str(dst), "-af", f"silencedetect=n={NGUONG_IM_LANG_DB}dB:d=0.3", "-f", "null", "-"]
    )

    do = doc_so_do(vol, do_dai, im)
    log.info(
        "giong_mau.chuan_hoa_xong",
        dst=str(dst),
        do_dai=do.do_dai_giay,
        rms=round(do.rms, 4),
        dinh=round(do.dinh, 4),
        im_lang=do.ti_le_im_lang,
    )
    return do
