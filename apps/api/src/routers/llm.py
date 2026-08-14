"""Model LLM dùng được và số liệu đã dùng.

Router chỉ gọi service, trả response — KHÔNG có logic nghiệp vụ. Lỗi từ service
(``LlmAuthFailed``/``LlmUnavailable``) do ``api_error_handler`` dịch thành
status code, không bắt lại ở đây.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas.llm import LlmModelsOut, LlmUsageOut
from ..services import llm_model_service, llm_usage_service

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/models", response_model=LlmModelsOut)
def list_llm_models():
    """Model của khoá hiện tại, chia nhóm dịch và giọng nói.

    Có chạm mạng ngoài nhưng KHÔNG qua Celery (xem lý do ở
    ``services/llm_model_service.py``): một lượt GET nhẹ, chặn bằng hạn chờ
    ngắn và cache 5 phút. Hỏng thì trả lỗi rõ ràng chứ không bao giờ trả danh
    sách rỗng kèm 200.
    """
    return llm_model_service.liet_ke_models()


@router.get("/usage", response_model=LlmUsageOut)
def get_llm_usage(db: Session = Depends(get_db)):
    return llm_usage_service.tom_tat(db)
