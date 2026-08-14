"""Ghi và tra cứu ``cost_logs`` — tầng ``tasks/``, được phép chạm DB.

Tách khỏi ``tasks/video.py`` vì hai lý do: dùng chung cho mọi dịch vụ ngoài
(dịch, TTS, inpaint GPU sau này), và để ``pipeline/`` tuyệt đối không phải biết
DB tồn tại — nó chỉ gọi callback ``on_usage`` do chỗ này dựng ra.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from reup_core.logging import get_logger
from reup_core.models import CostLog

from ..config import get_settings
from ..translator.base import LlmUsage

log = get_logger(__name__)

SERVICE_LLM_TRANSLATE = "llm_translate"
UNIT_TOKEN = "token"

#: Một triệu token — đơn vị các nhà cung cấp niêm yết giá.
_TOKENS_PER_PRICE_UNIT = 1_000_000


def uoc_tinh_chi_phi(prompt_tokens: int, completion_tokens: int) -> float:
    """Tiền (USD) cho một lượt gọi, theo bảng giá trong cấu hình.

    Bậc miễn phí thì cả hai đơn giá bằng 0 nên kết quả luôn 0 — con số có ý
    nghĩa chỉ khi chuyển sang trả phí. Thứ THẬT SỰ chặn ta lại lúc này là số
    lượt gọi, không phải tiền.
    """
    s = get_settings()
    vao = prompt_tokens / _TOKENS_PER_PRICE_UNIT * s.llm_price_input_per_1m
    ra = completion_tokens / _TOKENS_PER_PRICE_UNIT * s.llm_price_output_per_1m
    return round(vao + ra, 6)


def ghi_usage(session, video_id: uuid.UUID | None, usage: LlmUsage, truoc: LlmUsage | None) -> None:
    """Ghi PHẦN CHÊNH giữa hai lần chụp usage thành một dòng ``cost_logs``.

    ``translate_cues`` báo usage cộng dồn sau mỗi lô, nên phải trừ đi lần chụp
    trước để ra đúng lượng của riêng lô vừa xong — cộng thẳng số cộng dồn sẽ
    đếm gấp bội.
    """
    prompt = usage.prompt_tokens - (truoc.prompt_tokens if truoc else 0)
    completion = usage.completion_tokens - (truoc.completion_tokens if truoc else 0)
    total = usage.total_tokens - (truoc.total_tokens if truoc else 0)

    session.add(
        CostLog(
            video_id=video_id,
            service=SERVICE_LLM_TRANSLATE,
            model=usage.model,
            unit=UNIT_TOKEN,
            quantity=float(total),
            cost_usd=uoc_tinh_chi_phi(prompt, completion),
        )
    )


def dem_luot(session, *, trong_giay: int) -> int:
    """Số lượt gọi LLM trong ``trong_giay`` giây gần nhất."""
    moc = datetime.now(UTC) - timedelta(seconds=trong_giay)
    return int(
        session.scalar(
            sa.select(sa.func.count())
            .select_from(CostLog)
            .where(CostLog.service == SERVICE_LLM_TRANSLATE, CostLog.created_at >= moc)
        )
        or 0
    )


def tien_thang_nay(session) -> float:
    """Tổng tiền đã tiêu từ đầu tháng (UTC)."""
    dau_thang = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return float(
        session.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(CostLog.cost_usd), 0.0)).where(
                CostLog.created_at >= dau_thang
            )
        )
        or 0.0
    )


def tom_tat(session) -> dict:
    """Số liệu để hiển thị và để chặn khi vượt trần."""
    s = get_settings()
    return {
        "luot_phut": dem_luot(session, trong_giay=60),
        "luot_ngay": dem_luot(session, trong_giay=86400),
        "tien_thang_usd": round(tien_thang_nay(session), 4),
        "tran_luot_phut": s.llm_max_requests_per_min,
        "tran_luot_ngay": s.llm_max_requests_per_day,
        "tran_tien_thang_usd": s.monthly_budget_usd,
    }
