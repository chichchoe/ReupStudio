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
        # Không nuốt lỗi im lặng: đây là nhánh cuối cùng bắt mọi lỗi ngoài dự
        # kiến trong vòng lặp nhận message — phải log rõ để còn biết vì sao
        # một kết nối bị đóng.
        log.exception("ws.unexpected_error")
        manager.disconnect(ws)


def _handle_client_message(manager: WsManager, ws: WebSocket, raw: str) -> None:
    """Đọc lệnh subscribe/unsubscribe từ client. JSON hỏng hoặc thiếu khoá hợp lệ
    thì bỏ qua message và log cảnh báo — KHÔNG đóng kết nối, KHÔNG raise.

    Phần tử topic không phải chuỗi (dict, list, số...) bị lọc bỏ âm thầm (có
    log) thay vì đưa vào ``set`` — phần tử không hashable (dict/list) làm
    ``set.update()`` ném ``TypeError``, việc này từng làm đứt kết nối cả client
    vì lỗi lọt lên nhánh ``except Exception`` ở ``websocket_endpoint``.
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
        topics = _chi_giu_chuoi(subscribe_topics)
        if len(topics) != len(subscribe_topics):
            log.warning("ws.subscribe_non_str_dropped", raw=raw[:200])
        manager.subscribe(ws, topics)
    if isinstance(unsubscribe_topics, list):
        topics = _chi_giu_chuoi(unsubscribe_topics)
        if len(topics) != len(unsubscribe_topics):
            log.warning("ws.unsubscribe_non_str_dropped", raw=raw[:200])
        manager.unsubscribe(ws, topics)


def _chi_giu_chuoi(topics: list[Any]) -> list[str]:
    """Lọc chỉ giữ phần tử kiểu ``str`` — phần tử khác (dict, list, số...)
    không hashable hoặc không phải topic hợp lệ nên bị loại trước khi đưa
    vào ``set`` trong ``WsManager``.
    """
    return [t for t in topics if isinstance(t, str)]
