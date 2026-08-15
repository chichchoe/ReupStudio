"""M4-BE-02 — API render nhiều nền tảng cùng lúc.

Dùng TestClient tối giản + SQLite trong RAM qua StaticPool (bắt chước
``test_retry.py``): monkeypatch ``task_bridge.render_variants`` để kiểm task
Celery được đẩy đi đúng một lần, KHÔNG chờ nó chạy thật.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from reup_core.enums import VideoStatus
from reup_core.models import PlatformLimit, RenderVariant, Video
from reup_core.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db import get_db
from src.errors import ApiError, api_error_handler
from src.routers import render as render_router
from src.services import task_bridge

#: Chỉ seed 3/5 nền tảng — dùng để test cả trường hợp nền tảng hợp lệ (nằm
#: trong enum Platform) nhưng CHƯA có dòng platform_limits (facebook/instagram
#: /zalo cố tình bỏ trống).
_SEEDED_PLATFORMS = ["tiktok", "youtube", "facebook"]


def _seed_platform_limits(session: Session) -> None:
    for platform in _SEEDED_PLATFORMS:
        session.add(
            PlatformLimit(
                platform=platform,
                max_duration_sec=0,
                max_title_len=150,
                max_desc_len=2200,
                max_hashtags=30,
                safe_daily_posts=3,
                aspect_ratios=["9:16"],
                safe_area={"top": 0.06, "bottom": 0.18, "left": 0.05, "right": 0.20},
            )
        )
    session.commit()


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        _seed_platform_limits(session)

    def override_get_db():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    dispatched: list[dict] = []

    def fake_render_variants(video_id):
        # Mở session MỚI, tách biệt transaction của request -> đọc đúng cái
        # đã thật sự commit xuống DB tại thời điểm task_bridge được gọi
        # (bắt chước fake_retry_from ở test_retry.py).
        with Session(engine) as check:
            video = check.get(Video, video_id)
            dispatched.append(
                {
                    "video_id": video_id,
                    "process_config_khi_dispatch": dict(video.process_config),
                }
            )
        return "fake-task-id"

    monkeypatch.setattr(task_bridge, "render_variants", fake_render_variants)

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(render_router.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield {
            "client": client,
            "engine": engine,
            "session_factory": session_factory,
            "dispatched": dispatched,
        }


def _tao_video(session_factory, **kwargs) -> uuid.UUID:
    defaults = {
        "source_platform": "douyin",
        "source_video_id": str(uuid.uuid4()),
        "source_url": "https://www.douyin.com/video/123",
        "status": VideoStatus.READY,
        "flags": {},
        "process_config": {},
    }
    defaults.update(kwargs)
    with session_factory() as session:
        video = Video(**defaults)
        session.add(video)
        session.commit()
        session.refresh(video)
        return video.id


def _tao_variant(session_factory, video_id: uuid.UUID, **kwargs) -> uuid.UUID:
    defaults = {
        "video_id": video_id,
        "target_platform": "tiktok",
        "part_index": 1,
        "part_total": 1,
        "config_snapshot": {},
    }
    defaults.update(kwargs)
    with session_factory() as session:
        variant = RenderVariant(**defaults)
        session.add(variant)
        session.commit()
        session.refresh(variant)
        return variant.id


# --- POST /videos/{id}/render ---


def test_render_3_nen_tang_tra_202_va_day_task_dung_mot_lan(ctx) -> None:
    video_id = _tao_video(ctx["session_factory"])

    resp = ctx["client"].post(
        f"/api/v1/videos/{video_id}/render",
        json={"target_platforms": ["tiktok", "youtube", "facebook"], "preset_overrides": {}},
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["task_id"] == "fake-task-id"

    assert len(ctx["dispatched"]) == 1
    dispatch = ctx["dispatched"][0]
    assert dispatch["video_id"] == video_id
    assert dispatch["process_config_khi_dispatch"]["target_platforms"] == [
        "tiktok",
        "youtube",
        "facebook",
    ]


def test_render_ghi_preset_overrides_vao_process_config(ctx) -> None:
    video_id = _tao_video(ctx["session_factory"])

    resp = ctx["client"].post(
        f"/api/v1/videos/{video_id}/render",
        json={
            "target_platforms": ["tiktok"],
            "preset_overrides": {"reframe_mode": "crop", "hook_text": "Xem ngay!"},
        },
    )

    assert resp.status_code == 202
    dispatch = ctx["dispatched"][0]
    config = dispatch["process_config_khi_dispatch"]
    assert config["reframe_mode"] == "crop"
    assert config["hook_text"] == "Xem ngay!"
    assert config["target_platforms"] == ["tiktok"]


def test_render_nen_tang_khong_thuoc_enum_tra_422_khong_day_task(ctx) -> None:
    video_id = _tao_video(ctx["session_factory"])

    resp = ctx["client"].post(
        f"/api/v1/videos/{video_id}/render",
        json={"target_platforms": ["twitter"], "preset_overrides": {}},
    )

    assert resp.status_code == 422
    assert ctx["dispatched"] == []


def test_render_nen_tang_hop_le_nhung_chua_co_platform_limits_tra_422(ctx) -> None:
    """ "instagram" hợp lệ trong enum Platform nhưng chưa được seed vào
    platform_limits (xem ``_SEEDED_PLATFORMS``) -> phải bị chặn ở service,
    KHÔNG lọt xuống worker rồi mới hỏng.
    """
    video_id = _tao_video(ctx["session_factory"])

    resp = ctx["client"].post(
        f"/api/v1/videos/{video_id}/render",
        json={"target_platforms": ["tiktok", "instagram"], "preset_overrides": {}},
    )

    assert resp.status_code == 422
    assert ctx["dispatched"] == []


def test_render_danh_sach_rong_tra_422(ctx) -> None:
    video_id = _tao_video(ctx["session_factory"])

    resp = ctx["client"].post(
        f"/api/v1/videos/{video_id}/render",
        json={"target_platforms": [], "preset_overrides": {}},
    )

    assert resp.status_code == 422
    assert ctx["dispatched"] == []


def test_render_video_da_xoa_mem_tra_notfound(ctx) -> None:
    video_id = _tao_video(ctx["session_factory"])
    with ctx["session_factory"]() as session:
        video = session.get(Video, video_id)
        video.deleted_at = __import__("datetime").datetime.now()
        session.commit()

    resp = ctx["client"].post(
        f"/api/v1/videos/{video_id}/render",
        json={"target_platforms": ["tiktok"], "preset_overrides": {}},
    )

    assert resp.status_code == 404
    assert ctx["dispatched"] == []


def test_render_video_khong_ton_tai_tra_notfound(ctx) -> None:
    resp = ctx["client"].post(
        f"/api/v1/videos/{uuid.uuid4()}/render",
        json={"target_platforms": ["tiktok"], "preset_overrides": {}},
    )

    assert resp.status_code == 404
    assert ctx["dispatched"] == []


# --- GET /videos/{id}/variants ---


def test_liet_ke_variants_tra_dung_cac_ban_ghi_sap_on_dinh(ctx) -> None:
    video_id = _tao_video(ctx["session_factory"])
    _tao_variant(ctx["session_factory"], video_id, target_platform="youtube", part_index=1)
    _tao_variant(ctx["session_factory"], video_id, target_platform="tiktok", part_index=2)
    _tao_variant(ctx["session_factory"], video_id, target_platform="tiktok", part_index=1)

    resp = ctx["client"].get(f"/api/v1/videos/{video_id}/variants")

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 3
    # Sắp ổn định theo (target_platform, part_index): tiktok p1, tiktok p2, youtube p1.
    thu_tu = [(item["target_platform"], item["part_index"]) for item in items]
    assert thu_tu == [("tiktok", 1), ("tiktok", 2), ("youtube", 1)]


def test_liet_ke_variants_video_khac_khong_lot_vao(ctx) -> None:
    video_a = _tao_video(ctx["session_factory"])
    video_b = _tao_video(ctx["session_factory"])
    _tao_variant(ctx["session_factory"], video_a, target_platform="tiktok")
    _tao_variant(ctx["session_factory"], video_b, target_platform="youtube")

    resp = ctx["client"].get(f"/api/v1/videos/{video_a}/variants")

    items = resp.json()
    assert len(items) == 1
    assert items[0]["target_platform"] == "tiktok"


def test_liet_ke_variants_video_da_xoa_mem_tra_notfound(ctx) -> None:
    video_id = _tao_video(ctx["session_factory"])
    with ctx["session_factory"]() as session:
        video = session.get(Video, video_id)
        video.deleted_at = __import__("datetime").datetime.now()
        session.commit()

    resp = ctx["client"].get(f"/api/v1/videos/{video_id}/variants")

    assert resp.status_code == 404


# --- GET /variants/{id}/file ---


def test_tai_file_variant_chua_co_file_tra_notfound(ctx) -> None:
    video_id = _tao_video(ctx["session_factory"])
    variant_id = _tao_variant(ctx["session_factory"], video_id, out_path=None)

    resp = ctx["client"].get(f"/api/v1/variants/{variant_id}/file")

    assert resp.status_code == 404


def test_tai_file_variant_khong_ton_tai_tra_notfound(ctx) -> None:
    resp = ctx["client"].get(f"/api/v1/variants/{uuid.uuid4()}/file")

    assert resp.status_code == 404


def test_tai_file_variant_cua_video_da_xoa_mem_tra_notfound(ctx, tmp_path) -> None:
    """Finding review coordinator: xoá mềm video KHÔNG xoá dòng render_variants
    (``ondelete="CASCADE"`` chỉ chạy khi hard-delete) — nếu không kiểm riêng,
    ai còn giữ ``variant_id`` vẫn tải được file dù video "đã xoá". File THẬT
    còn tồn tại trên đĩa (không phải ca thiếu file) để khẳng định chặn đúng vì
    video cha bị xoá, không phải vì thiếu file.
    """
    video_id = _tao_video(ctx["session_factory"])
    out_file = tmp_path / "tiktok_p1.mp4"
    out_file.write_bytes(b"fake mp4 content")
    variant_id = _tao_variant(ctx["session_factory"], video_id, out_path=str(out_file))
    with ctx["session_factory"]() as session:
        video = session.get(Video, video_id)
        video.deleted_at = __import__("datetime").datetime.now()
        session.commit()

    resp = ctx["client"].get(f"/api/v1/variants/{variant_id}/file")

    assert resp.status_code == 404


def test_tai_file_variant_da_render_tra_ve_file_that(ctx, tmp_path) -> None:
    video_id = _tao_video(ctx["session_factory"])
    out_file = tmp_path / "tiktok_p1.mp4"
    out_file.write_bytes(b"fake mp4 content")
    variant_id = _tao_variant(ctx["session_factory"], video_id, out_path=str(out_file))

    resp = ctx["client"].get(f"/api/v1/variants/{variant_id}/file")

    assert resp.status_code == 200
    assert resp.content == b"fake mp4 content"
