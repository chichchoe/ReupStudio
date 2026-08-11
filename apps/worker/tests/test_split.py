"""M4-WK-04 — chia video thành các tập theo giới hạn thời lượng.

Hàm thuần trong ``src/pipeline/shortform/split.py``, test gọi trực tiếp,
không cần Redis/Celery.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from src.errors import ReupError
from src.pipeline.cues import Cue
from src.pipeline.shortform.split import (
    InvalidSplitLimitError,
    Part,
    _chon_bien,
    _gop_tap_cuoi_qua_ngan,
    silence_cut_points,
    split_by_duration,
)


def _cue(i: int, start: float, end: float, text: str = "x") -> Cue:
    return Cue(i=i, start=start, end=end, text=text)


# --------------------------------------------------------------------------- #
# max_duration_sec == 0 — đường chạy mặc định/phổ biến nhất của hệ thống
# --------------------------------------------------------------------------- #


def test_max_bang_0_tra_dung_mot_tap_phu_toan_bo_video() -> None:
    """max_duration_sec=0 là giá trị seed mặc định cho cả 5 nền tảng trong
    platform_limits — người dùng tự xem lại video trước khi đăng, công cụ
    không được tự ý cắt. Đây là ca hạng nhất, phải luôn đúng."""
    parts = split_by_duration(600.0, 0)

    assert parts == [Part(index=1, start=0.0, end=600.0)]


def test_max_bang_0_khong_chia_du_video_rat_dai() -> None:
    parts = split_by_duration(3600.0, 0, cut_points=[100.0, 2000.0])

    assert parts == [Part(index=1, start=0.0, end=3600.0)]


# --------------------------------------------------------------------------- #
# total_sec <= max_duration_sec — không cần chia
# --------------------------------------------------------------------------- #


def test_total_nho_hon_max_tra_dung_mot_tap() -> None:
    parts = split_by_duration(50.0, 60)

    assert parts == [Part(index=1, start=0.0, end=50.0)]


def test_total_bang_max_tra_dung_mot_tap() -> None:
    parts = split_by_duration(90.0, 90)

    assert parts == [Part(index=1, start=0.0, end=90.0)]


# --------------------------------------------------------------------------- #
# Chia đều khi không có cut_points dùng được
# --------------------------------------------------------------------------- #


def test_240s_max_180_chia_dung_hai_tap_khong_tap_nao_qua_180() -> None:
    parts = split_by_duration(240.0, 180)

    assert len(parts) == 2
    assert all(p.duration <= 180 for p in parts)
    assert parts == [
        Part(index=1, start=0.0, end=180.0),
        Part(index=2, start=180.0, end=240.0),
    ]


def test_240s_max_90_chia_ba_tap_phu_kin_khong_chong_lan() -> None:
    total = 240.0
    parts = split_by_duration(total, 90)

    assert len(parts) == 3
    assert all(p.duration <= 90 for p in parts)

    # Phủ kín [0, total], không chồng lấn, không hở: cộng dồn phải khớp biên.
    assert parts[0].start == 0.0
    assert parts[-1].end == total
    for prev, nxt in pairwise(parts):
        assert prev.end == nxt.start


# --------------------------------------------------------------------------- #
# cut_points — mốc ưu tiên, không cắt giữa câu
# --------------------------------------------------------------------------- #


def test_cut_points_gan_moc_ly_tuong_duoc_dung_lam_bien() -> None:
    """85 gần lý tưởng 90, 175 gần lý tưởng 180 — biên tập phải trùng đúng các
    mốc đó thay vì cắt đều tại 90/180."""
    parts = split_by_duration(240.0, 90, cut_points=[85.0, 175.0])

    assert [p.end for p in parts[:-1]] == [85.0, 175.0]
    assert parts[-1].end == 240.0


def test_cut_point_qua_xa_ly_tuong_van_duoc_dung_neu_la_lua_chon_duy_nhat() -> None:
    """Không có ngưỡng "quá xa" bị loại — chỉ cần mốc nằm trong (current, giới
    hạn], thuật toán vẫn ưu tiên mốc đó hơn là cắt đều, vì mốc đó tránh cắt
    giữa câu."""
    parts = split_by_duration(200.0, 90, cut_points=[10.0])

    assert parts[0].end == 10.0


def test_khong_co_cut_points_dung_duoc_thi_cat_deu() -> None:
    """Không có cut_points nào rơi vào cửa sổ (mốc_hiện_tại, giới_hạn] của bất
    kỳ lần cắt nào (âm, bằng 0, hoặc nằm quá xa sau vị trí lý tưởng) — quay về
    cắt đều tại vị trí lý tưởng."""
    parts = split_by_duration(240.0, 90, cut_points=[-5.0, 0.0, 239.9, 500.0])

    assert [p.end for p in parts[:-1]] == [90.0, 180.0]


# --------------------------------------------------------------------------- #
# Tập cuối ngắn hơn min_part_sec
# --------------------------------------------------------------------------- #


def test_tap_cuoi_ngan_duoc_gop_vao_tap_truoc_qua_helper_gop() -> None:
    """Test trực tiếp _gop_tap_cuoi_qua_ngan — helper THUẦN, nhận list biên và
    trả list biên đã gộp. boundaries=[0, 45, 49]: tập cuối dài 4s (<10, min
    mặc định), gộp với tập trước (45-0=45) cho tổng 49 <= max(50) => gộp
    thành công, biên giữa (45.0) bị loại bỏ."""
    boundaries = _gop_tap_cuoi_qua_ngan([0.0, 45.0, 49.0], 50, 10.0)

    assert boundaries == [0.0, 49.0]


def test_gop_se_vuot_max_thi_khong_gop_giu_nguyen_tap_ngan() -> None:
    """boundaries=[0, 90, 94]: tập cuối dài 4s (<10), nhưng gộp lại
    (94-0=94) sẽ vượt max=90 => KHÔNG gộp, giữ nguyên 2 tập."""
    boundaries = _gop_tap_cuoi_qua_ngan([0.0, 90.0, 94.0], 90, 10.0)

    assert boundaries == [0.0, 90.0, 94.0]


def test_helper_gop_khong_dong_neu_tap_cuoi_du_dai() -> None:
    boundaries = _gop_tap_cuoi_qua_ngan([0.0, 90.0, 120.0], 90, 10.0)

    assert boundaries == [0.0, 90.0, 120.0]


def test_split_by_duration_khong_bao_gio_tra_tap_cuoi_qua_ngan_khi_kha_thi() -> None:
    """Trước đây _chon_bien luôn cắt tham lam đúng tại vị trí lý tưởng
    (current + max), nên với total=184, max=90 sẽ để lại tập cuối 184-180=4s
    (< min_part_sec=10) — và việc gộp ngược 2 tập cuối (90 + 4 = 94 > 90)
    LUÔN vượt max nên không bao giờ gộp được: đây là hệ quả toán học của vòng
    lặp "cắt khi phần còn lại > max" — hễ còn phải cắt tiếp thì phần còn lại
    tại thời điểm đó đã vượt max, nên 2 tập cuối cộng lại luôn vượt max, gộp
    ngược không bao giờ khả thi. split_by_duration phải né trước bằng cách
    lùi mốc chọn (xem _chon_bien), không được để lọt tập cuối 4s ra ngoài.
    """
    parts = split_by_duration(184.0, 90, min_part_sec=10.0)

    assert parts[-1].duration >= 10.0
    assert all(p.duration <= 90 for p in parts)
    # Phủ kín, không hở, không chồng lấn.
    assert parts[0].start == 0.0
    assert parts[-1].end == 184.0
    for prev, nxt in pairwise(parts):
        assert prev.end == nxt.start


def test_split_by_duration_gop_gan_dung_khi_min_part_sec_khong_kha_thi() -> None:
    """Khi min_part_sec >= max_duration_sec, không có cách nào đảm bảo tập nào
    cũng đủ min_part_sec — _chon_bien bỏ qua nhìn trước, tập cuối ngắn được
    giữ nguyên (gộp sẽ luôn vượt max, đúng theo quy tắc)."""
    parts = split_by_duration(95.0, 90, min_part_sec=95.0)

    assert len(parts) == 2
    assert parts[-1].duration == pytest.approx(5.0)
    assert all(p.duration <= 90 for p in parts)


# --------------------------------------------------------------------------- #
# _chon_bien — kiểm hành vi nhìn trước min_part_sec trực tiếp
# --------------------------------------------------------------------------- #


def test_chon_bien_lui_moc_de_tranh_duoi_qua_ngan() -> None:
    boundaries = _chon_bien(184.0, 90, [], 10.0)

    # Đúng lẽ ra cắt đều sẽ ra [0, 90, 180, 184] (đuôi 4s) — thuật toán phải
    # lùi mốc thứ hai lại 174 để đuôi đủ 10s.
    assert boundaries == [0.0, 90.0, 174.0, 184.0]


# --------------------------------------------------------------------------- #
# Validate đầu vào
# --------------------------------------------------------------------------- #


def test_max_duration_am_nem_loi_co_nghia() -> None:
    with pytest.raises(InvalidSplitLimitError):
        split_by_duration(100.0, -5)


def test_min_part_sec_am_nem_loi_co_nghia() -> None:
    with pytest.raises(InvalidSplitLimitError):
        split_by_duration(100.0, 50, min_part_sec=-1.0)


def test_total_sec_am_nem_loi_co_nghia() -> None:
    with pytest.raises(InvalidSplitLimitError):
        split_by_duration(-1.0, 50)


def test_invalid_split_limit_error_la_reup_error() -> None:
    assert issubclass(InvalidSplitLimitError, ReupError)


# --------------------------------------------------------------------------- #
# silence_cut_points
# --------------------------------------------------------------------------- #


def test_hai_cue_cach_nua_giay_co_moc_o_giua() -> None:
    cues = [_cue(1, 0.0, 2.0), _cue(2, 2.5, 4.0)]

    points = silence_cut_points(cues, min_gap=0.35)

    assert points == [pytest.approx(2.25)]


def test_hai_cue_cach_0_1_giay_khong_co_moc() -> None:
    cues = [_cue(1, 0.0, 2.0), _cue(2, 2.1, 4.0)]

    points = silence_cut_points(cues, min_gap=0.35)

    assert points == []


def test_silence_cut_points_khong_yeu_cau_cue_da_sap_xep() -> None:
    cues = [_cue(2, 2.5, 4.0), _cue(1, 0.0, 2.0)]

    points = silence_cut_points(cues, min_gap=0.35)

    assert points == [pytest.approx(2.25)]


def test_silence_cut_points_it_hon_hai_cue_tra_rong() -> None:
    assert silence_cut_points([], min_gap=0.35) == []
    assert silence_cut_points([_cue(1, 0.0, 2.0)], min_gap=0.35) == []


def test_silence_cut_points_nhieu_khoang_lang() -> None:
    cues = [
        _cue(1, 0.0, 2.0),
        _cue(2, 2.5, 4.0),  # gap 0.5 -> mốc 2.25
        _cue(3, 4.05, 6.0),  # gap 0.05 -> không có mốc
        _cue(4, 7.0, 8.0),  # gap 1.0 -> mốc 6.5
    ]

    points = silence_cut_points(cues, min_gap=0.35)

    assert points == [pytest.approx(2.25), pytest.approx(6.5)]
