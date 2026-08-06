from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from reup_core.logging import get_logger

from ..ws.manager import WsManager

log = get_logger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    manager = ws.app.state.ws_manager
    await manager.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            _handle_client_message(manager, ws, raw)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


def _handle_client_message(manager: WsManager, ws: WebSocket, raw: str) -> None:
    """Đọc lệnh subscribe/unsubscribe từ client. JSON hỏng hoặc thiếu khoá hợp lệ
    thì bỏ qua message và log cảnh báo — KHÔNG đóng kết nối, KHÔNG raise.
    """
    try:
        data: Any = json.loads(raw)
    except (ValueError, TypeError):
        log.warning("ws.invalid_json", raw=raw[:200])
        return
    if not isinstance(data, dict):
        log.warning("ws.invalid_message", raw=raw[:200])
        return

    subscribe_topics = data.get("subscribe")
    unsubscribe_topics = data.get("unsubscribe")
    if not isinstance(subscribe_topics, list) and not isinstance(unsubscribe_topics, list):
        log.warning("ws.missing_subscribe_key", raw=raw[:200])
        return

    if isinstance(subscribe_topics, list):
        manager.subscribe(ws, subscribe_topics)
    if isinstance(unsubscribe_topics, list):
        manager.unsubscribe(ws, unsubscribe_topics)
