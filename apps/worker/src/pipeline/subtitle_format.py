"""Chuẩn hoá phụ đề cho dễ đọc trên video ngắn.

Quy tắc (đọc từ cấu hình):
- Tối đa 2 dòng mỗi khung, mỗi dòng tối đa 42 ký tự
- Mỗi khung hiển thị tối thiểu 1.2 giây
- Gộp các khung quá ngắn với khung kế tiếp
- CHIA khung quá dài thành nhiều khung nối tiếp (xem ``split_long_cues``)
- Không để hai khung chồng thời gian nhau

Thứ tự các bước trong ``format_cues`` là bắt buộc: chia khung dài phải chạy
TRƯỚC khi ngắt dòng, vì ``wrap_text`` dồn phần thừa vào dòng cuối và sau đó
không còn gì để cứu.

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


#: Dấu ưu tiên cắt, xếp theo mức "trọn ý" giảm dần. Có cả dấu câu tiếng Trung
#: vì cue nguồn thường còn nguyên dấu của bản gốc sau khi dịch.
_DAU_NGAT = ("。", ".", "！", "!", "？", "?", "；", ";", "，", ",", "、")

#: Chỉ cắt ở dấu câu khi mảnh đã dài ít nhất chừng này so với độ dài mục tiêu.
#: Không có ngưỡng thì "Được rồi," (9 ký tự) cắt ngay ký tự thứ 9, tiêu một mảnh
#: cho gần như không có chữ, rồi phần còn lại dồn hết vào mảnh cuối — quan sát
#: trên bản render 2026-08-15.
_TI_LE_UU_TIEN_DAU = 0.6

#: Khi thời lượng không cho phép chia đủ nhỏ, nới độ dài mục tiêu theo bước này
#: cho tới khi số mảnh vừa số khung thời gian cho phép.
_BUOC_NOI_MUC = 1.3


def split_long_cues(cues: list[Cue], opts: FormatOptions) -> list[Cue]:
    """Chia cue quá dài thành nhiều cue nối tiếp nhau.

    VÌ SAO CẦN: quan sát trên ảnh render thật (2026-08-14), phụ đề chiếm 8 dòng
    che kín mặt người dù cấu hình để tối đa 2 dòng. Whisper gộp cả đoạn nói liền
    mạch thành MỘT cue 19 giây ~200 ký tự; ``wrap_text`` gặp cue quá dài thì dồn
    phần thừa vào dòng cuối (cố ý — thà chữ dài còn hơn mất chữ), rồi libass tự
    ngắt tiếp thành 8 dòng. Không có bước này thì ``max_lines`` chỉ là con số
    trang trí.

    Thời lượng chia theo SỐ KÝ TỰ chứ không chia đều: chia đều làm câu dài trôi
    quá nhanh để đọc kịp.

    KHÔNG chia nhỏ hơn ``min_duration``. Một cue hơi dài vẫn đọc được; một chuỗi
    cue nhấp nháy 0,4 giây thì không.
    """
    gioi_han = opts.max_chars_per_line * opts.max_lines
    ra: list[Cue] = []

    for cue in cues:
        text = cue.text.strip()
        if len(text) <= gioi_han:
            ra.append(cue)
            continue

        #: Số phần cần chia theo độ dài, nhưng bị chặn trên bởi thời lượng: mỗi
        #: phần phải đủ ``min_duration`` để người xem đọc kịp.
        can_theo_chu = -(-len(text) // gioi_han)  # chia lấy trần
        cho_phep_theo_gio = max(1, int(cue.duration // opts.min_duration))
        so_phan = min(can_theo_chu, cho_phep_theo_gio)

        if so_phan <= 1:
            ra.append(cue)
            continue

        phan_text = _chia_van_ban(text, so_phan, gioi_han, cho_phep_theo_gio)
        ra.extend(_rai_thoi_gian(cue, phan_text))

    #: Đánh số lại liên tục — số trùng nhau làm file SRT/ASS khó đọc khi debug.
    return [Cue(i, c.start, c.end, c.text) for i, c in enumerate(ra)]


def _chia_van_ban(text: str, so_phan: int, gioi_han: int, so_phan_toi_da: int) -> list[str]:
    """Chia chuỗi thành các mảnh dài xấp xỉ nhau, không mảnh nào vượt ``gioi_han``.

    Cách cũ đếm ngược "còn được cắt mấy lần nữa" và cắt ở dấu câu đầu tiên gặp
    được. Nó tiêu hết lượt cắt vào mấy dấu phẩy sớm rồi dồn phần còn lại vào
    mảnh cuối — vẫn tràn, chỉ là tràn ở chỗ khác.

    Cách này gói theo ĐỘ DÀI MỤC TIÊU với một trần cứng, nên mảnh cuối không còn
    là nơi chứa phần thừa.

    Khi thời lượng cue không đủ để chia nhỏ tới mức đó, nới dần độ dài mục tiêu:
    thà một mảnh hơi dài còn hơn chuỗi mảnh nhấp nháy dưới ``min_duration``.
    """
    muc = len(text) / so_phan
    phan = _gom_theo_muc(text, muc, gioi_han)

    while len(phan) > so_phan_toi_da and muc < len(text):
        muc *= _BUOC_NOI_MUC
        phan = _gom_theo_muc(text, muc, gioi_han)

    return phan


def _gom_theo_muc(text: str, muc: float, gioi_han: int) -> list[str]:
    """Gói từ thành mảnh dài khoảng ``muc``, không mảnh nào vượt trần.

    Trần thật là ``max(gioi_han, muc)``: khi ``muc`` bị nới lên vì thiếu thời
    gian, trần phải nới theo, nếu không vòng nới ở trên chạy mãi không đổi.
    """
    tran = max(float(gioi_han), muc)
    phan: list[str] = []
    hien_tai: list[str] = []

    def chot() -> None:
        nonlocal hien_tai
        if hien_tai:
            phan.append(" ".join(hien_tai))
            hien_tai = []

    for t in text.split():
        if hien_tai and len(" ".join([*hien_tai, t])) > tran:
            chot()
        hien_tai.append(t)

        dai = len(" ".join(hien_tai))
        cat_o_dau_cau = t.endswith(_DAU_NGAT) and dai >= muc * _TI_LE_UU_TIEN_DAU
        if cat_o_dau_cau or dai >= muc:
            chot()

    chot()
    return phan or [text]


def _rai_thoi_gian(cue: Cue, phan_text: list[str]) -> list[Cue]:
    """Rải mốc thời gian cho các mảnh, tỉ lệ theo số ký tự.

    Mảnh cuối lấy đúng ``cue.end`` thay vì cộng dồn — cộng dồn số thực sẽ lệch
    vài phần nghìn giây và để hở một khe nhỏ ở cuối.
    """
    tong_chu = sum(len(p) for p in phan_text) or 1
    ra: list[Cue] = []
    moc = cue.start

    for chi_so, p in enumerate(phan_text):
        cuoi_cung = chi_so == len(phan_text) - 1
        ket = cue.end if cuoi_cung else moc + cue.duration * len(p) / tong_chu
        ra.append(Cue(cue.i, moc, ket, p))
        moc = ket
    return ra


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
            merged[-1] = Cue(last.i, last.start, pending.end, f"{last.text} {pending.text}".strip())
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
    #: CHIA cue quá dài TRƯỚC khi ngắt dòng. Đảo thứ tự thì ``wrap_text`` đã kịp
    #: dồn phần thừa vào dòng cuối, và bước chia không còn gì để cứu — đó đúng
    #: là đường đã cho ra phụ đề 8 dòng che kín mặt người trên bản render thật.
    merged = split_long_cues(merged, opts)
    total = len(merged)
    marks = milestones(total) if progress_cb else set()

    wrapped: list[Cue] = []
    for done, c in enumerate(merged, start=1):
        wrapped.append(c.with_text(wrap_text(c.text, opts.max_chars_per_line, opts.max_lines)))
        if progress_cb and done in marks:
            progress_cb(percent_of(done, total))

    timed = enforce_timing(wrapped, opts)
    return [Cue(index, c.start, c.end, c.text) for index, c in enumerate(timed)]
