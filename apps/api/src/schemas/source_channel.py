from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from reup_core.enums import LicenseStatus, SourcePlatform


class SourceChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: str
    external_id: str
    handle: str | None
    display_name: str | None
    url: str
    scan_interval_min: int
    last_scanned_at: datetime | None
    last_seen_video_id: str | None
    filter_preset_id: uuid.UUID | None
    process_preset_id: uuid.UUID | None
    license_status: str
    license_note: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class SourceChannelCreate(BaseModel):
    platform: SourcePlatform
    external_id: str
    url: str
    handle: str | None = None
    display_name: str | None = None
    scan_interval_min: int = 60
    filter_preset_id: uuid.UUID | None = None
    process_preset_id: uuid.UUID | None = None
    license_status: LicenseStatus = LicenseStatus.UNKNOWN
    license_note: str | None = None
    enabled: bool = True


class SourceChannelUpdate(BaseModel):
    handle: str | None = None
    display_name: str | None = None
    scan_interval_min: int | None = None
    last_seen_video_id: str | None = None
    filter_preset_id: uuid.UUID | None = None
    process_preset_id: uuid.UUID | None = None
    license_status: LicenseStatus | None = None
    license_note: str | None = None
    enabled: bool | None = None


class ResolveChannelRequest(BaseModel):
    url: str


class ResolveChannelResult(BaseModel):
    """Kết quả phân tích URL kênh — CHỈ từ URL, KHÔNG gọi mạng.

    ``display_name``/``follower_count``/``sample_videos`` luôn rỗng/null ở M2:
    lấy metadata thật là việc của task Celery quét kênh, làm ở chặng sau.
    """

    platform: str
    external_id: str
    handle: str | None
    url: str
    display_name: str | None = None
    follower_count: int | None = None
    sample_videos: list[str] = Field(default_factory=list)
    needs_scan: bool = True
