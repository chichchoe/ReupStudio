"""Ghép câu dịch với câu gốc — dùng chung cho API và worker.

Nằm ở ``reup_core`` chứ không ở ``apps/worker``: API cần hàm này để trả bảng
đối chiếu, mà API KHÔNG được import code worker (xem docstring
``api/src/services/task_bridge.py``).

Hàm THUẦN: không chạm DB, không import celery.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CauDon:
    """Một câu phụ đề tối giản — chỉ những gì việc ghép cần."""

    i: int
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class CapDoiChieu:
    """Một dòng bảng đối chiếu: câu dịch và (các) câu gốc cùng khoảng thời gian."""

    i: int
    start: float
    end: float
    dich: str
    #: Các câu gốc chồng thời gian, nối bằng " / ". Rỗng nếu không có câu nào.
    goc: str


def ghep_theo_thoi_gian(dich: list[CauDon], goc: list[CauDon]) -> list[CapDoiChieu]:
    """Ghép câu dịch với câu gốc theo GIAO NHAU THỜI GIAN, không theo chỉ số.

    Vì sao không theo chỉ số: ``subtitle_format.format_cues`` gộp câu ngắn,
    tách câu dài rồi đánh số lại từ 0 — sau bước đó ``dich[i]`` không còn là
    bản dịch của ``goc[i]``. Đo trên dữ liệu thật ngày 2026-08-20: 8/10 video
    lệch số câu.

    Hai câu coi là cùng chỗ khi khoảng thời gian CHỒNG LẤN thật sự:
    ``goc.start < dich.end and goc.end > dich.start``. Chạm biên (câu này kết
    thúc đúng lúc câu kia bắt đầu) KHÔNG tính — nếu tính thì mỗi câu dịch đều
    dính thêm câu gốc liền trước.

    Cả hai danh sách phải đã sắp theo ``start`` tăng dần (mọi nơi trong
    pipeline đều giữ thứ tự này) — nhờ vậy quét được bằng con trỏ, không phải
    so từng cặp.
    """
    ra: list[CapDoiChieu] = []
    dau = 0

    for cau in dich:
        #: Bỏ qua hẳn câu gốc đã kết thúc trước khi câu dịch này bắt đầu. An
        #: toàn vì ``dich`` sắp tăng dần: câu dịch sau còn bắt đầu muộn hơn.
        while dau < len(goc) and goc[dau].end <= cau.start:
            dau += 1

        phan: list[str] = []
        vi_tri = dau
        while vi_tri < len(goc) and goc[vi_tri].start < cau.end:
            if goc[vi_tri].end > cau.start:
                phan.append(goc[vi_tri].text)
            vi_tri += 1

        ra.append(
            CapDoiChieu(
                i=cau.i,
                start=cau.start,
                end=cau.end,
                dich=cau.text,
                goc=" / ".join(phan),
            )
        )

    return ra


def tu_dicts(items: list[dict]) -> list[CauDon]:
    """Đọc cột ``subtitles.cues`` (JSON) thành ``CauDon``, bỏ qua khoá lạ."""
    return [
        CauDon(
            i=int(d["i"]),
            start=float(d["start"]),
            end=float(d["end"]),
            text=str(d["text"]),
        )
        for d in items
    ]
