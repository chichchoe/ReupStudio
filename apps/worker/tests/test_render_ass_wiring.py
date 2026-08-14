"""Hai đường render phải burn từ file ASS dựng theo khung ĐÍCH.

Khoá lại chỗ nối giữa ``pipeline/subtitle_ass.py`` và ``ffmpeg/burn.py``: nếu
một ngày nào đó ai đó nối lại bằng SRT, bộ test này đỏ ngay. Đây là mặt còn
thiếu của lỗi phụ đề bay ra ngoài khung — ``test_subtitle_ass.py`` chỉ chứng
minh file ASS đúng, chưa chứng minh render THẬT SỰ dùng nó.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.errors import InvalidFrameSizeError
from src.pipeline import render as render_mod
from src.pipeline.cues import Cue
from src.pipeline.render import VariantPlan, render_variant, render_with_subtitles
from src.pipeline.shortform.safe_area import SafeArea

TIKTOK = SafeArea(top=0.06, bottom=0.18, left=0.05, right=0.20)
CUES = [Cue(0, 1.0, 2.0, "Xin chào")]


@pytest.fixture
def spy(monkeypatch, tmp_path):
    """Chặn mọi lệnh gọi ffmpeg, giữ lại đường dẫn file phụ đề đã dùng."""
    ghi_nhan: dict[str, list] = {"burn": [], "reframe": []}

    def _fake_burn(src, subtitle_file, dst, **kwargs):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        ghi_nhan["burn"].append(Path(subtitle_file))
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


def _src(tmp_path: Path) -> Path:
    src = tmp_path / "nguon.mp4"
    src.write_bytes(b"x")
    return src


def test_master_burn_tu_file_ass(spy, tmp_path) -> None:
    render_with_subtitles(
        "vid-master",
        _src(tmp_path),
        CUES,
        safe=TIKTOK,
        video_width=1080,
        video_height=1920,
    )
    assert spy["burn"][0].suffix == ".ass"
    assert "PlayResY: 1920" in spy["burn"][0].read_text(encoding="utf-8")


def test_variant_burn_tu_file_ass_theo_khung_doc_sau_reframe(spy, tmp_path) -> None:
    """Nguồn ngang 1920×1080 -> reframe sang 1080×1920. ASS phải theo khung SAU
    reframe, không phải khung nguồn — burn diễn ra trên video đã đổi khung."""
    render_variant(
        "vid-variant",
        _src(tmp_path),
        CUES,
        VariantPlan(target_platform="tiktok", part_index=1, part_total=1, start=0.0, end=10.0),
        safe=TIKTOK,
        video_width=1920,
        video_height=1080,
    )
    noi_dung = spy["burn"][0].read_text(encoding="utf-8")
    assert spy["burn"][0].suffix == ".ass"
    assert "PlayResX: 1080" in noi_dung
    assert "PlayResY: 1920" in noi_dung


def test_thieu_kich_thuoc_khung_thi_bao_loi_thay_vi_render_khong_phu_de(spy, tmp_path) -> None:
    """Không biết khung thì không tính được lề/cỡ chữ.

    Thà dừng với lỗi rõ còn hơn cho ra một video trông bình thường nhưng mất
    sạch phụ đề — đúng kiểu hỏng đã mất nhiều tháng mới phát hiện.
    """
    with pytest.raises(InvalidFrameSizeError):
        render_with_subtitles(
            "vid-thieu-kich-thuoc",
            _src(tmp_path),
            CUES,
            safe=TIKTOK,
            video_width=None,
            video_height=None,
        )
