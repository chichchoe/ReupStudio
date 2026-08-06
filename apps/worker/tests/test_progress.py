"""Test tiến trình pipeline: mốc %, quy đổi %, đọc dòng ``-progress`` của ffmpeg,
và ``format_cues`` bắn mốc khi duyệt cue.

Không cần Redis/ffmpeg — mọi hàm test ở đây đều thuần (xem test_dedup.py để
biết phong cách test chung của repo).
"""

from __future__ import annotations

import pytest

from src.ffmpeg.runner import out_time_to_percent, parse_progress_line
from src.milestones import MIN_MILESTONES, milestones, percent_of
from src.pipeline.cues import Cue
from src.pipeline.subtitle_format import format_cues

# --------------------------------------------------------------------------- #
# milestones()
# --------------------------------------------------------------------------- #


def test_it_nhat_5_moc_khi_total_lon_hon_hoac_bang_5() -> None:
    for total in (5, 6, 7, 30, 100, 1000):
        assert len(milestones(total)) >= MIN_MILESTONES


def test_moc_cuoi_luon_la_total_khi_du_phan_tu() -> None:
    for total in (5, 6, 30, 100):
        assert max(milestones(total)) == total


def test_ban_o_moi_phan_tu_khi_total_nho_hon_5() -> None:
    for total in range(1, MIN_MILESTONES):
        assert milestones(total) == set(range(1, total + 1))


def test_total_bang_0_hoac_am_thi_khong_co_moc() -> None:
    assert milestones(0) == set()
    assert milestones(-3) == set()


def test_moc_nam_trong_khoang_1_toi_total() -> None:
    for total in (5, 7, 30, 1000):
        assert all(1 <= m <= total for m in milestones(total))


# --------------------------------------------------------------------------- #
# percent_of()
# --------------------------------------------------------------------------- #


def test_percent_of_khong_bao_gio_vuot_khoang_mac_dinh() -> None:
    for done in range(-5, 20):
        assert 0 <= percent_of(done, 10) <= 100


def test_percent_of_khong_bao_gio_vuot_khoang_tuy_chinh() -> None:
    for done in range(-5, 20):
        assert 10 <= percent_of(done, 10, lo=10, hi=95) <= 95


def test_percent_of_don_dieu_khong_giam() -> None:
    total = 37
    percents = [percent_of(done, total) for done in range(total + 1)]
    assert percents == sorted(percents)


def test_percent_of_bien_dau_cuoi_dung_lo_hi() -> None:
    assert percent_of(0, 10) == 0
    assert percent_of(10, 10) == 100
    assert percent_of(0, 10, lo=10, hi=95) == 10
    assert percent_of(10, 10, lo=10, hi=95) == 95


def test_percent_of_total_bang_0_tra_ve_hi() -> None:
    assert percent_of(5, 0) == 100
    assert percent_of(5, 0, hi=42) == 42


# --------------------------------------------------------------------------- #
# parse_progress_line()
# --------------------------------------------------------------------------- #


def test_doc_dung_out_time_ms() -> None:
    assert parse_progress_line("out_time_ms=1234567") == 1234567
    assert parse_progress_line("out_time_ms=1234567\n") == 1234567


@pytest.mark.parametrize(
    "line",
    [
        "frame=12",
        "progress=continue",
        "progress=end",
        "",
        "   ",
        "dòng rác không có dấu bằng",
    ],
)
def test_tra_none_cho_dong_khong_phai_out_time_ms(line: str) -> None:
    assert parse_progress_line(line) is None


def test_out_time_ms_khong_parse_duoc_thi_tra_none() -> None:
    assert parse_progress_line("out_time_ms=N/A") is None


# --------------------------------------------------------------------------- #
# out_time_to_percent()
# --------------------------------------------------------------------------- #


def test_out_time_to_percent_dung_so_do_that_tu_ffmpeg() -> None:
    """Số đo thật lấy từ ffmpeg: video 15s, dòng -progress cuối cho
    out_time_ms=14_933_333 — hiểu đúng là micro giây (14.93s / 15s ≈ 99%)."""
    assert out_time_to_percent(14_933_333, 15.0) == 99


def test_out_time_to_percent_neu_hieu_nham_mili_giay_thi_vo_ly() -> None:
    """Nếu hiểu out_time_ms là mili giây thật (chia 1000) thay vì micro giây
    (chia 1_000_000) như brief gốc viết verbatim, % vọt qua 100 ngay dòng
    progress ĐẦU TIÊN và kẹp cứng — vô hiệu hoá hoàn toàn việc bắn tiến trình
    mượt. Đây chính là bug đã tìm ra khi kiểm bằng ffmpeg thật."""
    out_time_us = 14_933_333
    duration_sec = 15.0
    hieu_nham_la_ms = max(0, min(100, int(out_time_us / 1000 / duration_sec * 100)))
    assert hieu_nham_la_ms == 100  # vô lý — mới 14.9/15s mà đã báo xong

    dung = out_time_to_percent(out_time_us, duration_sec)
    assert dung == 99  # hiểu đúng micro giây thì gần xong nhưng chưa 100


def test_out_time_to_percent_ket_thuc_dung_100() -> None:
    assert out_time_to_percent(15_000_000, 15.0) == 100


def test_out_time_to_percent_khong_vuot_qua_100_khi_vuot_duration() -> None:
    assert out_time_to_percent(20_000_000, 15.0) == 100


def test_out_time_to_percent_khong_am_khi_out_time_am() -> None:
    assert out_time_to_percent(-5000, 15.0) == 0


def test_out_time_to_percent_duration_khong_duong_tra_ve_0() -> None:
    assert out_time_to_percent(1000, 0) == 0
    assert out_time_to_percent(1000, -5) == 0


# --------------------------------------------------------------------------- #
# format_cues(progress_cb=...)
# --------------------------------------------------------------------------- #


def _cues(n: int) -> list[Cue]:
    """Cue đủ dài (1.5s) và cách nhau để không bị merge_short_cues gộp mất."""
    return [Cue(i, i * 2.0, i * 2.0 + 1.5, f"Câu thoại số {i} đủ dài") for i in range(n)]


def test_format_cues_ban_it_nhat_5_moc_tang_dan_ket_thuc_100() -> None:
    seen: list[int] = []
    format_cues(_cues(30), progress_cb=seen.append)

    assert len(seen) >= MIN_MILESTONES
    assert len(set(seen)) >= MIN_MILESTONES
    assert seen == sorted(seen)
    assert seen[-1] == 100


def test_format_cues_khong_progress_cb_van_chay_binh_thuong() -> None:
    out = format_cues(_cues(30))
    assert len(out) == 30


def test_format_cues_it_cue_van_goi_progress_cb() -> None:
    seen: list[int] = []
    format_cues(_cues(2), progress_cb=seen.append)
    assert seen  # có gọi, kể cả khi ít hơn MIN_MILESTONES cue
    assert seen[-1] == 100
