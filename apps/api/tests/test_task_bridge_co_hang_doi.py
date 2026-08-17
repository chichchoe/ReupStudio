"""Mọi lời gọi ``send_task`` của API PHẢI truyền ``queue``.

App Celery của API là app RIÊNG, không mang ``task_routes`` của worker. Thiếu
``queue=`` thì task rơi vào hàng mặc định ``celery`` — hàng mà không worker nào
nghe. Endpoint vẫn trả 200/202, không lỗi, không log, và việc không bao giờ
chạy.

Gặp thật ngày 2026-08-17 với ``doc_lai_sau_khi_sua``: người dùng bấm "Lưu và
đọc lại", API trả 200, giọng không được đọc lại. Chỉ lộ ra khi soi hàng đợi
Redis thấy key ``celery`` mọc lên.

``test_dinh_tuyen_task.py`` bên worker KHÔNG bắt được lỗi này — nó kiểm bảng
định tuyến của worker, còn chỗ hỏng nằm ở phía người GỬI.
"""

from __future__ import annotations

import ast
from pathlib import Path

NGUON = Path(__file__).resolve().parents[1] / "src" / "services" / "task_bridge.py"


def _cac_loi_goi_send_task() -> list[ast.Call]:
    cay = ast.parse(NGUON.read_text(encoding="utf-8"))
    return [
        n
        for n in ast.walk(cay)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "send_task"
    ]


def test_co_it_nhat_vai_loi_goi() -> None:
    """Chốt chặn cho chính test này: đọc nhầm file thì nó phải đỏ."""
    assert len(_cac_loi_goi_send_task()) >= 5


def test_moi_send_task_deu_truyen_queue() -> None:
    thieu = [
        goi.args[0].value if goi.args and isinstance(goi.args[0], ast.Constant) else "?"
        for goi in _cac_loi_goi_send_task()
        if not any(k.arg == "queue" for k in goi.keywords)
    ]

    assert not thieu, f"send_task thiếu queue= nên task sẽ đi vào hàng chết: {thieu}"
