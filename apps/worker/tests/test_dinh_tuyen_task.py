"""Mọi task trong chuỗi pipeline phải có hàng đợi mà worker thật sự nghe.

Quan sát ngày 2026-08-15: thêm hai task M3 vào chuỗi, chain được gửi đi, KHÔNG
có lỗi nào trong log, và video đứng im mãi mãi. Nguyên nhân: task không khai
trong ``task_routes`` nên rơi vào hàng mặc định ``celery``, mà worker chỉ nghe
``download,media,gpu,upload``.

Loại hỏng này không để lại dấu vết nào — không exception, không log lỗi, chỉ là
im lặng — nên phải có test khoá lại.
"""

from __future__ import annotations

from src.celery_app import app
from src.tasks.video import _STEP_TASKS

#: Đúng danh sách hàng đợi mà lệnh chạy worker trong Makefile đang nghe.
HANG_DOI_CO_NGUOI_NGHE = {"download", "media", "gpu", "upload"}


def test_moi_buoc_pipeline_deu_co_dinh_tuyen() -> None:
    tuyen = app.conf.task_routes or {}
    thieu = [t.name for t in _STEP_TASKS.values() if t.name not in tuyen]

    assert not thieu, f"task không có hàng đợi, sẽ đứng im không báo lỗi: {thieu}"


def test_moi_dinh_tuyen_deu_tro_toi_hang_co_nguoi_nghe() -> None:
    lac = {
        ten: cau_hinh["queue"]
        for ten, cau_hinh in (app.conf.task_routes or {}).items()
        if cau_hinh.get("queue") not in HANG_DOI_CO_NGUOI_NGHE
    }

    assert not lac, f"hàng đợi không có worker nào nghe: {lac}"
