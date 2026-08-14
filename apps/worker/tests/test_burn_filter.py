"""Chuỗi filter của bước burn — không gọi ffmpeg thật, chỉ soi tham số dựng ra.

Khoá lại quyết định sau khi đo bằng ffmpeg thật (xem ``pipeline/subtitle_ass.py``):
kiểu chữ nằm TRONG file ASS, không truyền qua ``force_style`` nữa. ``force_style``
đi kèm SRT là nguồn gốc lỗi phụ đề bay ra ngoài khung 1080×1920, vì số trong đó
được hiểu theo khung 384×288 do ffmpeg tự đặt chứ không phải pixel thật.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ffmpeg import burn as burn_mod


@pytest.fixture
def ffmpeg_gia(monkeypatch):
    """Chặn ffmpeg, giữ lại danh sách tham số và tạo sẵn file tạm đầu ra."""
    ghi_nhan: dict[str, list[str]] = {}

    def _fake_run(args, **kwargs):
        ghi_nhan["args"] = list(args)
        Path(args[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(args[-1]).write_bytes(b"x")
        return ""

    monkeypatch.setattr(burn_mod, "run_ffmpeg", _fake_run)
    monkeypatch.setattr(burn_mod, "run_ffmpeg_progress", lambda args, **kw: _fake_run(args))
    return ghi_nhan


def _vf(args: list[str]) -> str:
    return args[args.index("-vf") + 1]


def _chuan_bi(tmp_path: Path) -> tuple[Path, Path, Path]:
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    ass = tmp_path / "sub.vi.ass"
    ass.write_text("[Script Info]\n", encoding="utf-8")
    return src, ass, tmp_path / "out.mp4"


def test_burn_tro_thang_toi_file_ass(ffmpeg_gia, tmp_path) -> None:
    src, ass, dst = _chuan_bi(tmp_path)
    burn_mod.burn_subtitles(src, ass, dst)
    assert _vf(ffmpeg_gia["args"]).startswith(f"subtitles='{ass}'")


def test_khong_con_tuy_chon_force_style(ffmpeg_gia, tmp_path) -> None:
    """Kiểu chữ phải nằm trong file ASS. Còn ``force_style`` nghĩa là lỗi cũ quay lại.

    So theo CÚ PHÁP ``:force_style=`` chứ không tìm chuỗi con "force_style" —
    ``tmp_path`` mang tên hàm test nên bản thân đường dẫn cũng chứa chuỗi đó.
    """
    src, ass, dst = _chuan_bi(tmp_path)
    burn_mod.burn_subtitles(src, ass, dst)
    assert ":force_style=" not in _vf(ffmpeg_gia["args"])


def test_hook_noi_sau_filter_phu_de(ffmpeg_gia, tmp_path) -> None:
    src, ass, dst = _chuan_bi(tmp_path)
    burn_mod.burn_subtitles(src, ass, dst, hook_filter="drawtext=text='xin chao'")
    vf = _vf(ffmpeg_gia["args"])
    assert vf.index("subtitles=") < vf.index("drawtext=")


def test_duong_dan_co_dau_hai_cham_duoc_escape(ffmpeg_gia, tmp_path) -> None:
    """``:`` trong đường dẫn tách cú pháp filter của ffmpeg nếu không escape."""
    thu_muc = tmp_path / "phim: tap 1"
    thu_muc.mkdir()
    src = thu_muc / "in.mp4"
    src.write_bytes(b"x")
    ass = thu_muc / "sub.vi.ass"
    ass.write_text("[Script Info]\n", encoding="utf-8")

    burn_mod.burn_subtitles(src, ass, thu_muc / "out.mp4")
    assert "phim\\: tap 1" in _vf(ffmpeg_gia["args"])
