"""Logic nghiệp vụ cho kênh nguồn. KHÔNG biết gì về HTTP/FastAPI.

Chốt an toàn pháp lý: ``license_status`` mặc định ``unknown``, và kênh
``unknown`` không bao giờ được đưa vào luồng xử lý tự động — xem
``can_auto_process``. Đây là ràng buộc nghiệp vụ, không được bỏ qua vì tiện.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from reup_core.enums import AUTO_ALLOWED_LICENSES
from reup_core.models import SourceChannel
from reup_core.models.source_channel import VALID_SCAN_INTERVAL_MIN
from sqlalchemy.orm import Session

from ..errors import ApiError, Conflict, NotFound


def can_auto_process(channel: SourceChannel) -> bool:
    """Chỉ True khi enabled và license_status nằm trong AUTO_ALLOWED_LICENSES.

    Đây là chốt an toàn pháp lý duy nhất quyết định một kênh có được đưa vào
    luồng tự động hay không. Mọi nơi khác trong hệ thống (task Celery quét
    kênh, v.v.) phải gọi qua hàm này, không tự kiểm tra ``license_status``.
    """
    return channel.enabled and channel.license_status in AUTO_ALLOWED_LICENSES


def _validate_scan_interval(scan_interval_min: int) -> None:
    if scan_interval_min not in VALID_SCAN_INTERVAL_MIN:
        allowed = ", ".join(str(v) for v in sorted(VALID_SCAN_INTERVAL_MIN))
        raise ApiError(
            f"scan_interval_min phải là một trong: {allowed} (phút), nhận được {scan_interval_min}"
        )


def list_channels(
    db: Session,
    *,
    platform: str | None = None,
    enabled: bool | None = None,
) -> list[SourceChannel]:
    stmt = sa.select(SourceChannel)
    if platform:
        stmt = stmt.where(SourceChannel.platform == platform)
    if enabled is not None:
        stmt = stmt.where(SourceChannel.enabled == enabled)
    return list(db.scalars(stmt.order_by(SourceChannel.created_at.desc())).all())


def get_channel(db: Session, channel_id: uuid.UUID) -> SourceChannel:
    channel = db.get(SourceChannel, channel_id)
    if channel is None:
        raise NotFound(f"Không tìm thấy kênh nguồn {channel_id}")
    return channel


def create_channel(
    db: Session,
    *,
    platform: str,
    external_id: str,
    url: str,
    handle: str | None = None,
    display_name: str | None = None,
    scan_interval_min: int = 60,
    filter_preset_id: uuid.UUID | None = None,
    process_preset_id: uuid.UUID | None = None,
    license_status: str = "unknown",
    license_note: str | None = None,
    enabled: bool = True,
) -> SourceChannel:
    _validate_scan_interval(scan_interval_min)

    existing = db.scalar(
        sa.select(SourceChannel).where(
            SourceChannel.platform == platform,
            SourceChannel.external_id == external_id,
        )
    )
    if existing is not None:
        raise Conflict(f"Kênh {platform}/{external_id} đã được theo dõi, không tạo trùng")

    channel = SourceChannel(
        platform=platform,
        external_id=external_id,
        url=url,
        handle=handle,
        display_name=display_name,
        scan_interval_min=scan_interval_min,
        filter_preset_id=filter_preset_id,
        process_preset_id=process_preset_id,
        license_status=license_status,
        license_note=license_note,
        enabled=enabled,
    )
    db.add(channel)
    db.flush()
    return channel


def update_channel(
    db: Session,
    channel_id: uuid.UUID,
    *,
    handle: str | None = None,
    display_name: str | None = None,
    scan_interval_min: int | None = None,
    last_seen_video_id: str | None = None,
    filter_preset_id: uuid.UUID | None = None,
    process_preset_id: uuid.UUID | None = None,
    license_status: str | None = None,
    license_note: str | None = None,
    enabled: bool | None = None,
) -> SourceChannel:
    channel = get_channel(db, channel_id)

    if scan_interval_min is not None:
        _validate_scan_interval(scan_interval_min)
        channel.scan_interval_min = scan_interval_min
    if handle is not None:
        channel.handle = handle
    if display_name is not None:
        channel.display_name = display_name
    if last_seen_video_id is not None:
        channel.last_seen_video_id = last_seen_video_id
    if filter_preset_id is not None:
        channel.filter_preset_id = filter_preset_id
    if process_preset_id is not None:
        channel.process_preset_id = process_preset_id
    if license_status is not None:
        channel.license_status = license_status
    if license_note is not None:
        channel.license_note = license_note
    if enabled is not None:
        channel.enabled = enabled
    return channel


def delete_channel(db: Session, channel_id: uuid.UUID) -> None:
    channel = get_channel(db, channel_id)
    db.delete(channel)
