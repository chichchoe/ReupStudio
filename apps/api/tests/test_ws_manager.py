"""M2-BE-01 — định tuyến WebSocket theo video_id và kênh queue.

Không cần Redis: kiểm hàm thuần topic_of/should_send, broadcast với client giả,
và queue_counts trên SQLite trong RAM.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid

import pytest
from reup_core.enums import VideoStatus
from reup_core.models import Video
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.services import queue_service
from src.ws.manager import WsManager, should_send, topic_of


class FakeWebSocket:
    """Client WebSocket giả — ghi mọi payload nhận được vào ``sent``."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


# --- topic_of ---


def test_topic_of_progress_map_sang_video() -> None:
    assert topic_of("reup:progress:abc") == "video:abc"


def test_topic_of_status_map_sang_video() -> None:
    assert topic_of("reup:status:abc") == "video:abc"


def test_topic_of_queue() -> None:
    assert topic_of("reup:queue") == "queue"


def test_topic_of_alert() -> None:
    assert topic_of("reup:alert") == "alert"


def test_topic_of_kenh_la_thi_tra_none() -> None:
    assert topic_of("reup:linh:tinh") is None
    assert topic_of("chuoi rac khong lien quan") is None


# --- should_send ---


def test_should_send_client_chi_nhan_video_da_subscribe() -> None:
    subs = {"video:a"}
    assert should_send("video:a", subs) is True
    assert should_send("video:b", subs) is False


def test_should_send_alert_luon_gui_du_khong_subscribe() -> None:
    assert should_send("alert", set()) is True


def test_should_send_queue_khi_da_subscribe_queue() -> None:
    assert should_send("queue", {"queue"}) is True
    assert should_send("queue", set()) is False


# --- broadcast: 2 tab cùng subscribe 1 video đều nhận được cùng payload ---


def test_hai_client_cung_subscribe_mot_video_deu_nhan_duoc_payload() -> None:
    manager = WsManager(redis_url="redis://unused")
    tab1, tab2 = FakeWebSocket(), FakeWebSocket()
    manager.subscribe(tab1, ["video:a"])
    manager.subscribe(tab2, ["video:a"])

    payload = {"type": "progress", "video_id": "a", "step": "render", "percent": 68}
    asyncio.run(manager.broadcast("video:a", payload))

    assert tab1.sent == [payload]
    assert tab2.sent == [payload]


def test_client_khong_subscribe_video_do_thi_khong_nhan() -> None:
    manager = WsManager(redis_url="redis://unused")
    tab_a, tab_b = FakeWebSocket(), FakeWebSocket()
    manager.subscribe(tab_a, ["video:a"])
    manager.subscribe(tab_b, ["video:b"])

    payload = {"type": "status", "video_id": "a", "status": "ready", "step": None}
    asyncio.run(manager.broadcast("video:a", payload))

    assert tab_a.sent == [payload]
    assert tab_b.sent == []


def test_client_chua_subscribe_gi_van_nhan_alert() -> None:
    manager = WsManager(redis_url="redis://unused")
    tab = FakeWebSocket()
    manager._clients[tab] = set()  # kết nối mới, chưa gửi lệnh subscribe nào

    alert_payload = {"type": "alert", "level": "error", "title": "x", "detail": ""}
    asyncio.run(manager.broadcast("alert", alert_payload))

    assert tab.sent == [alert_payload]


def test_unsubscribe_thi_thoi_nhan() -> None:
    manager = WsManager(redis_url="redis://unused")
    tab = FakeWebSocket()
    manager.subscribe(tab, ["video:a"])
    manager.unsubscribe(tab, ["video:a"])

    asyncio.run(manager.broadcast("video:a", {"type": "progress"}))

    assert tab.sent == []


# --- reup:status:* -> tính lại queue_counts -> đẩy cho client subscribe queue ---


def test_status_message_day_queue_cho_client_da_subscribe_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Không cần Redis/Postgres: mock thẳng queue_service.queue_counts."""
    monkeypatch.setattr(queue_service, "queue_counts", lambda db: {"active": 4, "pending": 12})

    manager = WsManager(redis_url="redis://unused")
    sub_queue, sub_video_khac = FakeWebSocket(), FakeWebSocket()
    manager.subscribe(sub_queue, ["queue"])
    manager.subscribe(sub_video_khac, ["video:khac"])

    status_payload = {"type": "status", "video_id": "abc", "status": "ready", "step": None}
    fake_redis_message = {
        "type": "pmessage",
        "channel": "reup:status:abc",
        "data": json.dumps(status_payload),
    }
    asyncio.run(manager._handle_message(fake_redis_message))

    # Client subscribe "queue" nhận payload queue vừa tính lại (không nhận
    # status vì không subscribe video:abc).
    assert sub_queue.sent == [{"type": "queue", "active": 4, "pending": 12}]
    # Client subscribe kênh khác thì không nhận gì cả — cả status lẫn queue.
    assert sub_video_khac.sent == []


def test_status_message_client_khong_subscribe_queue_thi_khong_nhan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(queue_service, "queue_counts", lambda db: {"active": 1, "pending": 2})

    manager = WsManager(redis_url="redis://unused")
    sub_video = FakeWebSocket()
    manager.subscribe(sub_video, ["video:abc"])

    fake_redis_message = {
        "type": "pmessage",
        "channel": "reup:status:abc",
        "data": json.dumps({"type": "status", "video_id": "abc", "status": "ready"}),
    }
    asyncio.run(manager._handle_message(fake_redis_message))

    # Nhận đúng sự kiện status của video mình subscribe, KHÔNG nhận queue.
    assert sub_video.sent == [{"type": "status", "video_id": "abc", "status": "ready"}]


# --- queue_counts trên SQLite ---


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _add_video(db: Session, *, status: VideoStatus, deleted: bool = False) -> Video:
    video = Video(
        source_platform="douyin",
        source_video_id=uuid.uuid4().hex[:12],
        source_url="https://www.douyin.com/video/1",
        status=status,
        flags={},
        process_config={},
        deleted_at=dt.datetime(2026, 1, 1) if deleted else None,
    )
    db.add(video)
    db.flush()
    return video


def test_queue_counts_dem_dung_running_va_queued(db: Session) -> None:
    _add_video(db, status=VideoStatus.RUNNING)
    _add_video(db, status=VideoStatus.RUNNING)
    _add_video(db, status=VideoStatus.QUEUED)
    _add_video(db, status=VideoStatus.READY)

    result = queue_service.queue_counts(db)

    assert result == {"active": 2, "pending": 1}


def test_queue_counts_bo_qua_video_da_xoa_mem(db: Session) -> None:
    _add_video(db, status=VideoStatus.RUNNING, deleted=True)
    _add_video(db, status=VideoStatus.QUEUED, deleted=True)
    _add_video(db, status=VideoStatus.RUNNING)

    result = queue_service.queue_counts(db)

    assert result == {"active": 1, "pending": 0}


def test_queue_counts_khong_co_video_nao_thi_tra_ve_0(db: Session) -> None:
    assert queue_service.queue_counts(db) == {"active": 0, "pending": 0}
