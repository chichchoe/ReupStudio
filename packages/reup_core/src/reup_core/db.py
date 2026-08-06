"""Engine và session factory dùng chung (đồng bộ, cho worker và alembic)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal = None


def database_url() -> str:
    return os.getenv(
        "DATABASE_URL", "postgresql+psycopg://reup:reup@localhost:5432/reup"
    )


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            database_url(), pool_pre_ping=True, pool_size=5, max_overflow=10
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Session tự commit khi thoát bình thường, rollback khi có lỗi."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
