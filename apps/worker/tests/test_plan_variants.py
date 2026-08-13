"""M4-WK-05 — lập kế hoạch render_variants theo từng nền tảng đích.

Hàm thuần trong ``src/pipeline/render.py::plan_variants``, không chạm DB, không
chạm ffmpeg — chỉ điều phối ``split_by_duration`` (M4-WK-04) theo giới hạn
thời lượng riêng của từng nền tảng.
"""

from __future__ import annotations

import pytest

from src.errors import PlatformLimitNotFoundError
from src.pipeline.cues import Cue
from src.pipeline.render import VariantPlan, plan_variants


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
