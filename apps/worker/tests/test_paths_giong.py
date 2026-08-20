"""Đường dẫn file của thư viện giọng.

``paths.py`` là nơi DUY NHẤT được ghép đường dẫn (luật số 3 CLAUDE.md). Test
này khoá bốn tên file spec C2 đã chốt, và khoá một cái bẫy có thật: đã có sẵn
``voice_parts_dir(video_id)`` trả về ``media/work/<video_id>/giong`` — thư mục
chứa từng MẨU giọng của một video. Hai thứ khác hẳn nhau mà tên gần giống, lẫn
là xoá nhầm cả bộ mẫu giọng khi dọn thư mục work.
"""

from __future__ import annotations

from pathlib import Path

from reup_core import paths

GIONG_ID = "8c1f7b6e-0000-4000-8000-000000000001"


def test_moi_file_nam_trong_thu_muc_cua_dung_giong_do(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    thu_muc = paths.giong_dir(GIONG_ID)

    assert thu_muc == tmp_path.resolve() / "giong" / GIONG_ID
    for f in (
        paths.giong_mau_wav(GIONG_ID),
        paths.giong_mau_txt(GIONG_ID),
        paths.giong_codes(GIONG_ID),
        paths.giong_nghe_thu(GIONG_ID),
    ):
        assert f.parent == thu_muc


def test_dung_dung_bon_ten_file_spec_da_chot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    assert paths.giong_mau_wav(GIONG_ID).name == "mau.wav"
    assert paths.giong_mau_txt(GIONG_ID).name == "mau.txt"
    assert paths.giong_codes(GIONG_ID).name == "codes.npz"
    assert paths.giong_nghe_thu(GIONG_ID).name == "nghe-thu.wav"


def test_thu_muc_duoc_tao_tu_dong(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    d = paths.giong_dir(GIONG_ID)
    assert d.exists() and d.is_dir()


def test_file_tai_len_giu_nguyen_duoi(tmp_path: Path, monkeypatch) -> None:
    #: ffmpeg đoán định dạng đầu vào theo nội dung, nhưng giữ đuôi giúp người
    #: soi thư mục biết ngay file gốc là gì khi đi tìm nguyên nhân.
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    assert paths.giong_tai_len(GIONG_ID, ".m4a").name == "goc.m4a"
    assert paths.giong_tai_len(GIONG_ID, "mp3").name == "goc.mp3"
    assert paths.giong_tai_len(GIONG_ID, "").name == "goc"


def test_KHAC_han_thu_muc_mau_giong_cua_mot_video(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    assert paths.giong_dir(GIONG_ID) != paths.voice_parts_dir(GIONG_ID)
    assert not paths.giong_dir(GIONG_ID).is_relative_to(paths.work_dir(GIONG_ID))
