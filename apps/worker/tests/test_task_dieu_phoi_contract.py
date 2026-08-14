"""Ba task ĐIỀU PHỐI phải nhận đúng tham số qua đường Celery thật.

``test_task_contract.py`` chỉ khoá các task BƯỚC trong ``_STEP_TASKS``. Ba task
điều phối (``process_video``, ``retry_from_step``, ``translate_video_chain``)
không nằm trong dict đó nên chưa có gì canh.

Sinh ra từ một lỗi thật (2026-08-15): bản vá thêm hàm phụ ``_cac_buoc_retry``
chèn NGAY DƯỚI ``@app.task(name="reup.retry_from_step")``, nên decorator bọc
nhầm hàm phụ; ``retry_from_step`` thành hàm trần mà Celery không hề biết tới.
Sáu bài test viết cho ``_cac_buoc_retry`` vẫn xanh, vì đối tượng Task của Celery
gọi trực tiếp được hệt như hàm thường — chỉ khi bấm "xử lý lại" trên máy thật
mới lộ.

``__header__`` là đúng thứ Celery gọi để kiểm tham số trong ``apply_async``.
"""

from __future__ import annotations

import uuid

import pytest

from src.celery_app import app


@pytest.mark.parametrize(
    "ten_task",
    ["reup.process_video", "reup.translate_video_chain"],
)
def test_task_dieu_phoi_nhan_mot_video_id(ten_task: str) -> None:
    task = app.tasks[ten_task]

    task.__header__(str(uuid.uuid4()))


def test_retry_nhan_video_id_va_ten_buoc() -> None:
    """Đúng cách API gọi: ``send_task(args=[video_id, step])``."""
    task = app.tasks["reup.retry_from_step"]

    task.__header__(str(uuid.uuid4()), "transcribe")


def test_retry_goi_duoc_khi_khong_truyen_buoc() -> None:
    task = app.tasks["reup.retry_from_step"]

    task.__header__(str(uuid.uuid4()))


def test_ten_task_tro_dung_ham_dieu_phoi_chu_khong_phai_ham_phu() -> None:
    """Chốt chặn cho đúng lỗi đã xảy ra: decorator bọc nhầm hàm bên dưới nó."""
    assert app.tasks["reup.retry_from_step"].__name__ == "retry_from_step"
    assert app.tasks["reup.process_video"].__name__ == "process_video"
    assert app.tasks["reup.translate_video_chain"].__name__ == "translate_video_chain"
