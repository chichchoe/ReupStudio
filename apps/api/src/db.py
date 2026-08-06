"""Session dependency cho FastAPI."""

from __future__ import annotations

from collections.abc import Iterator

from reup_core.db import get_session_factory
from sqlalchemy.orm import Session


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
