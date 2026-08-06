"""Tiện ích thuần tính mốc tiến trình.

Tách khỏi ``progress.py`` vì ``progress.py`` có ``import redis`` ở đầu file —
tầng ``pipeline/`` không được kéo Redis vào (xem CLAUDE.md). Module này không
import gì từ ``pipeline/``, ``tasks/`` hay Redis, nên dùng chung được ở mọi
tầng. ĐỪNG gộp ngược các hàm này vào ``progress.py``.
"""

from __future__ import annotations

MIN_MILESTONES = 5


def milestones(total: int, count: int = MIN_MILESTONES) -> set[int]:
    """Chỉ số phần tử (đếm từ 1) mà tới đó thì nên bắn tiến trình.

    Khi ``total`` bé hơn hoặc bằng ``count``, bắn ở mọi phần tử (không đủ phần
    tử để dàn đều). Khi ``total`` lớn hơn ``count``, dàn đều ``count`` mốc,
    mốc cuối luôn là ``total`` — nhờ vậy step nào lặp qua danh sách cũng có
    ít nhất ``count`` mốc, kể cả danh sách ngắn.
    """
    if total <= 0:
        return set()
    if total <= count:
        return set(range(1, total + 1))
    return {total * i // count for i in range(1, count + 1)}


def percent_of(done: int, total: int, *, lo: int = 0, hi: int = 100) -> int:
    """Quy đổi ``done/total`` sang phần trăm trong khoảng ``[lo, hi]``.

    Luôn kẹp trong ``[lo, hi]`` và đơn điệu không giảm theo ``done``.
    """
    if total <= 0:
        return hi
    ratio = min(1.0, max(0.0, done / total))
    return round(lo + ratio * (hi - lo))
