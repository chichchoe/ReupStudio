"""M4-WK-01 — đổi video ngang sang dọc 9:16, không cắt mất đầu nhân vật.

Chỉ test ``subject_column`` — hàm THUẦN, không cần ffmpeg/OpenCV để dò khung
thật. Dựng mảng khung tổng hợp (numpy) mô phỏng một vệt sáng di chuyển: chủ
thể "chuyển động" ở một cột, nền tĩnh (toàn 0) — ``subject_column`` phải nhặt
đúng cột đó bằng phương sai theo thời gian, không cần video thật.

Phần dựng lệnh ffmpeg (``reframe_blur``, ``reframe_crop``) kiểm bằng tay qua
``scripts/try_reframe.py`` trên video tổng hợp, không có test tự động (đúng
quy ước CLAUDE.md: FFmpeg kiểm bằng script chạy tay).
"""

from __future__ import annotations

import random

import numpy as np

from src.pipeline.shortform.reframe import (
    DEFAULT_CENTER,
    subject_column,
)

TOLERANCE = 0.08


def _moving_streak_frames(
    *,
    width: int,
    height: int,
    target_frac: float,
    count: int = 8,
    jitter_px: int = 2,
    seed: int = 0,
) -> list[np.ndarray]:
    """Nhiều khung xám: một vệt sáng dọc di chuyển quanh ``target_frac``.

    Nền toàn 0 (tĩnh), vệt sáng (giá trị 255) nhảy nhẹ quanh cột đích giữa các
    khung — mô phỏng chủ thể chuyển động nhẹ (rung tay, cử động) quanh một vị
    trí ổn định, đúng kiểu dữ liệu mà thuật toán phương sai theo thời gian
    phải bắt được.
    """
    rng = random.Random(seed)
    target_idx = target_frac * width
    frames = []
    for _ in range(count):
        frame = np.zeros((height, width), dtype=np.uint8)
        idx = int(round(target_idx + rng.uniform(-jitter_px, jitter_px)))
        idx = max(0, min(width - 1, idx))
        frame[:, idx] = 255
        frames.append(frame)
    return frames


def test_vet_sang_o_mot_phan_tu_ben_trai_ra_khoang_025() -> None:
    frames = _moving_streak_frames(width=200, height=100, target_frac=0.25)
    result = subject_column(frames)
    assert abs(result - 0.25) <= TOLERANCE


def test_chu_the_o_giua_ra_khoang_05() -> None:
    frames = _moving_streak_frames(width=200, height=100, target_frac=0.5)
    result = subject_column(frames)
    assert abs(result - 0.5) <= TOLERANCE


def test_chu_the_sat_mep_phai_bi_kep_khong_tran_khung() -> None:
    # Kích thước thật (16:9) để tính chính xác nửa bề rộng dải cắt kỳ vọng:
    # crop_w = 1080 * 9/16 = 607.5px → nửa bề rộng phần trăm = 607.5/2/1920.
    width, height = 1920, 1080
    out_aspect = 9 / 16
    expected_half_width = (height * out_aspect / 2) / width

    frames = _moving_streak_frames(width=width, height=height, target_frac=0.97)
    result = subject_column(frames, out_aspect=out_aspect)

    # Bị kẹp: không được ra gần 0.97 như vị trí chủ thể thật, mà phải lùi lại
    # để dải cắt quanh nó còn nằm trọn trong khung.
    assert result <= 1 - expected_half_width + 1e-9
    assert result < 0.9


def test_khung_hoan_toan_tinh_ra_mac_dinh_khong_nem_loi() -> None:
    frames = [np.zeros((100, 200), dtype=np.uint8) for _ in range(6)]
    assert subject_column(frames) == DEFAULT_CENTER


def test_it_hon_hai_khung_ra_mac_dinh_khong_nem_loi() -> None:
    assert subject_column([]) == DEFAULT_CENTER
    assert subject_column([np.zeros((100, 200), dtype=np.uint8)]) == DEFAULT_CENTER


def test_ket_qua_luon_trong_khoang_0_1() -> None:
    rng = np.random.default_rng(42)
    for target in (0.0, 0.02, 0.5, 0.98, 1.0):
        frames = _moving_streak_frames(width=200, height=100, target_frac=target)
        result = subject_column(frames)
        assert 0.0 <= result <= 1.0

    # Nhiễu hoàn toàn ngẫu nhiên mỗi khung (trường hợp xấu nhất, không có chủ
    # thể rõ ràng nào) vẫn phải ra một số hợp lệ trong [0, 1].
    noisy_frames = [rng.integers(0, 256, size=(100, 200), dtype=np.uint8) for _ in range(6)]
    result = subject_column(noisy_frames)
    assert 0.0 <= result <= 1.0
