"""Bản ``master`` phải là video DỌC 9:16, kể cả khi video có lời thoại.

Quan sát ngày 2026-08-15: render lại một video có lời thoại rồi đo file ra —
vẫn 320×240, đúng bằng khung nguồn. Nhánh KHÔNG lời thoại (``render_normalized``)
đã đổi khung từ hôm trước, nhưng nhánh CÓ lời thoại (``render_with_subtitles``)
thì chưa bao giờ đổi. Nghĩa là mọi video thật — video nào chẳng có người nói —
đều ra khung gốc.

CLAUDE.md, mục ngữ cảnh nghiệp vụ: "Video dọc 9:16 là mặc định."

Cái bẫy khi sửa: file ASS phải dựng theo khung SAU khi đổi, không phải khung
nguồn. Dựng theo khung nguồn thì lề và cỡ chữ tính trên 320×240 rồi đem vẽ lên
1080×1920 — chữ bé như hạt gạo nằm lệch một góc, mà video vẫn chạy nên không ai
biết. Đúng họ hàng với lỗi ``PlayRes`` đã mất nhiều công mới tìm ra.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline import render as render_mod
from src.pipeline.cues import Cue
from src.pipeline.render import render_with_subtitles
from src.pipeline.shortform.reframe import DEFAULT_OUT_HEIGHT, DEFAULT_OUT_WIDTH
from src.pipeline.shortform.safe_area import SafeArea

TIKTOK = SafeArea(top=0.06, bottom=0.18, left=0.05, right=0.20)
CUES = [Cue(0, 1.0, 2.0, "Xin chào")]


@pytest.fixture
def spy(monkeypatch, tmp_path):
    """Chặn ffmpeg, ghi lại nguồn đã burn và file ASS đã dùng."""
    ghi_nhan: dict[str, list] = {"burn_src": [], "ass": [], "reframe": []}

    def _fake_burn(src, subtitle_file, dst, **kwargs):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        ghi_nhan["burn_src"].append(Path(src))
        ghi_nhan["ass"].append(Path(subtitle_file))
        return dst

    def _fake_reframe(src, dst, **kwargs):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        ghi_nhan["reframe"].append(dst)
        return dst

    monkeypatch.setattr(render_mod, "burn_subtitles", _fake_burn)
    monkeypatch.setattr(render_mod, "reframe_blur", _fake_reframe)
    monkeypatch.setattr(render_mod, "reframe_crop", _fake_reframe)
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    return ghi_nhan


def _src(tmp_path: Path, ten: str = "nguon.mp4") -> Path:
    src = tmp_path / ten
    src.write_bytes(b"x")
    return src


def test_nguon_ngang_co_loi_thoai_duoc_doi_sang_khung_doc(spy, tmp_path) -> None:
    """Đúng ca hỏng: video 4:3 có lời thoại vẫn ra 4:3."""
    render_with_subtitles(
        "vid-ngang",
        _src(tmp_path),
        CUES,
        safe=TIKTOK,
        video_width=320,
        video_height=240,
    )

    assert spy["reframe"], "không đổi khung — bản master vẫn giữ khung nguồn"


def test_burn_len_ban_da_doi_khung_chu_khong_phai_nguon_goc(spy, tmp_path) -> None:
    """Đổi khung xong mà vẫn burn lên file gốc thì công đổi khung vứt đi."""
    render_with_subtitles(
        "vid-burn-dung-nguon",
        _src(tmp_path),
        CUES,
        safe=TIKTOK,
        video_width=1920,
        video_height=1080,
    )

    assert spy["burn_src"][0] == spy["reframe"][0]


def test_ass_dung_khung_SAU_khi_doi_chu_khong_phai_khung_nguon(spy, tmp_path) -> None:
    """Cái bẫy chính. Lề và cỡ chữ tính trên khung nguồn rồi vẽ lên khung đích
    cho ra chữ bé xíu nằm lệch — video vẫn chạy nên rất khó phát hiện."""
    render_with_subtitles(
        "vid-ass-khung-dich",
        _src(tmp_path),
        CUES,
        safe=TIKTOK,
        video_width=320,
        video_height=240,
    )

    noi_dung = spy["ass"][0].read_text(encoding="utf-8")
    assert f"PlayResX: {DEFAULT_OUT_WIDTH}" in noi_dung
    assert f"PlayResY: {DEFAULT_OUT_HEIGHT}" in noi_dung
    assert "PlayResY: 240" not in noi_dung


def test_nguon_da_doc_thi_khong_dong_vao(spy, tmp_path) -> None:
    """Scale đi scale lại chỉ làm giảm chất lượng."""
    nguon = _src(tmp_path)
    render_with_subtitles(
        "vid-da-doc",
        nguon,
        CUES,
        safe=TIKTOK,
        video_width=1080,
        video_height=1920,
    )

    assert not spy["reframe"]
    assert spy["burn_src"][0] == nguon


def test_che_do_doi_khung_lay_theo_tham_so(spy, tmp_path) -> None:
    """``reframe_mode`` phải đi tới nơi, không bị bỏ quên ở giữa đường."""
    render_with_subtitles(
        "vid-crop",
        _src(tmp_path),
        CUES,
        safe=TIKTOK,
        video_width=1920,
        video_height=1080,
        reframe_mode="crop",
    )

    assert "crop" in spy["reframe"][0].name


def test_che_do_doi_khung_sai_thi_bao_loi(spy, tmp_path) -> None:
    """Không âm thầm rơi về mặc định (luật số 7 CLAUDE.md)."""
    from src.errors import InvalidReframeModeError

    with pytest.raises(InvalidReframeModeError):
        render_with_subtitles(
            "vid-mode-sai",
            _src(tmp_path),
            CUES,
            safe=TIKTOK,
            video_width=1920,
            video_height=1080,
            reframe_mode="khong-ton-tai",
        )
