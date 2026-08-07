"""Logic nghiệp vụ cho giới hạn nền tảng. KHÔNG biết gì về HTTP/FastAPI.

Đây là bảng nguồn sự thật cho luật số 5 CLAUDE.md: "Giới hạn nền tảng đọc từ
bảng `platform_limits`, không hardcode trong code". Mỗi nền tảng luôn có sẵn
đúng một dòng (được seed ở migration ``0006``) — không có ``create_limit``,
chỉ đọc và chỉnh.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from reup_core.models import PlatformLimit
from sqlalchemy.orm import Session

from ..errors import ApiError, NotFound

#: Các cột số nguyên phải > 0 — 0 hoặc âm là vô nghĩa (VD: không thể giới hạn
#: 0 hashtag rồi vẫn cho phép hashtag). KHÔNG gồm ``max_duration_sec`` — cột
#: đó có quy tắc riêng (``_validate_max_duration_sec``): 0 = không giới hạn.
_POSITIVE_INT_FIELDS = (
    "max_title_len",
    "max_desc_len",
    "max_hashtags",
    "safe_daily_posts",
)

#: 4 khoá bắt buộc của ``safe_area`` — toạ độ phần trăm khung hình (0-1).
_SAFE_AREA_KEYS = ("top", "bottom", "left", "right")


def list_limits(db: Session) -> list[PlatformLimit]:
    stmt = sa.select(PlatformLimit).order_by(PlatformLimit.platform)
    return list(db.scalars(stmt).all())


def get_limit(db: Session, platform: str) -> PlatformLimit:
    limit = db.get(PlatformLimit, platform)
    if limit is None:
        raise NotFound(f"Không tìm thấy giới hạn cho nền tảng '{platform}'")
    return limit


def _validate_positive_ints(data: dict[str, Any]) -> None:
    for field in _POSITIVE_INT_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ApiError(f"'{field}' phải là số nguyên dương, nhận được {value!r}")


def _validate_max_duration_sec(value: Any) -> None:
    """0 = không giới hạn thời lượng (hợp lệ). Chỉ cấm số âm."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ApiError(
            f"'max_duration_sec' phải là số nguyên >= 0 (0 nghĩa là không giới "
            f"hạn thời lượng), nhận được {value!r}"
        )


def _validate_safe_area(safe_area: dict[str, Any]) -> None:
    thieu = [key for key in _SAFE_AREA_KEYS if key not in safe_area]
    if thieu:
        raise ApiError(
            f"safe_area thiếu khoá bắt buộc: {', '.join(thieu)}. "
            f"Cần đủ 4 khoá: {', '.join(_SAFE_AREA_KEYS)}"
        )

    for key in _SAFE_AREA_KEYS:
        value = safe_area[key]
        hop_le = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not hop_le or not (0 <= value < 0.5):
            raise ApiError(
                f"safe_area['{key}'] phải trong khoảng [0, 0.5), nhận được {value!r}"
            )

    if safe_area["top"] + safe_area["bottom"] >= 1:
        raise ApiError(
            "safe_area không hợp lệ: top + bottom phải nhỏ hơn 1, nếu không sẽ "
            "không còn chỗ nào để đặt phụ đề theo chiều dọc"
        )
    if safe_area["left"] + safe_area["right"] >= 1:
        raise ApiError(
            "safe_area không hợp lệ: left + right phải nhỏ hơn 1, nếu không sẽ "
            "không còn chỗ nào để đặt phụ đề theo chiều ngang"
        )


def update_limit(db: Session, platform: str, data: dict[str, Any]) -> PlatformLimit:
    """Chỉnh giới hạn của một nền tảng. ``data`` chỉ chứa các trường muốn đổi.

    Nếu ``platform`` không tồn tại thì ném ``NotFound``. Nếu dữ liệu không hợp
    lệ (số ≤ 0 — riêng ``max_duration_sec`` chỉ cấm số âm vì 0 nghĩa là không
    giới hạn — hoặc ``safe_area`` thiếu khoá/sai khoảng) thì ném ``ApiError``.
    """
    limit = get_limit(db, platform)

    _validate_positive_ints(data)
    if "max_duration_sec" in data:
        _validate_max_duration_sec(data["max_duration_sec"])
    if "safe_area" in data:
        _validate_safe_area(data["safe_area"])

    for field, value in data.items():
        setattr(limit, field, value)
    return limit
