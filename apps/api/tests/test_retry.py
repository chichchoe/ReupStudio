"""Finding #1 (review tổng M2) — "Xử lý lại" không còn là no-op im lặng.

Video bị đánh dấu SKIPPED (dedup bắt nhầm) hoặc ERROR phải được reset về
QUEUED và gỡ cờ trùng lặp TRƯỚC khi task Celery được gửi đi — nếu không,
`worker/tasks/base.py` thấy status=SKIPPED thì tự bỏ qua toàn bộ chuỗi, và
người dùng thấy "Đã đưa vào hàng đợi xử lý lại" mà thực ra không có gì chạy.

Dùng TestClient tối giản (không lifespan, không WebSocket) + SQLite trong RAM
qua StaticPool để nhiều session cùng thấy một DB — nhờ vậy có thể kiểm đúng
thứ tự "commit TRƯỚC khi gửi task": hàm ``task_bridge.retry_from`` giả mở một
session MỚI để đọc lại trạng thái tại đúng thời điểm nó được gọi.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from reup_core.enums import VideoStatus
from reup_core.models import Video
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db import get_db
from src.errors import ApiError, api_error_handler
from src.routers import videos as videos_router
from src.services import task_bridge


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def override_get_db():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    dispatched: list[dict] = []

    def fake_retry_from(video_id, step):
        # Mở session MỚI, tách biệt transaction của request -> đọc đúng cái
        # đã thật sự commit xuống DB tại thời điểm task_bridge được gọi.
        with Session(engine) as check:
            video = check.get(Video, video_id)
            dispatched.append(
                {
                    "video_id": video_id,
                    "step": step,
                    "status_khi_dispatch": video.status,
                    "flags_khi_dispatch": dict(video.flags),
                }
            )
        return "fake-task-id"

    monkeypatch.setattr(task_bridge, "retry_from", fake_retry_from)

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(videos_router.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield {
            "client": client,
            "engine": engine,
            "session_factory": session_factory,
            "dispatched": dispatched,
        }


def _tao_video(session_factory, **kwargs) -> uuid.UUID:
    defaults = {
        "source_platform": "douyin",
        "source_video_id": str(uuid.uuid4()),
        "source_url": "https://www.douyin.com/video/123",
        "status": VideoStatus.QUEUED,
        "flags": {},
        "process_config": {},
    }
    defaults.update(kwargs)
    with session_factory() as session:
        video = Video(**defaults)
        session.add(video)
        session.commit()
        session.refresh(video)
        return video.id


# --- retry đơn lẻ: POST /videos/{id}/retry ---


def test_retry_video_skipped_reset_ve_queued_va_go_co_trung(ctx) -> None:
    original_id = str(uuid.uuid4())
    video_id = _tao_video(
        ctx["session_factory"],
        status=VideoStatus.SKIPPED,
        flags={"duplicate_of": original_id, "duplicate_reason": "phash"},
    )

    resp = ctx["client"].post(f"/api/v1/videos/{video_id}/retry")

    assert resp.status_code == 202
    # task_bridge phải được gọi đúng một lần, SAU KHI trạng thái đã commit.
    assert len(ctx["dispatched"]) == 1
    dispatch = ctx["dispatched"][0]
    assert dispatch["status_khi_dispatch"] == VideoStatus.QUEUED.value
    assert "duplicate_of" not in dispatch["flags_khi_dispatch"]
    assert "duplicate_reason" not in dispatch["flags_khi_dispatch"]

    with ctx["session_factory"]() as check:
        video = check.get(Video, video_id)
        assert video.status == VideoStatus.QUEUED.value
        assert "duplicate_of" not in video.flags
        assert "duplicate_reason" not in video.flags


def test_retry_video_error_reset_ve_queued_va_xoa_error_message(ctx) -> None:
    video_id = _tao_video(
        ctx["session_factory"],
        status=VideoStatus.ERROR,
        error_message="download: timeout",
    )

    resp = ctx["client"].post(f"/api/v1/videos/{video_id}/retry")

    assert resp.status_code == 202
    with ctx["session_factory"]() as check:
        video = check.get(Video, video_id)
        assert video.status == VideoStatus.QUEUED.value
        assert video.error_message is None


# --- retry hàng loạt: POST /videos/bulk, action=retry ---


def test_bulk_retry_reset_nhieu_video_skipped_truoc_khi_dispatch(ctx) -> None:
    ids = [
        _tao_video(
            ctx["session_factory"],
            status=VideoStatus.SKIPPED,
            flags={"duplicate_of": str(uuid.uuid4()), "duplicate_reason": "md5"},
        )
        for _ in range(3)
    ]

    resp = ctx["client"].post(
        "/api/v1/videos/bulk", json={"ids": [str(i) for i in ids], "action": "retry"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["affected"] == 3
    assert body["skipped"] == []
    assert len(ctx["dispatched"]) == 3
    for dispatch in ctx["dispatched"]:
        assert dispatch["status_khi_dispatch"] == VideoStatus.QUEUED.value
        assert "duplicate_of" not in dispatch["flags_khi_dispatch"]

    with ctx["session_factory"]() as check:
        for video_id in ids:
            video = check.get(Video, video_id)
            assert video.status == VideoStatus.QUEUED.value
            assert "duplicate_of" not in video.flags
