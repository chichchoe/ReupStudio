from __future__ import annotations

from pathlib import Path

from src.pipeline.cues import Cue, cues_from_dicts, cues_to_dicts, write_srt


def test_srt_timestamp_dung_dinh_dang(tmp_path: Path) -> None:
    cues = [Cue(0, 0.0, 1.5, "Xin chào"), Cue(1, 61.25, 65.0, "Dòng hai")]
    path = write_srt(cues, tmp_path / "a.srt")
    content = path.read_text(encoding="utf-8")

    assert "00:00:00,000 --> 00:00:01,500" in content
    assert "00:01:01,250 --> 00:01:05,000" in content
    assert content.startswith("1\n")


def test_round_trip_dict(tmp_path: Path) -> None:
    cues = [Cue(0, 0.0, 1.0, "A"), Cue(1, 1.0, 2.0, "B")]
    assert cues_from_dicts(cues_to_dicts(cues)) == cues


def test_thoi_gian_am_duoc_kep_ve_0(tmp_path: Path) -> None:
    path = write_srt([Cue(0, -1.0, 1.0, "A")], tmp_path / "b.srt")
    assert "00:00:00,000" in path.read_text(encoding="utf-8")
