"""Chuẩn hoá phụ đề cho dễ đọc trên video ngắn.

Quy tắc (đọc từ cấu hình):
- Tối đa 2 dòng mỗi khung, mỗi dòng tối đa 42 ký tự
- Mỗi khung hiển thị tối thiểu 1.2 giây
- Gộp các khung quá ngắn với khung kế tiếp
- Không để hai khung chồng thời gian nhau

Đây là hàm THUẦN — bắt buộc có test tự động (xem tests/test_subtitle_format.py).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..milestones import milestones, percent_of
from .cues import Cue


@dataclass(frozen=True)
class FormatOptions:
    max_chars_per_line: int = 42
    max_lines: int = 2
    min_duration: float = 1.2
    #: Khung ngắn hơn ngưỡng này sẽ được gộp với khung sau.
    merge_below: float = 0.5
    #: Khoảng hở tối thiểu giữa hai khung liên tiếp (giây).
    min_gap: float = 0.04


def wrap_text(text: str, max_chars: int, max_lines: int) -> str:
    """Ngắt dòng theo từ, không cắt giữa từ.

    Nếu vượt quá ``max_lines``, phần thừa bị dồn vào dòng cuối (thà chữ hơi dài
    còn hơn mất nội dung).
    """
    words = text.split()
    if not words:
        return ""

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    if len(lines) > max_lines:
        head = lines[: max_lines - 1]
        tail = " ".join(lines[max_lines - 1 :])
        lines = [*head, tail]
    return "\n".join(lines)


def merge_short_cues(cues: list[Cue], opts: FormatOptions) -> list[Cue]:
    """Gộp khung quá ngắn vào khung kế tiếp để mắt kịp đọc."""
    if not cues:
        return []

    merged: list[Cue] = []
    pending: Cue | None = None

    for cue in cues:
        if pending is not None:
            cue = Cue(
                i=pending.i,
                start=pending.start,
                end=cue.end,
                text=f"{pending.text} {cue.text}".strip(),
            )
            pending = None
        if cue.duration < opts.merge_below:
            pending = cue
            continue
        merged.append(cue)

    if pending is not None:  # khung cuối quá ngắn — nối vào khung trước
        if merged:
            last = merged[-1]
            merged[-1] = Cue(
                last.i, last.start, pending.end, f"{last.text} {pending.text}".strip()
            )
        else:
            merged.append(pending)
    return merged


def enforce_timing(cues: list[Cue], opts: FormatOptions) -> list[Cue]:
    """Đảm bảo thời lượng tối thiểu và không chồng lấn."""
    result: list[Cue] = []
    for index, cue in enumerate(cues):
        start = cue.start
        end = max(cue.end, start + opts.min_duration)

        if result:
            prev = result[-1]
            if start < prev.end + opts.min_gap:
                start = prev.end + opts.min_gap
                end = max(end, start + opts.min_duration)

        # Không lấn sang khung kế tiếp
        if index + 1 < len(cues):
            next_start = cues[index + 1].start
            if end > next_start - opts.min_gap:
                end = max(start + 0.3, next_start - opts.min_gap)

        result.append(Cue(cue.i, round(start, 3), round(end, 3), cue.text))
    return result


def format_cues(
    cues: list[Cue],
    opts: FormatOptions | None = None,
    *,
    progress_cb: Callable[[int], None] | None = None,
) -> list[Cue]:
    """Pipeline chuẩn hoá đầy đủ: bỏ rỗng → gộp ngắn → ngắt dòng → chỉnh thời gian.

    ``progress_cb`` (nếu có) được gọi khi duyệt qua bước ngắt dòng, theo các
    mốc từ ``milestones()`` — đảm bảo ít nhất 5 mốc phần trăm khác nhau kể cả
    khi ít cue.
    """
    opts = opts or FormatOptions()

    cleaned = [
        Cue(c.i, c.start, c.end, " ".join(c.text.split()))
        for c in cues
        if c.text and c.text.strip()
    ]
    if not cleaned:
        return []

    merged = merge_short_cues(cleaned, opts)
    total = len(merged)
    marks = milestones(total) if progress_cb else set()

    wrapped: list[Cue] = []
    for done, c in enumerate(merged, start=1):
        wrapped.append(c.with_text(wrap_text(c.text, opts.max_chars_per_line, opts.max_lines)))
        if progress_cb and done in marks:
            progress_cb(percent_of(done, total))

    timed = enforce_timing(wrapped, opts)
    return [Cue(index, c.start, c.end, c.text) for index, c in enumerate(timed)]
