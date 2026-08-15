"""Xếp lịch lồng tiếng: đặt từng câu tiếng Việt vào đúng lúc trên trục thời gian.

Hàm THUẦN: không gọi TTS, không chạm ffmpeg, không chạm DB. Nhận độ dài các
file giọng đã sinh, trả về lịch phát.

Vấn đề gốc của lồng tiếng: **tiếng Việt dài hơn tiếng Trung**. Một câu thoại 2
giây tiếng Trung dịch ra có thể cần 3 giây để đọc. Nếu cứ phát nối tiếp nhau
thì mỗi câu đẩy câu sau trễ thêm, tới cuối video tiếng nói lệch hình hàng chục
giây — và người xem thấy ngay.

Ba cách xử lý, dùng theo thứ tự:

1. **Nói nhanh hơn**, nhưng có trần. Quá ``toc_do_toi_da`` thì người nghe không
   kịp, lúc đó giọng đọc thành vô dụng.
2. **Mượn khoảng lặng phía sau** nếu câu tiếp theo còn xa — cách này không tốn
   gì cả, nên thử trước khi ép nhanh.
3. **Chấp nhận tràn** khi hai cách trên không đủ, nhưng KHÔNG BAO GIỜ đẩy câu
   sau trễ đi: mỗi câu luôn bắt đầu đúng lúc cue của nó bắt đầu.

Cố ý KHÔNG kéo chậm giọng đọc cho vừa khung khi câu quá ngắn: giọng kéo chậm
nghe như đang ngái ngủ, thà im lặng một chút.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ReupError
from .cues import Cue


@dataclass(frozen=True)
class ThamSoLongTieng:
    """Núm vặn của bước xếp lịch. Không hardcode ở chỗ khác."""

    #: Trần tốc độ đọc. 1,5 là mức người Việt còn nghe kịp; trên nữa thì câu
    #: chữ vẫn đủ nhưng người xem không bắt được ý, tức là hỏng mà vẫn "chạy".
    toc_do_toi_da: float = 1.5

    #: Sàn tốc độ. KHÔNG kéo chậm dưới 1,0 — xem docstring module.
    toc_do_toi_thieu: float = 1.0

    #: Chừa lại chừng này giây trước khi câu sau bắt đầu, để hai giọng không
    #: dính đuôi nhau.
    khe_giua_hai_cau: float = 0.08


@dataclass(frozen=True)
class DoanTiengNoi:
    """Một câu đã có chỗ trên trục thời gian."""

    #: Chỉ số cue gốc — giữ lại để ghép đúng file giọng với đúng câu.
    cue_index: int
    bat_dau: float
    #: Độ dài file giọng gốc, trước khi ép nhanh.
    do_dai_goc: float
    #: Nhân vào tốc độ phát. 1,0 là giữ nguyên.
    he_so_toc_do: float

    @property
    def do_dai_sau_khi_ep(self) -> float:
        return self.do_dai_goc / self.he_so_toc_do

    @property
    def ket_thuc(self) -> float:
        return self.bat_dau + self.do_dai_sau_khi_ep


def lap_lich_long_tieng(
    cues: list[Cue],
    do_dai_am: list[float],
    tham_so: ThamSoLongTieng | None = None,
) -> list[DoanTiengNoi]:
    """Xếp lịch phát cho từng câu, trả về danh sách đoạn đã khớp thời gian.

    ``do_dai_am[i]`` là độ dài (giây) của file giọng đã sinh cho ``cues[i]``.

    Lệch số lượng thì ném lỗi chứ không đoán: lệch nghĩa là có câu mất giọng
    hoặc giọng gán nhầm câu, và cả hai đều hỏng âm thầm — video vẫn chạy, chỉ
    là nhân vật nói lời của câu khác.
    """
    tham_so = tham_so or ThamSoLongTieng()

    if len(cues) != len(do_dai_am):
        raise ReupError(
            f"Số câu ({len(cues)}) khác số file giọng ({len(do_dai_am)}) — "
            "không ghép được giọng với câu."
        )

    ra: list[DoanTiengNoi] = []

    for chi_so, (cue, do_dai) in enumerate(zip(cues, do_dai_am, strict=True)):
        #: TTS trả file 0 giây khi câu chỉ có dấu câu. Giữ lại sẽ chia cho 0 ở
        #: phép tính hệ số tốc độ.
        if do_dai <= 0:
            continue

        #: Chỗ trống thật sự có: từ lúc cue này bắt đầu tới lúc cue SAU bắt đầu,
        #: chứ không phải tới lúc cue này kết thúc. Đây chính là bước "mượn
        #: khoảng lặng phía sau" — không tốn gì nên thử trước khi ép nhanh.
        if chi_so + 1 < len(cues):
            gioi_han = cues[chi_so + 1].start - tham_so.khe_giua_hai_cau
        else:
            gioi_han = cue.start + do_dai  # câu cuối: không có gì phía sau để đụng

        cho_trong = max(0.0, gioi_han - cue.start)

        if cho_trong <= 0 or do_dai <= cho_trong:
            he_so = tham_so.toc_do_toi_thieu
        else:
            he_so = min(tham_so.toc_do_toi_da, do_dai / cho_trong)

        ra.append(
            DoanTiengNoi(
                cue_index=chi_so,
                bat_dau=cue.start,
                do_dai_goc=do_dai,
                he_so_toc_do=max(tham_so.toc_do_toi_thieu, he_so),
            )
        )

    return ra
