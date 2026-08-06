"""Chống trùng video: MD5 (trùng từng byte) + pHash (trùng nội dung).

Hai lớp bổ sung nhau:

* **MD5** — bắt trường hợp tải lại đúng file cũ. Rẻ, chính xác tuyệt đối, nhưng
  đổi một byte metadata là hỏng.
* **pHash** — bắt bản đã mã hoá lại, đổi độ phân giải, đổi bitrate hoặc thêm
  viền. So sánh bằng khoảng cách Hamming, không bao giờ bằng dấu ``==``.

pHash một video = ghép pHash của ``frames`` khung rải đều. Mỗi khung 64 bit
(16 ký tự hex), mặc định 4 khung → 64 ký tự hex, vừa đúng cột ``videos.phash``.

Hàm thuần: không import celery, không chạm DB.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from reup_core.logging import get_logger

from ..errors import DedupError
from ..ffmpeg.frames import extract_gray_frames, sample_timestamps
from ..ffmpeg.probe import probe

log = get_logger(__name__)

#: Ảnh xám 32×32 trước khi DCT — đủ chi tiết mà DCT vẫn nhanh.
PHASH_GRID = 32
#: Chỉ giữ góc trên-trái 8×8 hệ số DCT (tần số thấp = bố cục, bỏ nhiễu nén).
PHASH_LOW_FREQ = 8
PHASH_BITS_PER_FRAME = PHASH_LOW_FREQ * PHASH_LOW_FREQ  # 64
PHASH_HEX_PER_FRAME = PHASH_BITS_PER_FRAME // 4  # 16
#: Số khung mặc định. Đổi số này là đổi độ dài chuỗi hash → phải tính lại toàn bộ.
PHASH_DEFAULT_FRAMES = 4

MD5_CHUNK_BYTES = 1 << 20


@dataclass(frozen=True)
class Fingerprint:
    """Dấu vân tay của một file video."""

    md5: str
    phash: str

    @property
    def frames(self) -> int:
        return len(self.phash) // PHASH_HEX_PER_FRAME


# --------------------------------------------------------------------------- #
# MD5
# --------------------------------------------------------------------------- #


def file_md5(path: Path, chunk_size: int = MD5_CHUNK_BYTES) -> str:
    """MD5 của cả file. Đọc theo khối để không nạp cả video vào RAM."""
    digest = hashlib.md5()
    with path.open("rb") as fh:
        while block := fh.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# DCT — tự viết, không kéo numpy/scipy vào worker
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=8)
def _cos_table(n: int, keep: int) -> tuple[tuple[float, ...], ...]:
    """``table[k][i] = cos(pi/n * (i + 0.5) * k)`` — nhân tử của DCT-II.

    Bảng phụ thuộc duy nhất vào kích thước nên tính một lần rồi dùng lại.
    """
    return tuple(
        tuple(math.cos(math.pi / n * (i + 0.5) * k) for i in range(n))
        for k in range(keep)
    )


def _dct_low_freq(matrix: list[list[float]], keep: int) -> list[list[float]]:
    """DCT-II hai chiều, chỉ trả góc trên-trái ``keep × keep``.

    Tách rời theo hàng rồi theo cột, và bỏ luôn các hệ số tần số cao không dùng
    tới: 32×32 chỉ còn ~10k phép nhân thay vì 1M nếu làm thẳng công thức 2D.
    Hệ số KHÔNG chuẩn hoá — chỉ so sánh tương đối nên hằng số nhân không đổi kết quả.
    """
    n = len(matrix)
    table = _cos_table(n, keep)
    rows = [[sum(row[i] * table[k][i] for i in range(n)) for k in range(keep)] for row in matrix]
    return [
        [sum(rows[i][x] * table[k][i] for i in range(n)) for x in range(keep)]
        for k in range(keep)
    ]


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


# --------------------------------------------------------------------------- #
# pHash
# --------------------------------------------------------------------------- #


def phash_from_gray(
    pixels: bytes, *, grid: int = PHASH_GRID, keep: int = PHASH_LOW_FREQ
) -> int:
    """pHash 64 bit của một ảnh xám thô ``grid × grid``.

    Mỗi bit = "hệ số DCT này có lớn hơn trung vị không". So với trung vị (không
    phải trung bình) nên chỉnh sáng cả ảnh không làm đổi hash.
    """
    expected = grid * grid
    if len(pixels) != expected:
        raise DedupError(f"Ảnh xám phải có đúng {expected} byte, nhận {len(pixels)}")

    matrix = [[float(pixels[y * grid + x]) for x in range(grid)] for y in range(grid)]
    low = _dct_low_freq(matrix, keep)
    flat = [value for row in low for value in row]

    #: Bỏ hệ số DC (flat[0] — độ sáng trung bình) khi tính trung vị: nó lớn hơn
    #: mọi hệ số khác vài bậc và sẽ kéo lệch ngưỡng.
    threshold = _median(flat[1:])

    bits = 0
    for value in flat:
        bits = (bits << 1) | int(value > threshold)
    return bits


def frame_phash_hex(pixels: bytes, *, grid: int = PHASH_GRID, keep: int = PHASH_LOW_FREQ) -> str:
    width = (keep * keep) // 4
    return f"{phash_from_gray(pixels, grid=grid, keep=keep):0{width}x}"


def video_phash(
    path: Path,
    *,
    frames: int = PHASH_DEFAULT_FRAMES,
    duration_sec: float | None = None,
) -> str:
    """pHash của cả video: ghép pHash của ``frames`` khung rải đều.

    Idempotent: cùng một file luôn cho cùng chuỗi vì mốc lấy mẫu tính từ thời
    lượng, không phải từ số khung đã giải mã.
    """
    if duration_sec is None:
        duration_sec = probe(path).duration_sec

    timestamps = sample_timestamps(duration_sec, frames)
    grays = extract_gray_frames(path, timestamps, PHASH_GRID)
    value = "".join(frame_phash_hex(g) for g in grays)
    log.debug("dedup.phash", path=str(path), frames=frames, phash=value)
    return value


def fingerprint(path: Path, *, frames: int = PHASH_DEFAULT_FRAMES) -> Fingerprint:
    """MD5 + pHash trong một lần gọi."""
    return Fingerprint(md5=file_md5(path), phash=video_phash(path, frames=frames))


# --------------------------------------------------------------------------- #
# So sánh
# --------------------------------------------------------------------------- #


def phash_distance(left: str, right: str) -> int:
    """Số bit khác nhau giữa hai pHash (khoảng cách Hamming).

    0 = giống hệt. Tối đa = số bit của chuỗi.
    """
    if len(left) != len(right):
        raise DedupError(
            f"Hai pHash khác độ dài ({len(left)} vs {len(right)}), không so sánh được"
        )
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError as exc:
        raise DedupError(f"pHash không phải chuỗi hex: {exc}") from exc


def is_similar_phash(left: str | None, right: str | None, *, max_distance: int) -> bool:
    """Hai video có được coi là trùng nội dung không.

    Thiếu hash hoặc hash sinh bằng số khung khác nhau → trả ``False``. Thà bỏ
    sót một bản trùng còn hơn xoá nhầm một video hợp lệ.
    """
    if not left or not right or len(left) != len(right):
        return False
    return phash_distance(left, right) <= max_distance
