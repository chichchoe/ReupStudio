"""Video không có lời thoại vẫn phải được CHUẨN HOÁ, không được trả bản gốc.

Trước đây ``render_video_task`` gặp video không có cue nào thì ``copyfile``
nguyên bản gốc sang thư mục ``out/`` rồi đánh dấu READY. Hệ thống báo "xong"
trong khi thứ giao ra đúng bằng thứ nhận vào — đây là một trong những lý do
người dùng thấy "nó vẫn chỉ là video gốc, không phải video reup".

Quyết định (chốt 2026-08-14): vẫn cắt 9:16 và chèn hook, chỉ bỏ phần phụ đề.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.render import render_normalized
from src.pipeline.shortform.safe_area import SafeArea

TIKTOK = SafeArea(top=0.06, bottom=0.18, left=0.05, right=0.20)


@pytest.fixture
def spy(monkeypatch, tmp_path):
    """Chặn mọi lệnh gọi ffmpeg, ghi lại đã gọi cái gì với tham số nào."""
    goi: dict[str, list] = {"reframe": [], "burn": [], "trim": []}

    def _fake_reframe(src, dst, **kw):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        goi["reframe"].append((src, dst))
        return dst

    def _fake_burn(src, subtitle_file, dst, **kw):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        goi["burn"].append((src, Path(subtitle_file), dst, kw))
        return dst

    def _fake_trim(src, dst, **kw):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        goi["trim"].append((src, dst, kw))
        return dst

    import src.pipeline.render as mod

    monkeypatch.setattr(mod, "reframe_blur", _fake_reframe)
    monkeypatch.setattr(mod, "reframe_crop", _fake_reframe)
    monkeypatch.setattr(mod, "burn_subtitles", _fake_burn)
    monkeypatch.setattr(mod, "trim_video", _fake_trim)
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    return goi


def _nguon(tmp_path: Path) -> Path:
    src = tmp_path / "goc.mp4"
    src.write_bytes(b"noi-dung-goc")
    return src


def test_nguon_ngang_van_duoc_doi_sang_doc(spy, tmp_path) -> None:
    render_normalized(
        "vid-ngang", _nguon(tmp_path), safe=TIKTOK, video_width=1920, video_height=1080
    )
    assert spy["reframe"], "nguồn ngang phải được reframe sang 9:16"


def test_nguon_da_doc_thi_khong_reframe_lai(spy, tmp_path) -> None:
    """Scale đi scale lại chỉ làm giảm chất lượng."""
    render_normalized("vid-doc", _nguon(tmp_path), safe=TIKTOK, video_width=1080, video_height=1920)
    assert spy["reframe"] == []


def test_co_hook_thi_burn_kem_filter_hook(spy, tmp_path) -> None:
    render_normalized(
        "vid-hook",
        _nguon(tmp_path),
        safe=TIKTOK,
        video_width=1080,
        video_height=1920,
        hook_text="Xem hết nhé",
    )
    assert len(spy["burn"]) == 1
    assert spy["burn"][0][3]["hook_filter"].startswith("drawtext=")


def test_khong_hook_thi_chi_cat_khong_re_encode(spy, tmp_path) -> None:
    """Không có gì để vẽ lên hình thì đừng encode lại — vừa chậm vừa mất chất."""
    render_normalized(
        "vid-khong-hook", _nguon(tmp_path), safe=TIKTOK, video_width=1080, video_height=1920
    )
    assert spy["burn"] == []
    assert len(spy["trim"]) == 1


def test_khong_bao_gio_giao_ra_dung_file_goc(spy, tmp_path) -> None:
    """Chốt chặn cho đúng lỗi cũ: file đích không được là bản sao y hệt nguồn."""
    src = _nguon(tmp_path)
    dst = render_normalized("vid-khong-copy", src, safe=TIKTOK, video_width=1920, video_height=1080)
    assert dst != src
    assert dst.read_bytes() != src.read_bytes()


def test_chay_lai_lan_hai_khong_lam_lai_tu_dau(spy, tmp_path) -> None:
    """Luật số 4 CLAUDE.md — mỗi bước pipeline phải idempotent."""
    src = _nguon(tmp_path)
    render_normalized("vid-idem", src, safe=TIKTOK, video_width=1080, video_height=1920)
    so_lan_dau = len(spy["trim"])

    render_normalized("vid-idem", src, safe=TIKTOK, video_width=1080, video_height=1920)

    assert len(spy["trim"]) == so_lan_dau, "file đã có thì phải bỏ qua"
