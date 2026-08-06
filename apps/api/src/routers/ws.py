from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    manager = ws.app.state.ws_manager
    await manager.connect(ws)
    try:
        while True:
            # Giữ kết nối sống; client có thể gửi ping hoặc lệnh subscribe.
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)
