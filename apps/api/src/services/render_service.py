"""Logic nghiệp vụ cho render nhiều nền tảng cùng lúc (M4-BE-02).

KHÔNG biết gì về HTTP/FastAPI — router chỉ gọi các hàm ở đây rồi trả response.
Việc dispatch task Celery ở lớp gọi (router), giống ``prepare_retry`` +
``task_bridge.retry_from``: hàm ở đây chỉ chuẩn bị dữ liệu, KHÔNG commit và
KHÔNG gửi task, để router kiểm soát đúng thứ tự "commit trước khi dispatch".
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from reup_core.models import PlatformLimit, RenderVariant, Video
from sqlalchemy.orm import Session

from ..errors import NotFound, UnsupportedSource
from . import video_service


def _validate_target_platforms(db: Session, target_platforms: list[str]) -> None:
    """Mỗi nền tảng trong ``target_platforms`` phải có dòng ``platform_limits``
    tương ứng (luật số 5 CLAUDE.md — giới hạn nền tảng đọc từ bảng, không
    hardcode). Enum lạ đã bị chặn ở tầng schema (``list[Platform]``); ở đây
    chỉ còn phải kiểm nền tảng hợp lệ nhưng CHƯA cấu hình giới hạn.
    """
    co_san = set(
        db.scalars(
            sa.select(PlatformLimit.platform).where(PlatformLimit.platform.in_(target_platforms))
        ).all()
    )
    thieu = sorted(set(target_platforms) - co_san)
    if thieu:
        raise UnsupportedSource(f"Chưa cấu hình platform_limits cho nền tảng: {', '.join(thieu)}")


def request_render(
    db: Session,
    video_id: uuid.UUID,
    target_platforms: list[str],
    preset_overrides: dict[str, Any],
) -> Video:
    """Chuẩn bị một video để render nhiều bản (một bản mỗi nền tảng đích).

    Ghi ``target_platforms`` + ``preset_overrides`` vào ``video.process_config``
    — đây chính là nơi ``render_variants_task`` (worker) đọc lại để biết
    render cho nền tảng nào (xem ``_target_platforms`` trong
    ``apps/worker/src/tasks/video.py``).

    Router PHẢI ``db.commit()`` NGAY SAU khi gọi hàm này rồi mới gọi
    ``task_bridge.render_variants`` — bắt chước thứ tự commit-trước-dispatch
    của ``video_service.prepare_retry``, nếu không worker chạy gần như ngay
    lập tức có thể đọc phải ``process_config`` cũ.
    """
    video = video_service.get_video(db, video_id)
    _validate_target_platforms(db, target_platforms)

    video.process_config = {
        **video.process_config,
        **preset_overrides,
        "target_platforms": target_platforms,
    }
    return video


def list_variants(db: Session, video_id: uuid.UUID) -> list[RenderVariant]:
    """Danh sách ``render_variants`` của một video, sắp ổn định theo
    (nền tảng, số tập) để FE hiển thị nhất quán giữa các lần gọi.
    """
    video_service.get_video(db, video_id)  # ném NotFound nếu không có / đã xoá mềm
    return list(
        db.scalars(
            sa.select(RenderVariant)
            .where(RenderVariant.video_id == video_id)
            .order_by(RenderVariant.target_platform, RenderVariant.part_index)
        ).all()
    )


def get_variant(db: Session, variant_id: uuid.UUID) -> RenderVariant:
    """Lấy một ``render_variant``, chặn luôn video cha đã bị xoá mềm.

    ``RenderVariant.video_id`` có ``ondelete="CASCADE"`` nên hàng variant
    KHÔNG tự biến mất khi video bị xoá MỀM (chỉ mất khi hard-delete) — không
    thể trông chờ CASCADE làm hộ việc này. Gọi lại ``video_service.get_video``
    (hàm DUY NHẤT trong repo kiểm ``deleted_at``, giống ``list_variants`` đã
    làm) để video đã xoá không thể bị tải file qua ``variant_id`` còn giữ lại.
    """
    variant = db.get(RenderVariant, variant_id)
    if variant is None:
        raise NotFound(f"Không tìm thấy render variant {variant_id}")
    video_service.get_video(db, variant.video_id)
    return variant
