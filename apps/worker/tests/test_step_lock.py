"""Một bước của một video không được chạy hai lần cùng lúc.

Quan sát thật 2026-08-14: hai task ``reup.translate_video`` cùng chạy cho CÙNG
một video (hai tiến trình con của worker, cách nhau 15 giây). Hậu quả kép:

- đốt gấp đôi hạn mức LLM vốn đã chật;
- hai bản dịch ghi đè lẫn nhau, kết quả cuối tuỳ bên nào xong sau.

Dùng khoá Redis CÓ HẠN DÙNG chứ không phải cờ trong DB: worker chết giữa chừng
thì khoá tự hết hạn. Cờ trong DB sẽ kẹt ``running`` vĩnh viễn và chặn luôn mọi
lần chạy lại — đúng thứ đã phải sửa tay hai dòng ``job_runs`` hôm đó.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from reup_core.enums import PipelineStep, VideoStatus
from reup_core.models import Video
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tasks import base as task_base


@pytest.fixture
def khoa_gia(monkeypatch):
    """Khoá giả trong bộ nhớ (thay Redis) + SQLite trong RAM (thay Postgres).

    Bước pipeline vẫn tạo ``JobRun`` thật nên phải có session thật — dùng đúng
    khuôn của ``test_task_contract.py``.
    """
    dang_giu: set[str] = set()

    def _lay(key: str, ttl: int) -> bool:
        if key in dang_giu:
            return False
        dang_giu.add(key)
        return True

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

    monkeypatch.setattr(task_base, "_lay_khoa", _lay)
    monkeypatch.setattr(task_base, "_tra_khoa", lambda key: dang_giu.discard(key))
    monkeypatch.setattr(task_base, "session_scope", fake_scope)
    monkeypatch.setattr(task_base.prog, "progress", lambda *a, **k: None)
    monkeypatch.setattr(task_base.prog, "status_changed", lambda *a, **k: None)
    return {"dang_giu": dang_giu, "scope": fake_scope}


def _them_video(scope) -> str:
    with scope() as session:
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
        return str(video.id)


def _buoc(than_ham):
    return task_base.pipeline_step(PipelineStep.TRANSLATE)(than_ham)


def test_khong_ai_giu_khoa_thi_chay_binh_thuong(khoa_gia) -> None:
    da_chay: list[int] = []
    buoc = _buoc(lambda session, video: da_chay.append(1) or {})

    buoc(_them_video(khoa_gia["scope"]))

    assert da_chay == [1]


def test_dang_co_nguoi_giu_khoa_thi_bo_qua_khong_chay_lai(khoa_gia) -> None:
    """Task thứ hai cho cùng video phải THÀNH KHÔNG LÀM GÌ, không phải lỗi.

    Chạy trùng là thao tác thừa, không phải hỏng hóc — đánh dấu video lỗi sẽ
    làm người dùng hoảng vô cớ.
    """
    so_lan: list[int] = []
    vid = _them_video(khoa_gia["scope"])
    buoc = _buoc(lambda session, video: so_lan.append(1) or {})

    khoa_gia["dang_giu"].add(f"reup:lock:translate:{vid}")
    ket_qua = buoc(vid)

    assert so_lan == []
    assert ket_qua == vid


def test_hai_video_khac_nhau_khong_chan_nhau(khoa_gia) -> None:
    so_lan: list[int] = []
    buoc = _buoc(lambda session, video: so_lan.append(1) or {})

    buoc(_them_video(khoa_gia["scope"]))
    buoc(_them_video(khoa_gia["scope"]))

    assert len(so_lan) == 2


def test_tra_khoa_sau_khi_xong(khoa_gia) -> None:
    buoc = _buoc(lambda session, video: {})

    buoc(_them_video(khoa_gia["scope"]))

    assert khoa_gia["dang_giu"] == set(), "xong phải trả khoá, không giữ mãi"


def test_tra_khoa_ca_khi_buoc_that_bai(khoa_gia) -> None:
    """Hỏng mà không trả khoá thì video đó kẹt tới khi khoá hết hạn."""

    def _hong(session, video):
        raise RuntimeError("hỏng giữa chừng")

    buoc = _buoc(_hong)

    with pytest.raises(RuntimeError):
        buoc(_them_video(khoa_gia["scope"]))

    assert khoa_gia["dang_giu"] == set()
