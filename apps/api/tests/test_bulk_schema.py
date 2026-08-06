"""Finding #2 (review tổng M2) — POST /videos/bulk phải giới hạn số id.

Không giới hạn thì bulk_action lặp qua db.get() từng id, giữ một connection
của pool (pool_size=5, max_overflow=10) suốt thời gian xử lý — vi phạm luật
"endpoint không bao giờ chờ việc chạy lâu".
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from src.schemas.video import BulkAction


def test_501_id_bi_tu_choi() -> None:
    ids = [str(uuid.uuid4()) for _ in range(501)]
    with pytest.raises(ValidationError):
        BulkAction(ids=ids, action="approve")


def test_500_id_duoc_chap_nhan() -> None:
    ids = [str(uuid.uuid4()) for _ in range(500)]
    action = BulkAction(ids=ids, action="approve")
    assert len(action.ids) == 500


def test_10_id_duoc_chap_nhan() -> None:
    ids = [str(uuid.uuid4()) for _ in range(10)]
    action = BulkAction(ids=ids, action="retry")
    assert len(action.ids) == 10
