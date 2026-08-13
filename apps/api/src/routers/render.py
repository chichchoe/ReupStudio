"""M4-BE-02 — API render nhiều nền tảng cùng lúc.

Router chỉ validate input, gọi service, trả response — KHÔNG có logic
nghiệp vụ (bắt chước ``routers/videos.py``).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import NotFound
from ..schemas.common import TaskAccepted
from ..schemas.render import RenderRequest, RenderVariantOut
from ..services import render_service, task_bridge

router = APIRouter(tags=["render"])


@router.post("/videos/{video_id}/render", response_model=TaskAccepted, status_code=202)
def render_video(video_id: uuid.UUID, body: RenderRequest, db: Session = Depends(get_db)):
    """Kích hoạt render nhiều bản (một bản mỗi nền tảng đích). Luật số 10
    CLAUDE.md: render chạy hàng phút -> luôn qua Celery, endpoint không chờ.
    """
    render_service.request_render(
        db,
        video_id,
        [p.value for p in body.target_platforms],
        body.preset_overrides,
    )
    # Commit TRƯỚC khi gửi task — nếu không worker chạy gần như ngay lập tức
    # có thể đọc phải process_config cũ (xem render_service.request_render).
    db.commit()
    task_id = task_bridge.render_variants(video_id)
    return TaskAccepted(task_id=task_id, message="Đã đưa vào hàng đợi render")


@router.get("/videos/{video_id}/variants", response_model=list[RenderVariantOut])
def list_variants(video_id: uuid.UUID, db: Session = Depends(get_db)):
    return render_service.list_variants(db, video_id)


@router.get("/variants/{variant_id}/file")
def download_variant_file(variant_id: uuid.UUID, db: Session = Depends(get_db)):
    """Tải file của một render variant."""
    variant = render_service.get_variant(db, variant_id)
    if not variant.out_path or not Path(variant.out_path).exists():
        raise NotFound("Render variant chưa render xong hoặc file đã bị xoá")
    return FileResponse(
        variant.out_path,
        media_type="video/mp4",
        filename=f"{variant.target_platform}_p{variant.part_index}.mp4",
    )
