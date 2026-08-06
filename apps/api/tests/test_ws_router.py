"""Finding #3 (review tổng M2) — ``_handle_client_message`` không được đứt kết
nối khi client gửi topic không phải chuỗi (dict, list lồng, số...).

``set.update()`` với phần tử không hashable (dict, list) ném ``TypeError``, lọt
lên nhánh ``except Exception: manager.disconnect(ws)`` ở ``websocket_endpoint``
— đóng kết nối im lặng, không log gì. Bài test này gọi thẳng
``_handle_client_message`` (đồng bộ, không cần dựng WebSocket thật).
"""

from __future__ import annotations

import json

from src.routers.ws import _handle_client_message
from src.ws.manager import WsManager


class FakeWebSocket:
    """Đại diện tối thiểu cho WebSocket — manager chỉ dùng làm khoá dict."""


def _manager() -> WsManager:
    return WsManager(redis_url="redis://unused")


def test_subscribe_chua_dict_khong_nem_loi_va_bi_loc_bo() -> None:
    manager = _manager()
    ws = FakeWebSocket()

    _handle_client_message(manager, ws, json.dumps({"subscribe": [{"video": "a"}]}))

    assert manager._clients[ws] == set()


def test_subscribe_chua_list_long_khong_nem_loi_va_bi_loc_bo() -> None:
    manager = _manager()
    ws = FakeWebSocket()

    _handle_client_message(manager, ws, json.dumps({"subscribe": [["video:a"]]}))

    assert manager._clients[ws] == set()


def test_subscribe_toan_so_bi_loc_het_khong_lot_vao_set() -> None:
    manager = _manager()
    ws = FakeWebSocket()

    _handle_client_message(manager, ws, json.dumps({"subscribe": [1, 2, 3]}))

    assert manager._clients[ws] == set()


def test_subscribe_khong_phai_list_thi_bo_qua_khong_dong_ket_noi() -> None:
    manager = _manager()
    ws = FakeWebSocket()

    _handle_client_message(manager, ws, json.dumps({"subscribe": "video:a"}))

    # Không có subscribe hợp lệ nào -> client thậm chí chưa có entry trong _clients.
    assert manager._clients.get(ws) is None


def test_subscribe_va_unsubscribe_cung_message_giu_lai_topic_dang_chuoi() -> None:
    manager = _manager()
    ws = FakeWebSocket()
    manager.subscribe(ws, ["video:old"])

    raw = json.dumps(
        {
            "subscribe": ["video:new", {"a": 1}],
            "unsubscribe": ["video:old", ["x"]],
        }
    )
    _handle_client_message(manager, ws, raw)

    assert manager._clients[ws] == {"video:new"}


def test_topic_hop_le_van_duoc_giu_lai_khi_tron_voi_rac() -> None:
    manager = _manager()
    ws = FakeWebSocket()

    _handle_client_message(
        manager, ws, json.dumps({"subscribe": ["video:a", {"x": 1}, 42, "video:b"]})
    )

    assert manager._clients[ws] == {"video:a", "video:b"}
