"""Hợp đồng của lớp ``tasks/``: task Celery nhận đúng ``video_id``, và không
bao giờ để lỗi rơi vào khoảng trống.

Sinh ra từ một lỗi thật: ``download_video_task`` khai báo ``bind=True``, mà
``bind=True`` bảo Celery chèn ``self`` vào **vị trí tham số đầu tiên** — đúng
chỗ ``pipeline_step.wrapper`` đang đợi ``video_id``. Hậu quả: bước tải chết
100% với ``ValueError: badly formed hexadecimal UUID string``, và vì lỗi nổ
TRƯỚC khối ``try`` nên không ai ghi trạng thái lại — video nằm ``queued`` vĩnh
viễn, giao diện hiện "đang chờ" mãi mãi.

Hai bài test dưới đây khoá cả hai mặt của lỗi đó, cho MỌI bước pipeline chứ
không riêng bước tải. Không cần Postgres: SQLite trong RAM, đúng khuôn
``test_video_render_variants.py``.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from reup_core.enums import PipelineStep, VideoStatus
from reup_core.models import JobRun, Video
from reup_core.models.base import Base
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.tasks import base as task_base
from src.tasks.video import _STEP_TASKS


@pytest.fixture
def sqlite_scope(monkeypatch):
    """Thay ``session_scope`` của worker bằng SQLite trong RAM.

    Trả về chính ``sessionmaker`` để bài test tự mở session mà soi kết quả sau
    khi task chạy xong.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def fake_scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(task_base, "session_scope", fake_scope)
    #: Tiến trình bắn qua Redis — trong test không có Redis, cho thành no-op.
    monkeypatch.setattr(task_base.prog, "progress", lambda *a, **k: None)
    monkeypatch.setattr(task_base.prog, "status_changed", lambda *a, **k: None)
    return factory


def add_video(session) -> Video:
    video = Video(
        source_platform="douyin",
        source_video_id=uuid.uuid4().hex[:12],
        source_url="https://www.douyin.com/video/1",
        status=VideoStatus.QUEUED.value,
        flags={},
        process_config={},
    )
    session.add(video)
    session.commit()
    return video


@pytest.mark.parametrize("step,task", sorted(_STEP_TASKS.items(), key=lambda kv: kv[0].value))
def test_task_nhan_dung_video_id_o_tham_so_dau(step, task, monkeypatch):
    """Mọi task pipeline phải nhận ``video_id`` ở tham số đầu.

    ``bind=True`` (hoặc bất kỳ decorator nào chèn thêm tham số) sẽ làm bài test
    này đỏ — đó chính là mục đích.
    """
    nhan_duoc: list[object] = []

    def spy(session, video_id):
        nhan_duoc.append(video_id)
        raise RuntimeError("dừng sớm — chỉ cần biết tham số nhận được")

    monkeypatch.setattr(task_base, "load_video", spy)
    monkeypatch.setattr(task_base, "session_scope", _scope_rong)
    monkeypatch.setattr(task_base.prog, "progress", lambda *a, **k: None)
    monkeypatch.setattr(task_base.prog, "status_changed", lambda *a, **k: None)

    video_id = str(uuid.uuid4())

    #: Đúng cái Celery gọi để kiểm chữ ký trong ``apply_async`` — tức đường
    #: chain chạy thật. ``apply()`` KHÔNG kiểm bước này, nên chỉ dùng ``apply()``
    #: là để lọt nguyên một lớp lỗi: ``functools.wraps`` gắn ``__wrapped__``
    #: khiến Celery đọc nhầm chữ ký hàm bên trong ``(session, video)`` rồi từ
    #: chối lời gọi một tham số.
    task.__header__(video_id)

    task.apply(args=[video_id])

    assert nhan_duoc, f"{task.name} không gọi tới load_video"
    assert nhan_duoc[0] == video_id, (
        f"{task.name} nhận {nhan_duoc[0]!r} thay vì video_id — "
        "gần như chắc chắn do bind=True chèn self vào tham số đầu"
    )


@contextmanager
def _scope_rong():
    yield None


def test_buoc_that_bai_thi_video_bi_danh_dau_loi(sqlite_scope, monkeypatch):
    """Bước hỏng phải để lại dấu vết: video ERROR + có ``error_message`` + JobRun failed.

    Không có phần này thì video kẹt ``queued`` im lặng và người dùng ngồi chờ
    một thứ đã chết từ lâu.
    """
    with sqlite_scope() as session:
        video = add_video(session)
        video_id = str(video.id)

    @task_base.pipeline_step(PipelineStep.DOWNLOAD)
    def task_hong(session, video):
        raise RuntimeError("nền tảng chặn")

    with pytest.raises(RuntimeError):
        task_hong(video_id)

    with sqlite_scope() as session:
        video = session.get(Video, uuid.UUID(video_id))
        assert video.status == VideoStatus.ERROR.value
        assert video.error_message and "nền tảng chặn" in video.error_message
        runs = session.scalars(select(JobRun).where(JobRun.video_id == video.id)).all()
        assert [r.status for r in runs] == ["failed"]


def test_doi_so_dau_khong_phai_video_id_thi_bao_loi_ro_rang(sqlite_scope):
    """Truyền nhầm thứ khác vào chỗ ``video_id`` phải nổ kèm lời giải thích.

    ``ValueError: badly formed hexadecimal UUID string`` là thông báo vô dụng —
    người đọc log không thể suy ra nguyên nhân là ``bind=True``.
    """

    @task_base.pipeline_step(PipelineStep.DOWNLOAD)
    def task_bat_ky(session, video):  # pragma: no cover - không bao giờ tới đây
        return {}

    class TaskGia:
        def __repr__(self) -> str:
            return "<@task: reup.download_video>"

    with pytest.raises(task_base.TaskArgumentError) as exc:
        task_bat_ky(TaskGia())

    assert "video_id" in str(exc.value)
    assert "bind=True" in str(exc.value)
