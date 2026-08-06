from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from reup_core.enums import SourcePlatform
from reup_core.source_url import parse_channel_url
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import UnsupportedSource
from ..schemas.source_channel import (
    ResolveChannelRequest,
    ResolveChannelResult,
    SourceChannelCreate,
    SourceChannelOut,
    SourceChannelUpdate,
)
from ..services import source_channel_service

router = APIRouter(prefix="/source-channels", tags=["source-channels"])


@router.get("", response_model=list[SourceChannelOut])
def list_channels(
    platform: SourcePlatform | None = None,
    enabled: bool | None = None,
    db: Session = Depends(get_db),
):
    return source_channel_service.list_channels(
        db, platform=platform.value if platform else None, enabled=enabled
    )


@router.post("", response_model=SourceChannelOut, status_code=201)
def create_channel(body: SourceChannelCreate, db: Session = Depends(get_db)):
    return source_channel_service.create_channel(
        db,
        platform=body.platform.value,
        external_id=body.external_id,
        url=body.url,
        handle=body.handle,
        display_name=body.display_name,
        scan_interval_min=body.scan_interval_min,
        filter_preset_id=body.filter_preset_id,
        process_preset_id=body.process_preset_id,
        license_status=body.license_status.value,
        license_note=body.license_note,
        enabled=body.enabled,
    )


@router.patch("/{channel_id}", response_model=SourceChannelOut)
def update_channel(channel_id: uuid.UUID, body: SourceChannelUpdate, db: Session = Depends(get_db)):
    return source_channel_service.update_channel(
        db,
        channel_id,
        handle=body.handle,
        display_name=body.display_name,
        scan_interval_min=body.scan_interval_min,
        last_seen_video_id=body.last_seen_video_id,
        filter_preset_id=body.filter_preset_id,
        process_preset_id=body.process_preset_id,
        license_status=body.license_status.value if body.license_status else None,
        license_note=body.license_note,
        enabled=body.enabled,
    )


@router.delete("/{channel_id}", status_code=204)
def delete_channel(channel_id: uuid.UUID, db: Session = Depends(get_db)):
    source_channel_service.delete_channel(db, channel_id)
    return Response(status_code=204)


@router.post("/resolve", response_model=ResolveChannelResult)
def resolve_channel(body: ResolveChannelRequest):
    """Phân tích URL kênh — CHỈ đọc chuỗi URL, TUYỆT ĐỐI KHÔNG gọi mạng.

    Việc lấy tên hiển thị / số follower / video mẫu thật là việc của task
    Celery quét kênh, chạy ở chặng sau. Ở đây luôn trả ``needs_scan=True``.
    """
    parsed = parse_channel_url(body.url)
    if parsed is None:
        raise UnsupportedSource(f"Không nhận diện được URL kênh: {body.url}")

    return ResolveChannelResult(
        platform=parsed.platform.value,
        external_id=parsed.external_id,
        handle=parsed.handle,
        url=parsed.url,
    )
