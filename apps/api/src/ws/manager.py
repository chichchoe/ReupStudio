"""Cầu nối Redis pub/sub → WebSocket.

Worker publish tiến trình lên Redis; API subscribe rồi định tuyến xuống đúng
client đã subscribe kênh tương ứng. Frontend KHÔNG polling.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any

import redis.asyncio as aioredis
from fastapi import WebSocket
from reup_core.db import session_scope
from reup_core.logging import get_logger

from ..services import queue_service

log = get_logger(__name__)

#: Kênh Redis worker dùng để bắn sự kiện.
CHANNEL_PATTERN = "reup:*"

#: Số topic tối đa một kết nối được subscribe cùng lúc — chặn client bơm một
#: mảng lớn tuỳ ý làm set tăng trưởng vô hạn trong bộ nhớ server.
MAX_SUBSCRIPTIONS_PER_CLIENT = 500

#: Tiền tố kênh cần tính lại số liệu hàng chờ khi có sự kiện mới.
_STATUS_CHANNEL_PREFIX = "reup:status:"


def topic_of(redis_channel: str) -> str | None:
    """Ánh xạ kênh Redis sang topic mà client subscribe.

    reup:progress:<id> -> video:<id>; reup:status:<id> -> video:<id>;
    reup:queue -> queue; reup:alert -> alert; khác -> None.
    """
    if redis_channel.startswith("reup:progress:"):
        video_id = redis_channel.removeprefix("reup:progress:")
        return f"video:{video_id}" if video_id else None
    if redis_channel.startswith(_STATUS_CHANNEL_PREFIX):
        video_id = redis_channel.removeprefix(_STATUS_CHANNEL_PREFIX)
        return f"video:{video_id}" if video_id else None
    if redis_channel == "reup:queue":
        return "queue"
    if redis_channel == "reup:alert":
        return "alert"
    return None


def should_send(topic: str, subscriptions: set[str]) -> bool:
    """alert luôn gửi cho mọi client. Còn lại chỉ gửi khi đã subscribe."""
    if topic == "alert":
        return True
    return topic in subscriptions


class WsManager:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._clients: dict[WebSocket, set[str]] = {}
        self._task: asyncio.Task | None = None
        self._redis: aioredis.Redis | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients[ws] = set()
        await ws.send_json({"type": "hello", "clients": len(self._clients)})

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.pop(ws, None)

    def subscribe(self, ws: WebSocket, topics: Iterable[str]) -> None:
        subscriptions = self._clients.setdefault(ws, set())
        for topic in topics:
            if len(subscriptions) >= MAX_SUBSCRIPTIONS_PER_CLIENT:
                log.warning("ws.subscription_limit_reached", limit=MAX_SUBSCRIPTIONS_PER_CLIENT)
                break
            subscriptions.add(topic)

    def unsubscribe(self, ws: WebSocket, topics: Iterable[str]) -> None:
        subscriptions = self._clients.get(ws)
        if subscriptions is not None:
            subscriptions.difference_update(topics)

    async def broadcast(self, topic: str, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws, subscriptions in list(self._clients.items()):
            if not should_send(topic, subscriptions):
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def _listen(self) -> None:
        while True:
            try:
                self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
                pubsub = self._redis.pubsub()
                await pubsub.psubscribe(CHANNEL_PATTERN)
                log.info("ws.subscribed", pattern=CHANNEL_PATTERN)
                async for message in pubsub.listen():
                    if message.get("type") != "pmessage":
                        continue
                    await self._handle_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # kết nối Redis rớt — thử lại sau 3 giây
                log.warning("ws.redis_error", error=str(exc))
                await asyncio.sleep(3)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        channel = message.get("channel")
        if not isinstance(channel, str):
            return
        topic = topic_of(channel)
        if topic is None:
            log.warning("ws.unknown_channel", channel=channel)
            return
        try:
            payload = json.loads(message["data"])
        except (ValueError, TypeError):
            log.warning("ws.invalid_payload", channel=channel)
            return
        await self.broadcast(topic, payload)
        if channel.startswith(_STATUS_CHANNEL_PREFIX):
            await self._push_queue_counts()

    async def _push_queue_counts(self) -> None:
        # Phần chạm DB là đồng bộ, có thể chờ tới pool_timeout (mặc định 30s)
        # khi Postgres chậm/pool cạn — chạy trong thread riêng để không chặn
        # event loop (mọi WebSocket/HTTP khác trên cùng worker sẽ bị đứng nếu
        # gọi trực tiếp trong coroutine này).
        try:
            counts = await asyncio.to_thread(_fetch_queue_counts)
        except Exception as exc:  # DB rớt không được làm sập vòng lặp pub/sub
            log.warning("ws.queue_counts_failed", error=str(exc))
            return
        await self.broadcast("queue", {"type": "queue", **counts})


def _fetch_queue_counts() -> dict[str, int]:
    """Hàm đồng bộ chạm DB — chỉ gọi qua ``asyncio.to_thread`` từ manager."""
    with session_scope() as db:
        return queue_service.queue_counts(db)
