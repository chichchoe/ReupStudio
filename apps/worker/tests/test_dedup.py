"""M2-WK-02 — chống trùng bằng md5 + pHash.

Chỉ test phần thuần tính toán (băm, DCT, so khoảng cách). Phần trích khung bằng
FFmpeg kiểm bằng ``scripts/try_dedup.py`` trên file thật.
"""

from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path

import pytest

from src.errors import DedupError
from src.pipeline.dedup import (
    PHASH_GRID,
    PHASH_HEX_PER_FRAME,
    Fingerprint,
    _dct_low_freq,
    file_md5,
    frame_phash_hex,
    is_similar_phash,
    phash_distance,
    phash_from_gray,
)

N = PHASH_GRID * PHASH_GRID


def _frame(seed: int = 0) -> bytes:
    """Khung hình giả lập: tổng vài sóng tần số thấp, giống bố cục ảnh thật.

    Giá trị nằm trong [40, 200] để phép chỉnh sáng ±20 trong test không bị chặn
    ở 0/255 — chặn biên là mất thông tin, sẽ làm hỏng phép đo chứ không phải
    hash sai.
    """
    rnd = random.Random(seed)
    waves = [(rnd.uniform(0.5, 3.5), rnd.uniform(0.5, 3.5), rnd.uniform(-1, 1)) for _ in range(5)]
    pixels = []
    for y in range(PHASH_GRID):
        for x in range(PHASH_GRID):
            value = sum(
                amp
                * math.sin(math.pi * fx * (x + 0.5) / PHASH_GRID)
                * math.cos(math.pi * fy * (y + 0.5) / PHASH_GRID)
                for fx, fy, amp in waves
            )
            pixels.append(max(40, min(200, int(120 + 30 * value))))
    return bytes(pixels)


def _checkerboard(block: int = 4) -> bytes:
    return bytes(
        255 if ((x // block) + (y // block)) % 2 else 0
        for y in range(PHASH_GRID)
        for x in range(PHASH_GRID)
    )


def _shift(pixels: bytes, delta: int) -> bytes:
    return bytes(max(0, min(255, p + delta)) for p in pixels)


def _add_noise(pixels: bytes, amplitude: int, seed: int = 7) -> bytes:
    rnd = random.Random(seed)
    return bytes(max(0, min(255, p + rnd.randint(-amplitude, amplitude))) for p in pixels)


# --------------------------------------------------------------------------- #
# MD5
# --------------------------------------------------------------------------- #


def test_md5_giong_hashlib_va_khong_phu_thuoc_kich_thuoc_khoi(tmp_path: Path) -> None:
    path = tmp_path / "a.mp4"
    data = bytes(range(256)) * 500
    path.write_bytes(data)

    assert file_md5(path) == hashlib.md5(data).hexdigest()
    assert file_md5(path, chunk_size=7) == file_md5(path, chunk_size=1 << 20)


def test_md5_khac_nhau_khi_doi_mot_byte(tmp_path: Path) -> None:
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"x" * 1000)
    b.write_bytes(b"x" * 999 + b"y")
    assert file_md5(a) != file_md5(b)


# --------------------------------------------------------------------------- #
# DCT
# --------------------------------------------------------------------------- #


def _naive_dct_2d(matrix: list[list[float]], keep: int) -> list[list[float]]:
    """Công thức DCT-II 2D viết thẳng — chậm, chỉ dùng làm mốc đối chiếu."""
    n = len(matrix)
    out = []
    for ky in range(keep):
        row = []
        for kx in range(keep):
            total = 0.0
            for y in range(n):
                for x in range(n):
                    total += (
                        matrix[y][x]
                        * math.cos(math.pi / n * (x + 0.5) * kx)
                        * math.cos(math.pi / n * (y + 0.5) * ky)
                    )
            row.append(total)
        out.append(row)
    return out


def test_dct_tach_roi_bang_dct_2d_thang() -> None:
    size = 8
    rnd = random.Random(3)
    matrix = [[float(rnd.randint(0, 255)) for _ in range(size)] for _ in range(size)]

    fast = _dct_low_freq(matrix, 4)
    slow = _naive_dct_2d(matrix, 4)

    for ky in range(4):
        for kx in range(4):
            assert fast[ky][kx] == pytest.approx(slow[ky][kx], rel=1e-9, abs=1e-6)


# --------------------------------------------------------------------------- #
# pHash một khung
# --------------------------------------------------------------------------- #


def test_phash_sai_kich_thuoc_thi_bao_loi() -> None:
    with pytest.raises(DedupError):
        phash_from_gray(b"\x00" * (N - 1))


def test_phash_cung_anh_thi_khoang_cach_bang_0() -> None:
    image = _frame()
    assert phash_from_gray(image) == phash_from_gray(image)
    assert phash_distance(frame_phash_hex(image), frame_phash_hex(image)) == 0


def test_phash_khong_doi_khi_chinh_sang_ca_anh() -> None:
    """Cộng hằng số chỉ đổi hệ số DC — ngưỡng lấy trung vị nên hash giữ nguyên.

    Đây là tính chất bắt buộc: nguồn TQ hay bị chỉnh sáng nhẹ khi reup.
    """
    for seed in range(5):
        image = _frame(seed)
        assert phash_distance(frame_phash_hex(image), frame_phash_hex(_shift(image, 20))) == 0
        assert phash_distance(frame_phash_hex(image), frame_phash_hex(_shift(image, -20))) == 0


def test_phash_nhieu_nhe_van_gan_hon_han_anh_khac() -> None:
    """Nhiễu kiểu nén lại phải nằm xa dưới khoảng cách giữa hai ảnh khác nhau.

    Khung tổng hợp ở đây là trường hợp XẤU NHẤT: gần như không có chi tiết tần
    số cao nên hệ số DCT bám sát trung vị, chỉ cần nhiễu nhẹ là lật bit. Đo trên
    video thật (xem ``scripts/try_dedup.py``) khoảng cách khi mã hoá lại chỉ ~2
    bit trên tổng 256.
    """
    for seed in range(5):
        image = _frame(seed)
        noisy = phash_distance(frame_phash_hex(image), frame_phash_hex(_add_noise(image, 4)))
        other = phash_distance(frame_phash_hex(image), frame_phash_hex(_frame(seed + 1)))
        assert noisy <= 20
        assert noisy < other


def test_phash_hai_anh_khac_han_thi_cach_xa() -> None:
    distance = phash_distance(frame_phash_hex(_frame()), frame_phash_hex(_checkerboard()))
    assert distance > 20


def test_phash_mot_khung_dai_16_ky_tu_hex() -> None:
    value = frame_phash_hex(_frame())
    assert len(value) == PHASH_HEX_PER_FRAME == 16
    int(value, 16)  # phải parse được như hex


# --------------------------------------------------------------------------- #
# Ghép nhiều khung + so sánh
# --------------------------------------------------------------------------- #


def test_phash_bon_khung_vua_dung_cot_64_ky_tu() -> None:
    frames = [_frame(seed) for seed in range(4)]
    combined = "".join(frame_phash_hex(f) for f in frames)

    assert len(combined) == 64
    assert Fingerprint(md5="0" * 32, phash=combined).frames == 4


def test_khoang_cach_khac_do_dai_thi_bao_loi() -> None:
    with pytest.raises(DedupError):
        phash_distance("ff" * 8, "ff" * 4)


def test_khoang_cach_dem_dung_so_bit() -> None:
    assert phash_distance("0000000000000000", "0000000000000001") == 1
    assert phash_distance("0000000000000000", "ffffffffffffffff") == 64
    assert phash_distance("00ff00ff00ff00ff", "ff00ff00ff00ff00") == 64


def test_thieu_hash_hoac_lech_do_dai_thi_khong_coi_la_trung() -> None:
    """Thà bỏ sót bản trùng còn hơn xoá nhầm video hợp lệ."""
    value = "ab" * 32
    assert is_similar_phash(None, value, max_distance=20) is False
    assert is_similar_phash(value, None, max_distance=20) is False
    assert is_similar_phash("", "", max_distance=20) is False
    # pHash sinh bằng số khung khác nhau → không so được
    assert is_similar_phash(value, "ab" * 16, max_distance=20) is False


def test_trung_khi_trong_nguong_khong_trung_khi_ngoai_nguong() -> None:
    base = "0" * 64
    one_bit = "0" * 63 + "1"  # lệch đúng 1 bit
    far = "f" * 64  # lệch 256 bit

    assert is_similar_phash(base, base, max_distance=0) is True
    assert is_similar_phash(base, one_bit, max_distance=1) is True
    assert is_similar_phash(base, one_bit, max_distance=0) is False
    assert is_similar_phash(base, far, max_distance=20) is False
