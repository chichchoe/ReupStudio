"""M4-WK-05 — lập kế hoạch render_variants theo từng nền tảng đích.

Hàm thuần trong ``src/pipeline/render.py::plan_variants``, không chạm DB, không
chạm ffmpeg — chỉ điều phối ``split_by_duration`` (M4-WK-04) theo giới hạn
thời lượng riêng của từng nền tảng. Cũng test ``_cues_for_segment`` (theo
review Task 6, nâng lên bắt buộc vì thuộc nhóm "chuẩn hoá phụ đề" mà CLAUDE.md
liệt kê phải test tự động) — hàm cắt/dịch mốc thời gian cue theo ranh giới
tập, sai thì phụ đề lệch ở MỌI tập được chia.
"""

from __future__ import annotations

import pytest

from src.errors import PlatformLimitNotFoundError
from src.pipeline.cues import Cue
from src.pipeline.render import VariantPlan, _cues_for_segment, plan_variants


def _cue(i: int, start: float, end: float, text: str = "x") -> Cue:
    return Cue(i=i, start=start, end=end, text=text)


def test_video_200s_ba_nen_tang_chia_dung_so_tap_moi_nen_tang() -> None:
    """200s, tiktok/youtube giới hạn 180s -> 2 tập; facebook giới hạn 90s ->
    3 tập (90*2=180 < 200 nên không đủ 2 tập)."""
    limits = {"tiktok": 180, "youtube": 180, "facebook": 90}
    plans = plan_variants(200.0, ["tiktok", "youtube", "facebook"], limits)

    by_platform: dict[str, list[VariantPlan]] = {}
    for p in plans:
        by_platform.setdefault(p.target_platform, []).append(p)

    assert len(by_platform["tiktok"]) == 2
    assert len(by_platform["youtube"]) == 2
    assert len(by_platform["facebook"]) == 3

    for parts in by_platform.values():
        total = len(parts)
        assert all(p.part_total == total for p in parts)
        assert [p.part_index for p in parts] == list(range(1, total + 1))
        # Phủ kín [0, 200], không hở, không chồng lấn.
        assert parts[0].start == 0.0
        assert parts[-1].end == 200.0


def test_video_60s_ca_ba_dich_deu_dung_mot_tap() -> None:
    """60s ngắn hơn mọi giới hạn -> mỗi nền tảng đúng 1 tập, part_index=1,
    part_total=1."""
    limits = {"tiktok": 180, "youtube": 180, "facebook": 90}
    plans = plan_variants(60.0, ["tiktok", "youtube", "facebook"], limits)

    assert len(plans) == 3
    for p in plans:
        assert p.part_index == 1
        assert p.part_total == 1
        assert p.start == 0.0
        assert p.end == 60.0


def test_danh_sach_dich_rong_tra_rong_khong_nem_loi() -> None:
    assert plan_variants(100.0, [], {"tiktok": 180}) == []


def test_nen_tang_khong_co_trong_limits_bao_loi_ro_rang() -> None:
    """KHÔNG được âm thầm bỏ qua nền tảng thiếu cấu hình — phải báo lỗi rõ."""
    with pytest.raises(PlatformLimitNotFoundError, match="threads"):
        plan_variants(100.0, ["tiktok", "threads"], {"tiktok": 180})


def test_max_duration_0_nghia_la_khong_gioi_han_tra_dung_mot_tap() -> None:
    """Giá trị seed mặc định của platform_limits (xem migration 0006) —
    plan_variants phải tôn trọng đúng quy ước này qua split_by_duration."""
    plans = plan_variants(600.0, ["tiktok"], {"tiktok": 0})

    assert plans == [
        VariantPlan(target_platform="tiktok", part_index=1, part_total=1, start=0.0, end=600.0)
    ]


def test_cues_duoc_dung_de_chon_moc_cat_khong_cat_giua_cau() -> None:
    """cut_points từ khoảng lặng giữa cue phải được ưu tiên hơn cắt đều —
    kiểm gián tiếp qua việc mốc cắt trùng đúng khoảng lặng đã chèn gần vị trí
    lý tưởng (giống test_split.py::test_cut_points_gan_moc_ly_tuong...)."""
    cues = [
        _cue(1, 0.0, 84.5),
        _cue(2, 85.0, 240.0),  # khoảng lặng 0.5s quanh giây 85, gần lý tưởng 90
    ]
    plans = plan_variants(240.0, ["facebook"], {"facebook": 90}, cues=cues)

    assert plans[0].end == pytest.approx(84.75)


def test_khong_co_cues_thi_cat_deu() -> None:
    plans = plan_variants(240.0, ["facebook"], {"facebook": 90})

    assert plans[0].end == 90.0
    assert plans[1].end == 180.0


# --------------------------------------------------------------------------- #
# _cues_for_segment — cắt & dịch mốc thời gian cue theo ranh giới tập
#
# Thuộc nhóm "chuẩn hoá phụ đề" (CLAUDE.md liệt kê bắt buộc test tự động):
# hàm này quyết định phụ đề của MỖI tập bị chia — sai thì lệch ở mọi tập,
# lệch nhẹ khó bắt bằng mắt.
# --------------------------------------------------------------------------- #


def test_cue_nam_tron_trong_tap_giu_nguyen_noi_dung_dich_moc_ve_goc_tap() -> None:
    cues = [_cue(1, 30.0, 35.0, "xin chào")]

    segment = _cues_for_segment(cues, start=20.0, end=60.0)

    assert len(segment) == 1
    assert segment[0].text == "xin chào"
    assert segment[0].start == pytest.approx(10.0)
    assert segment[0].end == pytest.approx(15.0)


def test_cue_nam_ngoai_tap_bi_loai() -> None:
    cues = [_cue(1, 0.0, 5.0), _cue(2, 200.0, 205.0)]

    segment = _cues_for_segment(cues, start=20.0, end=60.0)

    assert segment == []


def test_cue_giao_bien_dau_tap_bi_cat_ngan_khong_bi_loai() -> None:
    """Cue bắt đầu TRƯỚC start, kết thúc SAU start — phải giữ lại phần nằm
    trong tập, dịch mốc bắt đầu về 0 (không phải bị loại toàn bộ)."""
    cues = [_cue(1, 15.0, 25.0, "cắt biên đầu")]

    segment = _cues_for_segment(cues, start=20.0, end=60.0)

    assert len(segment) == 1
    assert segment[0].start == 0.0
    assert segment[0].end == pytest.approx(5.0)
    assert segment[0].text == "cắt biên đầu"


def test_cue_giao_bien_cuoi_tap_bi_cat_ngan_khong_bi_loai() -> None:
    """Cue bắt đầu TRƯỚC end, kết thúc SAU end — giữ lại phần nằm trong tập,
    cắt ngắn ở cuối, không kéo dài quá ranh giới tập."""
    cues = [_cue(1, 55.0, 70.0, "cắt biên cuối")]

    segment = _cues_for_segment(cues, start=20.0, end=60.0)

    assert len(segment) == 1
    assert segment[0].start == pytest.approx(35.0)
    assert segment[0].end == pytest.approx(40.0)  # end - start = 60 - 20
    assert segment[0].text == "cắt biên cuối"


def test_tap_khong_co_cue_nao_tra_rong_khong_nem_loi() -> None:
    assert _cues_for_segment([], start=0.0, end=100.0) == []
    assert _cues_for_segment([_cue(1, 500.0, 510.0)], start=0.0, end=100.0) == []


def test_cue_cham_dung_bien_khong_bi_dinh_vao_tap() -> None:
    """Cue kết thúc ĐÚNG lúc start hoặc bắt đầu ĐÚNG lúc end — nửa khoảng
    [start, end) nên không thuộc tập này (tránh cue trùng lặp giữa 2 tập kề
    nhau)."""
    cues = [_cue(1, 10.0, 20.0), _cue(2, 60.0, 70.0)]

    segment = _cues_for_segment(cues, start=20.0, end=60.0)

    assert segment == []
