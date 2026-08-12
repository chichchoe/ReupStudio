"""Chia video thành các tập theo giới hạn thời lượng nền tảng (M4-WK-04).

Hàm THUẦN: không đụng DB, không đụng ffmpeg, không import celery.

Mặc định hiện tại của hệ thống: ``max_duration_sec = 0`` được seed cho cả 5
nền tảng trong bảng ``platform_limits`` — nghĩa là KHÔNG giới hạn thời lượng,
người dùng tự xem lại video trước khi đăng chứ không muốn công cụ tự cắt theo
con số phỏng đoán. Đây là đường chạy PHỔ BIẾN NHẤT của hệ thống hiện nay, nên
``split_by_duration`` xử lý nó ngay đầu hàm: trả đúng một tập phủ toàn bộ
video, không chia gì cả.

Khi người dùng bật giới hạn lên (``PATCH /platform-limits/{platform}``), video
dài hơn giới hạn phải được chia — nhưng không được cắt giữa câu, vì cắt hụt
câu làm người xem bỏ đi ngay. ``cut_points`` (từ khoảng lặng giữa các cue phụ
đề, xem ``silence_cut_points``) là các mốc ưu tiên cắt; thuật toán chọn mốc
gần vị trí lý tưởng nhất mà vẫn không vượt ``max_duration_sec``.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from ...errors import InvalidSplitLimitError
from ..cues import Cue


@dataclass(frozen=True)
class Part:
    """Một tập sau khi chia, đơn vị giây trên trục thời gian video gốc."""

    index: int  # 1-based
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def split_by_duration(
    total_sec: float,
    max_duration_sec: int,
    *,
    cut_points: list[float] | None = None,
    min_part_sec: float = 10.0,
) -> list[Part]:
    """Chia video thành các tập không dài quá ``max_duration_sec``.

    ``cut_points`` là các mốc giây ƯU TIÊN cắt (khoảng lặng giữa câu, lấy từ cue
    phụ đề). Thuật toán chọn mốc gần vị trí lý tưởng nhất mà vẫn không vượt
    ``max_duration_sec``.

    Quy tắc:
    - ``max_duration_sec == 0`` → không giới hạn, trả đúng MỘT tập phủ toàn bộ.
    - Không tập nào dài hơn ``max_duration_sec``.
    - Các tập phủ kín ``[0, total_sec]``, không chồng lấn, không hở.
    - Tập cuối không ngắn hơn ``min_part_sec``, MIỄN LÀ điều đó còn khả thi
      trong giới hạn ``max_duration_sec`` (``min_part_sec < max_duration_sec``).
      ``_chon_bien`` nhìn trước để lùi mốc cắt ngay khi chọn, tránh sinh ra
      đoạn cuối cụt lủn rồi phải gộp ngược — xem lý do trong docstring của nó.
    - Không có ``cut_points`` nào dùng được thì cắt đều.
    """
    if total_sec < 0:
        raise InvalidSplitLimitError(f"total_sec phải >= 0, nhận {total_sec}")
    if max_duration_sec < 0:
        raise InvalidSplitLimitError(
            f"max_duration_sec phải >= 0 (0 nghĩa là không giới hạn), "
            f"nhận {max_duration_sec}"
        )
    if min_part_sec < 0:
        raise InvalidSplitLimitError(f"min_part_sec phải >= 0, nhận {min_part_sec}")

    # Đường chạy phổ biến nhất: không giới hạn → một tập duy nhất, không chia.
    if max_duration_sec == 0 or total_sec <= max_duration_sec:
        return [Part(index=1, start=0.0, end=total_sec)]

    # Không có bước gộp hậu kỳ ở đây: _chon_bien đã nhìn trước min_part_sec
    # ngay khi chọn mốc cắt (xem docstring của nó) — gộp tập cuối lại SAU khi
    # cắt xong là bất khả thi, vì hễ vòng lặp còn cắt tiếp thì đoạn còn lại
    # lúc đó đã vượt max_duration_sec rồi, nên 2 tập cuối cộng lại luôn vượt.
    boundaries = _chon_bien(total_sec, max_duration_sec, cut_points or [], min_part_sec)

    return [
        Part(index=i, start=start, end=end)
        for i, (start, end) in enumerate(pairwise(boundaries), start=1)
    ]


def _chon_bien(
    total_sec: float,
    max_duration_sec: int,
    cut_points: list[float],
    min_part_sec: float,
) -> list[float]:
    """Chọn các mốc biên tập ``0 = b0 < b1 < ... < bn = total_sec``.

    Đi từ đầu, mỗi bước đặt vị trí lý tưởng là ``diem_hien_tai + max_duration_sec``
    rồi tìm mốc ``cut_points`` gần nhất trong phạm vi ``(diem_hien_tai, lý_tưởng]``
    (không vượt giới hạn). Không có mốc nào phù hợp thì cắt đúng tại vị trí lý
    tưởng (cắt đều).

    Nhìn trước ``min_part_sec``: nếu cắt tại vị trí lý tưởng sẽ để lại đoạn
    CUỐI ngắn hơn ``min_part_sec``, lùi giới hạn tìm mốc về ``total_sec -
    min_part_sec`` để đoạn cuối đủ dài ngay từ đầu.

    Bắt buộc xử lý trước, không có bước gộp hậu kỳ nào sửa lại được: hễ vòng
    lặp còn phải cắt tiếp (``total_sec - current > max_duration_sec``) thì
    đoạn còn lại tại thời điểm đó ĐÃ vượt ``max_duration_sec`` — đó chính là
    lý do phải cắt. Vậy nên tổng của tập áp chót và tập cuối luôn luôn vượt
    quá ``max_duration_sec``, gộp ngược hai tập liền kề ở cuối sẽ không bao
    giờ vừa giới hạn (đã thử và bỏ cách này — xem lịch sử commit). Vì vậy
    phải né đoạn cuối quá ngắn NGAY LÚC CHỌN MỐC.
    """
    candidates = sorted(p for p in cut_points if 0 < p < total_sec)

    boundaries = [0.0]
    current = 0.0
    while total_sec - current > max_duration_sec:
        ideal = current + max_duration_sec
        gioi_han = ideal
        # min_part_sec >= max_duration_sec là cấu hình không khả thi (không
        # thể đảm bảo tập nào cũng đủ min_part_sec trong giới hạn max) — bỏ
        # qua nhìn trước, chấp nhận tập cuối có thể ngắn hơn min_part_sec.
        if min_part_sec < max_duration_sec and 0 < total_sec - ideal < min_part_sec:
            gioi_han = total_sec - min_part_sec
        # Mốc ưu tiên nằm trong (current, gioi_han], càng gần gioi_han càng
        # tốt, và phải đủ xa current để không tạo tập rỗng/quá ngắn do làm
        # tròn.
        best: float | None = None
        for p in candidates:
            if current < p <= gioi_han and (best is None or p > best):
                best = p
        cut = best if best is not None else gioi_han
        boundaries.append(cut)
        current = cut
    boundaries.append(total_sec)
    return boundaries


def silence_cut_points(cues: list[Cue], *, min_gap: float = 0.35) -> list[float]:
    """Mốc cắt an toàn = giữa hai cue liên tiếp cách nhau ``>= min_gap`` giây.

    Cắt ở giữa khoảng lặng giữa hai câu, không phải giữa câu — người xem không
    bị hụt vì đang xem tập trước dừng đúng lúc câu vừa kết thúc.
    """
    if len(cues) < 2:
        return []

    ordered = sorted(cues, key=lambda c: c.start)
    points: list[float] = []
    for prev, nxt in pairwise(ordered):
        gap = nxt.start - prev.end
        if gap >= min_gap:
            points.append((prev.end + nxt.start) / 2)
    return points
