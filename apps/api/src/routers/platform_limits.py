from __future__ import annotations

from fastapi import APIRouter, Depends
from reup_core.enums import Platform
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas.platform_limit import PlatformLimitOut, PlatformLimitUpdate
from ..services import platform_limit_service

router = APIRouter(prefix="/platform-limits", tags=["platform-limits"])


@router.get("", response_model=list[PlatformLimitOut])
def list_platform_limits(db: Session = Depends(get_db)):
    return platform_limit_service.list_limits(db)


@router.patch("/{platform}", response_model=PlatformLimitOut)
def update_platform_limit(
    platform: Platform, body: PlatformLimitUpdate, db: Session = Depends(get_db)
):
    data = body.model_dump(exclude_unset=True)
    return platform_limit_service.update_limit(db, platform.value, data)
