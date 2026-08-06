from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from reup_core.enums import PresetKind
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas.preset import PresetCreate, PresetOut, PresetUpdate
from ..services import preset_service

router = APIRouter(prefix="/presets", tags=["presets"])


@router.get("", response_model=list[PresetOut])
def list_presets(kind: PresetKind | None = None, db: Session = Depends(get_db)):
    return preset_service.list_presets(db, kind=kind.value if kind else None)


@router.post("", response_model=PresetOut, status_code=201)
def create_preset(body: PresetCreate, db: Session = Depends(get_db)):
    return preset_service.create_preset(
        db,
        kind=body.kind.value,
        name=body.name,
        config=body.config,
        is_default=body.is_default,
    )


@router.patch("/{preset_id}", response_model=PresetOut)
def update_preset(preset_id: uuid.UUID, body: PresetUpdate, db: Session = Depends(get_db)):
    return preset_service.update_preset(
        db,
        preset_id,
        name=body.name,
        config=body.config,
        is_default=body.is_default,
    )
