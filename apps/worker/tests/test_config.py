"""Finding #6 (review tổng M2) — chặn dedup_phash_frames vượt độ rộng cột.

Cột ``videos.phash`` là ``String(64)``, mỗi khung pHash chiếm 16 ký tự hex nên
tối đa chấp nhận 4 khung. Đặt ``DEDUP_PHASH_FRAMES`` lớn hơn phải bị từ chối
ngay ở tầng cấu hình, thay vì để Postgres ném ``StringDataRightTruncation``
lúc download.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_dedup_phash_frames_5_bi_tu_choi() -> None:
    with pytest.raises(ValidationError, match="dedup_phash_frames"):
        Settings(dedup_phash_frames=5)


def test_dedup_phash_frames_0_bi_tu_choi() -> None:
    with pytest.raises(ValidationError, match="dedup_phash_frames"):
        Settings(dedup_phash_frames=0)


def test_dedup_phash_frames_4_duoc_chap_nhan() -> None:
    settings = Settings(dedup_phash_frames=4)
    assert settings.dedup_phash_frames == 4


def test_dedup_phash_frames_1_duoc_chap_nhan() -> None:
    settings = Settings(dedup_phash_frames=1)
    assert settings.dedup_phash_frames == 1
