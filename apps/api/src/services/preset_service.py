"""Logic nghiệp vụ cho preset. KHÔNG biết gì về HTTP/FastAPI.

Quy tắc nghiệp vụ: mỗi ``kind`` chỉ có đúng một preset ``is_default=True``. Khi
một preset được đặt làm mặc định, preset mặc định cũ cùng kind bị gỡ cờ trong
cùng một transaction (không có commit ở đây — caller ở router chịu trách
nhiệm commit qua ``get_db``).
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from reup_core.models import Preset
from sqlalchemy.orm import Session

from ..errors import NotFound


def list_presets(db: Session, *, kind: str | None = None) -> list[Preset]:
    stmt = sa.select(Preset)
    if kind:
        stmt = stmt.where(Preset.kind == kind)
    return list(db.scalars(stmt.order_by(Preset.kind, Preset.name)).all())


def get_preset(db: Session, preset_id: uuid.UUID) -> Preset:
    preset = db.get(Preset, preset_id)
    if preset is None:
        raise NotFound(f"Không tìm thấy preset {preset_id}")
    return preset


def _clear_other_defaults(db: Session, kind: str, *, keep_id: uuid.UUID) -> None:
    """Gỡ cờ ``is_default`` của mọi preset khác cùng kind, trừ ``keep_id``."""
    db.execute(
        sa.update(Preset)
        .where(Preset.kind == kind, Preset.id != keep_id, Preset.is_default.is_(True))
        .values(is_default=False)
    )


def create_preset(
    db: Session,
    *,
    kind: str,
    name: str,
    config: dict[str, Any] | None = None,
    is_default: bool = False,
) -> Preset:
    preset = Preset(kind=kind, name=name, config=config or {}, is_default=is_default)
    db.add(preset)
    db.flush()
    if is_default:
        _clear_other_defaults(db, kind, keep_id=preset.id)
    return preset


def update_preset(
    db: Session,
    preset_id: uuid.UUID,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    is_default: bool | None = None,
) -> Preset:
    preset = get_preset(db, preset_id)
    if name is not None:
        preset.name = name
    if config is not None:
        preset.config = config
    if is_default is not None:
        preset.is_default = is_default
        if is_default:
            db.flush()
            _clear_other_defaults(db, preset.kind, keep_id=preset.id)
    return preset
