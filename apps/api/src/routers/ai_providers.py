"""Cấu hình nhà cung cấp AI — dán khoá, bật/tắt, hỏi danh sách model.

Người dùng cấu hình nhiều bên cùng lúc (Gemini, OpenRouter, Claude, DeepSeek)
rồi chọn bên nào cho từng video. Khoá KHÔNG BAO GIỜ ra khỏi API (luật số 6
CLAUDE.md) — endpoint đọc chỉ trả cờ đã đặt hay chưa.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from reup_core.settings_store import KhoaMaHoaThieu
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiError
from ..schemas.ai_provider import NhaCungCapOut, SuaNhaCungCapIn
from ..services import ai_provider_service

router = APIRouter(prefix="/ai-providers", tags=["ai-providers"])


@router.get("", response_model=list[NhaCungCapOut])
def danh_sach(db: Session = Depends(get_db)):
    """Mọi nhà cung cấp trong danh mục, kèm trạng thái đã cấu hình hay chưa."""
    return ai_provider_service.danh_sach(db)


@router.put("/{ma}", response_model=list[NhaCungCapOut])
def sua(ma: str, body: SuaNhaCungCapIn, db: Session = Depends(get_db)):
    """Lưu khoá và cấu hình một nhà cung cấp.

    Ô khoá để TRỐNG nghĩa là giữ nguyên cái đang có, không phải xoá — giao diện
    không bao giờ nhận được khoá thật nên nó luôn gửi chuỗi rỗng ở ô không sửa.
    Muốn gỡ khoá thì dùng ``DELETE``.
    """
    try:
        ai_provider_service.luu(
            db, ma, api_key=body.api_key, base_url=body.base_url, enabled=body.enabled
        )
    except KhoaMaHoaThieu as exc:
        raise ApiError(str(exc)) from exc

    db.commit()
    return ai_provider_service.danh_sach(db)


@router.delete("/{ma}/khoa", response_model=list[NhaCungCapOut])
def go_khoa(ma: str, db: Session = Depends(get_db)):
    """Gỡ khoá — dùng khi đổi tài khoản hoặc nghi khoá bị lộ."""
    ai_provider_service.xoa_khoa(db, ma)
    db.commit()
    return ai_provider_service.danh_sach(db)


@router.get("/{ma}/models", response_model=list[str])
def models(
    ma: str,
    muc_dich: str = Query("translate", pattern="^(translate|tts)$"),
    db: Session = Depends(get_db),
):
    """Hỏi THẲNG nhà cung cấp xem khoá này dùng được model nào, lọc theo việc.

    Hỏi trực tiếp thay vì để người dùng gõ tay tên model: gõ sai một ký tự thì
    lỗi chỉ hiện ra lúc dịch, sau khi đã chờ tải và nhận dạng xong.
    """
    return ai_provider_service.models(db, ma, muc_dich)
