"""Tiến trình con của Celery không được dùng chung kết nối DB với tiến trình cha.

Quan sát ngày 2026-08-16: bấm Dịch thì bước ``format_sub`` chết với
``psycopg.errors.DuplicatePreparedStatement: prepared statement "_pg3_0"
already exists``.

Nguyên nhân: ``celery_app.py`` gọi ``get_settings()`` ngay khi import, mà từ
khi cấu hình chuyển vào database, lời gọi đó mở luôn một kết nối. Kết nối ấy
nằm sẵn trong pool của TIẾN TRÌNH CHA, rồi Celery prefork nhân bản cả tiến
trình — hai con cùng thừa kế một socket, tức cùng một phiên PostgreSQL.
psycopg3 tự chuyển câu lệnh sang dạng prepared sau vài lần chạy và đặt tên
``_pg3_0``, ``_pg3_1``…; hai con đếm riêng nên cùng đòi tạo ``_pg3_0``.

Test chạy trong MỘT tiến trình nên không tái hiện được cú fork. Thứ khoá lại
được ở đây là điều kiện đủ: có người nghe tín hiệu ``worker_process_init``, và
người đó buông sạch kết nối thừa kế mà không đóng socket của cha.
"""

from __future__ import annotations

from weakref import ReferenceType

from celery.signals import worker_process_init
from reup_core.db import get_engine

from src.celery_app import _bo_ket_noi_db_thua_ke


def test_co_nguoi_nghe_worker_process_init() -> None:
    """Không mắc vào tín hiệu thì con vẫn dùng kết nối của cha."""
    #: `receivers` là list các cặp ``(khoá, ref)``; ref là weakref tới hàm để
    #: người nghe bị thu gom rác thì tín hiệu tự quên.
    nguoi_nghe = [
        ref() if isinstance(ref, ReferenceType) else ref for _, ref in worker_process_init.receivers
    ]
    assert _bo_ket_noi_db_thua_ke in nguoi_nghe


def test_bo_ket_noi_khong_dong_socket_cua_cha(monkeypatch) -> None:
    """Phải gọi ``dispose(close=False)``.

    ``dispose()`` mặc định ĐÓNG socket — mà socket đó là của tiến trình cha,
    đóng là giật mất kết nối cha và các con khác vẫn đang trỏ vào.
    """
    da_goi: dict[str, object] = {}

    class EngineGia:
        def dispose(self, close: bool = True) -> None:
            da_goi["close"] = close

    monkeypatch.setattr("reup_core.db.get_engine", lambda: EngineGia())
    _bo_ket_noi_db_thua_ke()

    assert da_goi == {"close": False}


def test_pool_rong_sau_khi_bo_ket_noi() -> None:
    """Sau khi buông, pool không còn giữ kết nối nào của cha."""
    engine = get_engine()
    try:
        engine.connect().close()  # đẩy một kết nối vào pool
    except Exception:  # noqa: BLE001 - máy chạy test có thể không có PostgreSQL
        return

    assert engine.pool.checkedin() > 0
    _bo_ket_noi_db_thua_ke()
    assert engine.pool.checkedin() == 0
