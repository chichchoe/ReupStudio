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

#: Tổng safe_area mỗi chiều (top+bottom, left+right) không được vượt quá giá
#: trị này — đảm bảo LUÔN còn tối thiểu 40% khung hình để đặt phụ đề. Chặn
#: riêng lẻ từng khoá `< 0.5` KHÔNG đủ: top=0.45, bottom=0.45 vẫn lọt qua chặn
#: riêng nhưng chỉ còn 10% chỗ đặt phụ đề — vô dụng trên thực tế.
_MAX_SAFE_AREA_SUM = 0.6


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


def _validate_safe_area(safe_area: Any) -> None:
    if not isinstance(safe_area, dict):
        raise ApiError(
            f"'safe_area' phải là object đủ 4 khoá {_SAFE_AREA_KEYS!r}, "
            f"nhận được {safe_area!r}"
        )

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

    phan_tram_chua_lai = int(round((1 - _MAX_SAFE_AREA_SUM) * 100))
    if safe_area["top"] + safe_area["bottom"] > _MAX_SAFE_AREA_SUM:
        raise ApiError(
            "safe_area không hợp lệ: vùng an toàn (top + bottom) chiếm quá nhiều "
            "khung hình, không còn chỗ đặt phụ đề (chừa lại tối thiểu "
            f"{phan_tram_chua_lai}% mỗi chiều)"
        )
    if safe_area["left"] + safe_area["right"] > _MAX_SAFE_AREA_SUM:
        raise ApiError(
            "safe_area không hợp lệ: vùng an toàn (left + right) chiếm quá nhiều "
            "khung hình, không còn chỗ đặt phụ đề (chừa lại tối thiểu "
            f"{phan_tram_chua_lai}% mỗi chiều)"
        )


def _validate_aspect_ratios(value: Any) -> None:
    hop_le = (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(item, str) for item in value)
    )
    if not hop_le:
        raise ApiError(
            f"'aspect_ratios' phải là danh sách chuỗi không rỗng, nhận được {value!r}"
        )


def update_limit(db: Session, platform: str, data: dict[str, Any]) -> PlatformLimit:
    """Chỉnh giới hạn của một nền tảng. ``data`` chỉ chứa các trường muốn đổi.

    Nếu ``platform`` không tồn tại thì ném ``NotFound``. Nếu dữ liệu không hợp
    lệ (số ≤ 0 — riêng ``max_duration_sec`` chỉ cấm số âm vì 0 nghĩa là không
    giới hạn — hoặc ``safe_area``/``aspect_ratios`` sai kiểu/thiếu khoá/rỗng)
    thì ném ``ApiError``. Kiểm cả trường hợp client gửi tường minh ``null`` cho
    ``safe_area``/``aspect_ratios`` (hai cột ``NOT NULL``) — nếu không sẽ lọt
    xuống DB và vỡ thành ``IntegrityError``/``TypeError`` không kiểm soát được.
    """
    limit = get_limit(db, platform)

    _validate_positive_ints(data)
    if "max_duration_sec" in data:
        _validate_max_duration_sec(data["max_duration_sec"])
    if "safe_area" in data:
        _validate_safe_area(data["safe_area"])
    if "aspect_ratios" in data:
        _validate_aspect_ratios(data["aspect_ratios"])

    for field, value in data.items():
        setattr(limit, field, value)
    return limit
