"""Dịch phụ đề Trung → Việt.

Ba điểm bắt buộc (xem docs/03-BACKLOG-CONG-VIEC.md, mục M1-WK-05):
1. Gửi cả LÔ, không gửi từng dòng — dịch rời rạc cho ra bản dịch không ngữ cảnh.
2. KIỂM TRA số dòng trả về; sai thì retry, retry vẫn sai thì dịch từng dòng.
3. Glossary ép cứng để tên riêng và xưng hô nhất quán giữa các tập.
"""

from __future__ import annotations

from reup_core.logging import get_logger

from ..config import get_settings
from ..errors import TranslateError
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


def chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def translate_cues(
    cues: list[Cue],
    *,
    tone: str = "doi_thuong",
    glossary: dict[str, str] | None = None,
    progress_cb=None,
) -> list[Cue]:
    if not cues:
        return []

    settings = get_settings()
    translator = get_translator()
    merged_glossary = {**DEFAULT_GLOSSARY, **(glossary or {})}

    batches = chunk(cues, settings.llm_batch_size)
    out: list[Cue] = []

    for index, batch in enumerate(batches):
        texts = [c.text for c in batch]
        translated = _translate_with_guard(translator, texts, tone, merged_glossary)
        out.extend(
            cue.with_text(text.strip() or cue.text)
            for cue, text in zip(batch, translated, strict=True)
        )
        if progress_cb:
            progress_cb(int((index + 1) / len(batches) * 100))

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
