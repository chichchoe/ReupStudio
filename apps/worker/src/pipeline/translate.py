"""Dịch phụ đề Trung → Việt.

Ba điểm bắt buộc (xem docs/03-BACKLOG-CONG-VIEC.md, mục M1-WK-05):
1. Gửi cả LÔ, không gửi từng dòng — dịch rời rạc cho ra bản dịch không ngữ cảnh.
2. KIỂM TRA số dòng trả về; sai thì retry, retry vẫn sai thì dịch từng dòng.
3. Glossary ép cứng để tên riêng và xưng hô nhất quán giữa các tập.
"""

from __future__ import annotations

import time
from dataclasses import replace

from reup_core.logging import get_logger

from ..config import get_settings
from ..errors import TranslateError
from ..milestones import milestones, percent_of
from ..translator import get_translator
from .cues import Cue

log = get_logger(__name__)

#: Từ điển mặc định cho thể loại phim ngắn Trung Quốc.
DEFAULT_GLOSSARY: dict[str, str] = {
    "总裁": "tổng tài",
    "霸道总裁": "tổng tài bá đạo",
    "老公": "chồng",
    "老婆": "vợ",
    "小姐姐": "chị đẹp",
    "渣男": "gã tồi",
    "重生": "trùng sinh",
    "穿越": "xuyên không",
}


#: Cho test thay bằng hàm giả — không ai muốn bài test chờ thật 60 giây.
_sleep = time.sleep

#: Mỗi nhịp chờ trước khi hỏi lại bộ đếm. Nhỏ hơn thì hỏi DB quá dày, lớn hơn
#: thì chờ thừa sau khi hạn mức đã rảnh.
NHIP_CHO_GIAY = 5.0

#: Chờ tối đa bấy nhiêu rồi thôi, dù bộ đếm vẫn kẹt trần. Kẹt mãi nghĩa là hết
#: hạn mức NGÀY chứ không phải nghẽn theo phút — chuyện đó do chốt chặn ở tầng
#: ``tasks/`` xử lý (dừng hẳn, báo người dùng), giãn nhịp không được treo vĩnh
#: viễn ở đây.
CHO_TOI_DA_GIAY = 90.0


def chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _cho_cho_vua_nhip(dem_luot_gan_day, tran_moi_phut: int) -> None:
    """Chờ trước khi gọi lượt tiếp theo, nếu 60 giây qua đã dùng hết trần.

    ``dem_luot_gan_day`` là hàm trả về SỐ LƯỢT GỌI của cả dự án trong 60 giây
    gần nhất — do tầng ``tasks/`` tiêm vào, đằng sau là bảng ``cost_logs``.
    Tầng này không được chạm DB (luật hai lớp CLAUDE.md).

    VÌ SAO PHẢI ĐẾM TỪ NGUỒN CHUNG: bản đầu đếm mốc thời gian trong bộ nhớ của
    chính tiến trình này. Worker chạy ``concurrency=2``, hai task song song mỗi
    bên tự thấy mình dưới trần, cộng lại gấp đôi — trần là của CẢ DỰ ÁN, không
    phải của từng tiến trình. Lỗi đó chỉ lộ khi đo trên video thật; test một
    tiến trình không thể thấy.

    Không tiêm bộ đếm (script chạy tay, không có DB) thì KHÔNG giãn nhịp —
    thà chạy thẳng còn hơn bắt người viết script dựng bộ đếm giả.
    """
    if tran_moi_phut <= 0 or dem_luot_gan_day is None:
        return

    da_cho = 0.0
    while dem_luot_gan_day() >= tran_moi_phut and da_cho < CHO_TOI_DA_GIAY:
        cho = min(NHIP_CHO_GIAY, CHO_TOI_DA_GIAY - da_cho)
        log.info("translate.pacing", cho_giay=cho, tran=tran_moi_phut)
        _sleep(cho)
        da_cho += cho


def translate_cues(
    cues: list[Cue],
    *,
    tone: str = "doi_thuong",
    glossary: dict[str, str] | None = None,
    progress_cb=None,
    on_usage=None,
    dem_luot_gan_day=None,
    model: str | None = None,
    api_key: str = "",
    base_url: str = "",
    provider: str = "",
) -> list[Cue]:
    """Dịch cả danh sách cue, gọi ``on_usage`` sau MỖI lô.

    ``on_usage`` nhận một ``LlmUsage`` chụp lại lượng đã dùng tính tới lô vừa
    xong. Hàm này ở tầng ``pipeline/`` nên KHÔNG được chạm DB (luật hai lớp
    CLAUDE.md) — ghi vào ``cost_logs`` là việc của tầng ``tasks/``, nó tiêm
    callback vào đây.

    Báo theo từng lô chứ không gộp một lần ở cuối: cần mốc thời gian của từng
    lượt gọi mới đếm đúng lượt/phút, mà một video dài dịch cả tiếng thì gộp
    cuối là mất sạch thông tin thời gian.
    """
    if not cues:
        return []

    settings = get_settings()
    translator = get_translator(model, api_key=api_key, base_url=base_url, provider=provider)
    #: Gắn vào TRANSLATOR chứ không báo sau mỗi lô: một lô lệch số dòng nở ra
    #: nhiều lượt gọi (chia đôi, rồi dịch từng dòng), báo theo lô sẽ đếm hụt
    #: hàng chục lần — xem ``_translate_with_guard`` và ``BaseTranslator``.
    if on_usage is not None:
        translator.on_usage = lambda u: on_usage(replace(u))
    merged_glossary = {**DEFAULT_GLOSSARY, **(glossary or {})}

    batches = chunk(cues, settings.llm_batch_size)
    total = len(batches)
    #: Bắn theo mốc dàn đều thay vì mọi lô — vẫn đủ MIN_MILESTONES kể cả khi
    #: ít lô (batch nhỏ), theo milestones().
    marks = milestones(total) if progress_cb else set()
    out: list[Cue] = []
    #: Dòng không dịch được, gom lại để cuối bước còn biết mình vừa làm gì.
    hong: list[str] = []

    for index, batch in enumerate(batches, start=1):
        _cho_cho_vua_nhip(dem_luot_gan_day, settings.llm_max_requests_per_min)
        texts = [c.text for c in batch]
        translated = _translate_with_guard(translator, texts, tone, merged_glossary, hong)
        out.extend(
            cue.with_text(text.strip() or cue.text)
            for cue, text in zip(batch, translated, strict=True)
        )
        if progress_cb and index in marks:
            progress_cb(percent_of(index, total))

    if len(out) != len(cues):  # chốt chặn cuối — không bao giờ được xảy ra
        raise TranslateError(f"Số dòng sau dịch ({len(out)}) khác đầu vào ({len(cues)})")

    #: Hỏng quá nhiều thì DỪNG, đừng trả về một bản "dịch" vẫn nguyên tiếng
    #: Trung. Quan sát ngày 2026-08-16: Google gỡ ``gemini-2.5-flash``, mọi
    #: lượt gọi trả 404, đường lui từng-dòng giữ nguyên cả 133 câu tiếng Trung
    #: — và bước này vẫn báo XONG. Video đi tiếp qua lồng tiếng, xoá chữ cứng,
    #: render, rồi người dùng mở lên mới thấy phụ đề vẫn là tiếng Trung.
    if len(hong) > len(cues) * TI_LE_HONG_COI_LA_CA_BUOC:
        raise TranslateError(
            f"Không dịch được {len(hong)}/{len(cues)} câu — bản dịch sẽ vẫn là tiếng "
            f"gốc nên dừng tại đây. Lỗi cuối: {hong[-1][:300]}"
        )
    if hong:
        log.warning("translate.mot_so_dong_giu_nguyen", so_dong=len(hong), tong=len(cues))

    log.info("translate.done", cues=len(out), batches=len(batches))
    return out


#: Lô nhỏ hơn mức này thì không chia nữa — chia tiếp chỉ tốn thêm lượt gọi mà
#: gần như không tăng cơ hội thành công, và mất hết ngữ cảnh của bản dịch.
LO_NHO_NHAT = 8


#: Quá tỉ lệ này số dòng KHÔNG dịch được thì coi như cả bước hỏng, không phải
#: vài dòng lẻ. Không đặt 0 vì có dòng dịch xong vẫn y nguyên một cách hợp lệ:
#: số, tên riêng, "OK". Nhưng quá một phần ba là chuyện khác hẳn.
TI_LE_HONG_COI_LA_CA_BUOC = 0.34


#: Mã HTTP mà chia nhỏ lô hay thử lại đều vô ích: model không tồn tại / bị gỡ,
#: khoá sai, khoá không có quyền. Lô nhỏ hơn cũng hỏng y hệt.
_LOI_VINH_VIEN = ("HTTP 400", "HTTP 401", "HTTP 403", "HTTP 404")


def _khong_the_thu_lai(loi: str) -> bool:
    return any(ma in loi for ma in _LOI_VINH_VIEN)


def _translate_with_guard(
    translator,
    texts: list[str],
    tone: str,
    glossary: dict[str, str],
    hong: list[str] | None = None,
) -> list[str]:
    """Gọi LLM, kiểm số dòng; lệch thì CHIA ĐÔI lô rồi thử lại.

    Vì sao không rơi thẳng xuống dịch từng dòng như bản đầu: đo thật ngày
    2026-08-14 trên video 672 câu với lô 100 — model trả 101 dòng cho 100 câu,
    và cơ chế cũ biến mỗi lô hỏng thành 100 lượt gọi riêng. Bốn lô sinh ra 189
    lượt thành công cộng 75 lượt bị từ chối, vào một model chỉ cho 15
    lượt/phút. Với API có hạn mức, dịch từng dòng là phương án ĐẮT NHẤT.

    Chia đôi giữ được lợi thế dịch theo lô (có ngữ cảnh, ít lượt gọi) mà vẫn
    thu hẹp dần vùng hỏng: 100 -> 2x50 -> 4x25 -> ... Chỉ khi lô đã nhỏ hơn
    ``LO_NHO_NHAT`` mới dịch từng dòng.
    """
    #: Chỗ gọi không quan tâm dòng nào hỏng thì vẫn chạy được — nhưng tầng
    #: trên PHẢI truyền vào, nếu không mất luôn chốt "hỏng quá nhiều thì dừng".
    if hong is None:
        hong = []

    for attempt in range(2):
        try:
            result = translator.translate_batch(texts, tone=tone, glossary=glossary)
        except TranslateError as exc:
            log.warning("translate.batch_failed", attempt=attempt, error=str(exc))
            #: Model bị gỡ hay khoá sai thì chia nhỏ lô cũng hỏng y hệt. Quan
            #: sát ngày 2026-08-16: một video 133 câu nở ra hàng chục lượt gọi
            #: 404 mất 40 giây, chỉ để đi tới cùng một kết luận biết từ lượt
            #: đầu. Ném thẳng lên cho người dùng đổi model.
            if _khong_the_thu_lai(str(exc)):
                raise
            continue

        if len(result) == len(texts):
            return result
        log.warning(
            "translate.count_mismatch",
            attempt=attempt,
            expected=len(texts),
            got=len(result),
        )

    if len(texts) >= LO_NHO_NHAT:
        giua = len(texts) // 2
        log.warning("translate.chia_doi_lo", tu=len(texts), thanh=giua)
        #: Ghép theo đúng thứ tự nửa đầu rồi nửa sau — đảo là phụ đề lệch hết,
        #: loại lỗi khó thấy nhất vì video vẫn chạy và vẫn có chữ.
        return _translate_with_guard(translator, texts[:giua], tone, glossary, hong) + (
            _translate_with_guard(translator, texts[giua:], tone, glossary, hong)
        )

    #: Hết đường chia — dịch từng dòng. Chậm và tốn, nhưng lúc này lô đã nhỏ
    #: nên thiệt hại có trần.
    log.warning("translate.fallback_line_by_line", count=len(texts))
    out: list[str] = []
    for text in texts:
        try:
            single = translator.translate_batch([text], tone=tone, glossary=glossary)
            if single:
                out.append(single[0])
                continue
            out.append(text)
        except TranslateError as exc:
            out.append(text)  # giữ nguyên tiếng Trung còn hơn mất dòng
            hong.append(str(exc))
            continue
        #: Trả về rỗng cũng là hỏng — chỉ là hỏng lặng lẽ hơn.
        hong.append("nhà cung cấp trả về rỗng")
    return out
