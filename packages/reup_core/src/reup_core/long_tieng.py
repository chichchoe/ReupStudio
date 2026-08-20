"""Luật xếp lịch lồng tiếng — dùng CHUNG cho worker và API.

Vì sao ở đây chứ không ở ``worker/pipeline/dubbing.py``: dòng thời gian ở màn
duyệt phải vẽ lớp giọng và bôi đỏ chỗ tràn, mà muốn đúng thì phải tính bằng
đúng luật worker dùng lúc dựng. Chép hằng số sang giao diện là mở đường cho
hai bên lệch nhau — giao diện báo xanh trong khi bản dựng thật vẫn tràn.

``pipeline/dubbing.py`` giữ nguyên phần xếp lịch cả video; chỗ này chỉ là luật
cho MỘT câu, đủ để cả hai bên hỏi cùng một câu hỏi và nhận cùng một đáp án.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Chừa lại chừng này giây trước khi câu sau bắt đầu, để hai giọng không dính
#: đuôi nhau.
KHE_GIUA_HAI_CAU = 0.08

#: Trần tốc độ đọc. 1,5 là mức người Việt còn nghe kịp; trên nữa thì câu chữ
#: vẫn đủ nhưng người xem không bắt được ý — tức là hỏng mà vẫn "chạy".
TOC_DO_TOI_DA = 1.5

#: Sàn tốc độ. KHÔNG kéo chậm dưới 1,0: giọng kéo chậm nghe như đang ngái ngủ,
#: thà im lặng một chút.
TOC_DO_TOI_THIEU = 1.0


@dataclass(frozen=True)
class ChoMotCau:
    """Câu này có bao nhiêu chỗ, phải đọc nhanh cỡ nào, và còn tràn bao nhiêu."""

    #: Chỗ trống thật sự dùng được: từ lúc câu này bắt đầu tới lúc câu SAU bắt
    #: đầu (đã trừ khe hở), KHÔNG phải tới lúc câu này kết thúc.
    cho_trong_giay: float
    #: Nhân vào tốc độ phát. 1,0 là giữ nguyên.
    he_so_toc_do: float
    #: Còn thừa bao nhiêu giây sau khi đã ép nhanh hết cỡ. 0 là vừa.
    tran_giay: float


def tinh_cho_cau(
    *,
    bat_dau: float,
    cau_sau_bat_dau: float | None,
    do_dai_giong: float | None,
) -> ChoMotCau:
    """Luật xếp chỗ cho MỘT câu. Hàm thuần.

    Ba cách xử lý, dùng theo thứ tự — giống hệt ``pipeline/dubbing.py``:

    1. **Mượn khoảng lặng phía sau** nếu câu tiếp theo còn xa. Không tốn gì cả
       nên thử trước.
    2. **Nói nhanh hơn**, nhưng không quá ``TOC_DO_TOI_DA``.
    3. **Chấp nhận tràn** khi hai cách trên không đủ. Câu sau vẫn bắt đầu đúng
       lúc của nó — không bao giờ đẩy nó trễ đi.

    ``cau_sau_bat_dau=None`` nghĩa là câu cuối: không có gì phía sau để đụng.
    """
    if do_dai_giong is None or do_dai_giong <= 0 or cau_sau_bat_dau is None:
        return ChoMotCau(
            cho_trong_giay=0.0, he_so_toc_do=TOC_DO_TOI_THIEU, tran_giay=0.0
        )

    cho_trong = max(0.0, cau_sau_bat_dau - KHE_GIUA_HAI_CAU - bat_dau)

    if cho_trong <= 0 or do_dai_giong <= cho_trong:
        return ChoMotCau(cho_trong, TOC_DO_TOI_THIEU, 0.0)

    he_so = max(TOC_DO_TOI_THIEU, min(TOC_DO_TOI_DA, do_dai_giong / cho_trong))
    return ChoMotCau(cho_trong, he_so, max(0.0, do_dai_giong / he_so - cho_trong))
