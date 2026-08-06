from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from reup_core.enums import PresetKind


class PresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    is_default: bool
    created_at: datetime
    updated_at: datetime


class PresetCreate(BaseModel):
    kind: PresetKind
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class PresetUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    is_default: bool | None = None
