from __future__ import annotations

import redis
import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()

    db_ok = True
    try:
        db.execute(sa.text("SELECT 1"))
    except Exception:
        db_ok = False

    redis_ok = True
    try:
        redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
    except Exception:
        redis_ok = False

    return {"ok": db_ok and redis_ok, "db": db_ok, "redis": redis_ok, "version": "0.1.0"}
