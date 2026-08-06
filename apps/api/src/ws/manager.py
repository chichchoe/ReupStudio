"""Cầu nối Redis pub/sub → WebSocket.

Worker publish tiến trình lên Redis; API subscribe rồi broadcast xuống mọi
client đang mở. Frontend KHÔNG polling.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import redis.asyncio as aioredis
from fastapi import WebSocket
from reup_core.logging import get_logger

log = get_logger(__name__)

#: Kênh Redis worker dùng để bắn sự kiện.
CHANNEL_PATTERN = "reup:*"


class WsManager:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._clients: set[WebSocket] = set()
        self._task: asyncio.Task | None = None
        self._redis: aioredis.Redis | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        await ws.send_json({"type": "hello", "clients": len(self._clients)})

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
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
                    try:
                        payload = json.loads(message["data"])
                    except (ValueError, TypeError):
                        continue
                    await self.broadcast(payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # kết nối Redis rớt — thử lại sau 3 giây
                log.warning("ws.redis_error", error=str(exc))
                await asyncio.sleep(3)
