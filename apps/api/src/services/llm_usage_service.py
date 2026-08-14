"""Số liệu đã dùng của LLM, cộng từ bảng ``cost_logs``. KHÔNG biết gì về HTTP.

Vì sao API phải tự cộng thay vì hỏi nhà cung cấp: đo ngày 2026-08-14, Gemini
KHÔNG trả header hạn mức nào (không có ``x-ratelimit-*``). Không hỏi được còn
bao nhiêu lượt thì phải tự đếm tại máy — mà đếm được là nhờ mỗi lượt gọi đều để
lại một dòng ``cost_logs``.

``apps/worker/src/tasks/cost.py`` có bộ đếm tương tự để CHẶN khi vượt trần;
chỗ này chỉ để HIỂN THỊ. Hai app độc lập nên không import chéo được — truy vấn
buộc phải viết lại. Đổi mốc thời gian hay bộ lọc ở một bên thì phải sửa cả bên
kia, nếu không con số người dùng nhìn thấy sẽ khác con số dùng để chặn họ.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from reup_core.models import CostLog
from sqlalchemy.orm import Session

from ..config import get_settings

#: Phải khớp ``SERVICE_LLM_TRANSLATE`` bên worker — cùng một chuỗi ghi vào DB.
SERVICE_LLM_TRANSLATE = "llm_translate"
#: ``cost_logs`` dùng chung cho TTS (đơn vị giây) và băng thông (đơn vị byte);
#: cộng thẳng ``quantity`` của mọi dòng vào ô token là cộng lẫn đơn vị.
UNIT_TOKEN = "token"

_GIAY_MOT_PHUT = 60
_GIAY_MOT_NGAY = 86_400


@dataclass(frozen=True)
class TomTatUsage:
    """Đủ để giao diện hiện "hôm nay: 143 lượt · 2,1M token" và vẽ thanh hạn mức."""

    requests_last_min: int
    requests_last_day: int
    tokens_last_day: int
    cost_usd_this_month: float
    #: Trần tự khai trong cấu hình. 0 = KHÔNG giới hạn (không phải "cấm gọi").
    max_requests_per_min: int
    max_requests_per_day: int
    monthly_budget_usd: float


def _moc(trong_giay: int) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=trong_giay)


def dem_luot(db: Session, *, trong_giay: int) -> int:
    """Số lượt gọi LLM trong ``trong_giay`` giây gần nhất.

    Cửa sổ TRƯỢT tính từ lúc gọi, không phải theo ngày lịch: nhà cung cấp cũng
    tính kiểu này, đếm theo ngày lịch sẽ báo còn hạn mức trong khi thật ra hết.
    """
    return int(
        db.scalar(
            sa.select(sa.func.count())
            .select_from(CostLog)
            .where(
                CostLog.service == SERVICE_LLM_TRANSLATE,
                CostLog.created_at >= _moc(trong_giay),
            )
        )
        or 0
    )


def tong_token(db: Session, *, trong_giay: int) -> int:
    """Tổng token LLM trong ``trong_giay`` giây gần nhất.

    Trả số nguyên dù cột là ``Float`` (kiểu chung với TTS đo bằng giây) — token
    luôn nguyên, và giao diện hiện "2,1M token" chứ không "2100000.0".
    """
    tong = db.scalar(
        sa.select(sa.func.coalesce(sa.func.sum(CostLog.quantity), 0.0)).where(
            CostLog.service == SERVICE_LLM_TRANSLATE,
            CostLog.unit == UNIT_TOKEN,
            CostLog.created_at >= _moc(trong_giay),
        )
    )
    return int(tong or 0)


def tien_thang_nay(db: Session) -> float:
    """Tiền đã tiêu cho MỌI dịch vụ ngoài từ đầu tháng, theo giờ UTC.

    Mốc UTC chứ không theo giờ máy: trần chi tiêu của nhà cung cấp tính theo
    UTC, lấy mốc khác sẽ lệch đúng vào hai ngày đầu/cuối tháng — lúc dễ vượt
    trần nhất.

    KHÔNG lọc theo ``service``, khác hẳn hai hàm đếm lượt phía trên. Lý do:
    ``MONTHLY_BUDGET_USD`` là trần TIỀN cho toàn bộ dịch vụ ngoài, và
    ``apps/worker/src/tasks/cost.py::kiem_han_muc`` chặn bằng đúng tổng đó.
    Hiển thị mà lọc riêng ``llm_translate`` thì tới khi M8 ghi thêm dòng TTS,
    con số người dùng NHÌN THẤY sẽ thấp hơn con số dùng để CHẶN — họ bị chặn
    giữa chừng mà nhìn màn hình thấy còn dư ngân sách.

    Ngược lại, số LƯỢT vẫn lọc riêng ``llm_translate`` vì trần lượt/phút và
    lượt/ngày là của riêng model dịch, không dùng chung với TTS.
    """
    dau_thang = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    tong = db.scalar(
        sa.select(sa.func.coalesce(sa.func.sum(CostLog.cost_usd), 0.0)).where(
            CostLog.created_at >= dau_thang,
        )
    )
    return round(float(tong or 0.0), 4)


def tom_tat(db: Session) -> TomTatUsage:
    """Số liệu đã dùng kèm trần, để giao diện tự tính còn lại bao nhiêu."""
    s = get_settings()
    return TomTatUsage(
        requests_last_min=dem_luot(db, trong_giay=_GIAY_MOT_PHUT),
        requests_last_day=dem_luot(db, trong_giay=_GIAY_MOT_NGAY),
        tokens_last_day=tong_token(db, trong_giay=_GIAY_MOT_NGAY),
        cost_usd_this_month=tien_thang_nay(db),
        max_requests_per_min=s.llm_max_requests_per_min,
        max_requests_per_day=s.llm_max_requests_per_day,
        monthly_budget_usd=s.monthly_budget_usd,
    )
