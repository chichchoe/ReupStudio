from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from reup_core.enums import M1_STEPS


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_platform: str
    source_video_id: str
    source_url: str
    source_author: str | None = None
    title_original: str | None = None
    title_vi: str | None = None
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    status: str
    current_step: str | None = None
    error_message: str | None = None
    flags: dict[str, Any] = Field(default_factory=dict)
    out_path: str | None = None
    created_at: datetime
    updated_at: datetime

    @property
    def step_index(self) -> int:
        if not self.current_step:
            return 0
        try:
            return [s.value for s in M1_STEPS].index(self.current_step)
        except ValueError:
            return 0


class VideoDetail(VideoOut):
    desc_original: str | None = None
    desc_vi: str | None = None
    hashtags_vi: list[str] | None = None
    fps: float | None = None
    has_audio: bool | None = None
    raw_path: str | None = None
    process_config: dict[str, Any] = Field(default_factory=dict)


class CreateFromLinks(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=200)
    process_config: dict[str, Any] = Field(default_factory=dict)
    autostart: bool = True


class CreateFromLinksResult(BaseModel):
    created: int
    skipped_duplicate: int
    invalid: list[str] = Field(default_factory=list)
    video_ids: list[uuid.UUID] = Field(default_factory=list)
    #: Link đã có sẵn trong thư viện → id của bản ghi cũ, để FE mở thẳng video đó.
    duplicate_ids: list[uuid.UUID] = Field(default_factory=list)


class VideoUpdate(BaseModel):
    title_vi: str | None = None
    desc_vi: str | None = None
    hashtags_vi: list[str] | None = None


class BulkAction(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1)
    action: Literal["approve", "delete", "retry"]


class SubtitleCue(BaseModel):
    i: int
    start: float
    end: float
    text: str


class SubtitleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lang: str
    source: str
    edited_by_user: bool
    cues: list[SubtitleCue]


class JobRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_sec: float | None = None
    log: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
