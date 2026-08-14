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


#: Cho test thay bằng đồng hồ giả — không ai muốn bài test chờ thật 60 giây.
_now = time.monotonic
_sleep = time.sleep

#: Cửa sổ trần lượt/phút của nhà cung cấp.
_CUA_SO_GIAY = 60.0


def chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _cho_cho_vua_nhip(moc_goi: list[float], tran_moi_phut: int) -> None:
    """Chờ trước khi gọi lượt tiếp theo, nếu 60 giây qua đã dùng hết trần.

    Retry khi bị từ chối chỉ chữa lỗi TẠM THỜI; trần tính theo phút là giới hạn
    CẤU TRÚC — bắn hết rồi bị chặn thì mỗi lượt bị từ chối vẫn tính vào hạn
    mức, càng bắn càng lún. Đo thật: video 672 câu chia 27 lượt vào model trần
    5 lượt/phút mất 3 TIẾNG.

    ``tran_moi_phut <= 0`` nghĩa là không khai trần — KHÔNG tự ý làm chậm khi
    người dùng chưa yêu cầu.
    """
    if tran_moi_phut <= 0:
        return

    bay_gio = _now()
    trong_cua_so = [t for t in moc_goi if bay_gio - t < _CUA_SO_GIAY]
    if len(trong_cua_so) < tran_moi_phut:
        return

    #: Chờ đúng tới lúc lượt CŨ NHẤT rơi khỏi cửa sổ, không chờ thừa.
    cu_nhat = min(trong_cua_so)
    con_lai = _CUA_SO_GIAY - (bay_gio - cu_nhat)
    if con_lai > 0:
        log.info("translate.pacing", cho_giay=round(con_lai, 1), tran=tran_moi_phut)
        _sleep(con_lai)


def translate_cues(
    cues: list[Cue],
    *,
    tone: str = "doi_thuong",
    glossary: dict[str, str] | None = None,
    progress_cb=None,
    on_usage=None,
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
    translator = get_translator()
    merged_glossary = {**DEFAULT_GLOSSARY, **(glossary or {})}

    batches = chunk(cues, settings.llm_batch_size)
    total = len(batches)
    #: Bắn theo mốc dàn đều thay vì mọi lô — vẫn đủ MIN_MILESTONES kể cả khi
    #: ít lô (batch nhỏ), theo milestones().
    marks = milestones(total) if progress_cb else set()
    out: list[Cue] = []

    moc_goi: list[float] = []
    for index, batch in enumerate(batches, start=1):
        _cho_cho_vua_nhip(moc_goi, settings.llm_max_requests_per_min)
        moc_goi.append(_now())
        texts = [c.text for c in batch]
        translated = _translate_with_guard(translator, texts, tone, merged_glossary)
        out.extend(
            cue.with_text(text.strip() or cue.text)
            for cue, text in zip(batch, translated, strict=True)
        )
        if on_usage is not None:
            on_usage(replace(translator.usage))
        if progress_cb and index in marks:
            progress_cb(percent_of(index, total))

    if len(out) != len(cues):  # chốt chặn cuối — không bao giờ được xảy ra
        raise TranslateError(f"Số dòng sau dịch ({len(out)}) khác đầu vào ({len(cues)})")

    log.info("translate.done", cues=len(out), batches=len(batches))
    return out


def _translate_with_guard(
    translator, texts: list[str], tone: str, glossary: dict[str, str]
) -> list[str]:
    """Gọi LLM, kiểm số dòng, retry, cuối cùng mới dịch từng dòng."""
    for attempt in range(2):
        try:
            result = translator.translate_batch(texts, tone=tone, glossary=glossary)
        except TranslateError as exc:
            log.warning("translate.batch_failed", attempt=attempt, error=str(exc))
            continue

        if len(result) == len(texts):
            return result
        log.warning(
            "translate.count_mismatch",
            attempt=attempt,
            expected=len(texts),
            got=len(result),
        )

    # Fallback: dịch từng dòng. Chậm và tốn hơn nhưng luôn đúng số lượng.
    log.warning("translate.fallback_line_by_line", count=len(texts))
    out: list[str] = []
    for text in texts:
        try:
            single = translator.translate_batch([text], tone=tone, glossary=glossary)
            out.append(single[0] if single else text)
        except TranslateError:
            out.append(text)  # giữ nguyên tiếng Trung còn hơn mất dòng
    return out
