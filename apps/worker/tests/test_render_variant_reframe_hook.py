"""M4-WK-05b (Task 9) — nối ``reframe``/``hook`` vào ``render_variant``.

Task 6 dựng khung ``render_variants`` nhưng KHÔNG gọi ``reframe.py`` (Task 4)
hay ``hook.py`` (Task 5) — hai module trọn vẹn từng là code chết. Test ở đây
kiểm ``render_variant`` GỌI ĐÚNG hai module đó, đúng THỨ TỰ (reframe trước,
hook/phụ đề sau) và đúng điều kiện (chỉ tập 1 có hook, nguồn dọc không reframe).

Toàn bộ MOCK các hàm chạm ffmpeg thật (``reframe_blur``/``reframe_crop``,
``burn_subtitles``, ``trim_video``) — nội dung filter/thuật toán tự thân của
từng hàm đã có test riêng (``test_hook.py``, ``test_reframe.py``) và được kiểm
CHẠY THẬT bằng ``scripts/try_render_variants.py`` + ``ffprobe`` (xem
task-9-report.md — nhánh reframe chạy thật được trên máy dev, nhánh
hook/phụ đề chỉ kiểm cấu trúc lệnh vì ffmpeg máy dev thiếu libass/libfreetype).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.errors import InvalidReframeModeError
from src.pipeline.cues import Cue
from src.pipeline.render import VariantPlan, render_variant
from src.pipeline.shortform.hook import build_hook_filter, hook_box
from src.pipeline.shortform.safe_area import SafeArea, fits_in_safe_area

TIKTOK = SafeArea(top=0.06, bottom=0.18, left=0.05, right=0.20)
SRC = Path("/fake/nguon.mp4")


def _cue(i: int, start: float, end: float, text: str = "loi thoai") -> Cue:
    return Cue(i=i, start=start, end=end, text=text)


def _plan(
    part_index: int = 1, part_total: int = 1, start: float = 0.0, end: float = 30.0
) -> VariantPlan:
    return VariantPlan(
        target_platform="tiktok",
        part_index=part_index,
        part_total=part_total,
        start=start,
        end=end,
    )


@pytest.fixture(autouse=True)
def _media_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))


@pytest.fixture
def spy(monkeypatch):
    """Chặn mọi hàm chạm ffmpeg thật, ghi lại lời gọi để kiểm cấu trúc lệnh."""
    calls: dict[str, list] = {
        "reframe_blur": [],
        "reframe_crop": [],
        "burn_subtitles": [],
        "trim_video": [],
    }

    def _fake_reframe_blur(src, dst, **kwargs):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        calls["reframe_blur"].append((src, dst, kwargs))
        return dst

    def _fake_reframe_crop(src, dst, **kwargs):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        calls["reframe_crop"].append((src, dst, kwargs))
        return dst

    def _fake_burn_subtitles(src, srt, dst, **kwargs):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        calls["burn_subtitles"].append((src, srt, dst, kwargs))
        return dst

    def _fake_trim_video(src, dst, **kwargs):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        calls["trim_video"].append((src, dst, kwargs))
        return dst

    monkeypatch.setattr("src.pipeline.render.reframe_blur", _fake_reframe_blur)
    monkeypatch.setattr("src.pipeline.render.reframe_crop", _fake_reframe_crop)
    monkeypatch.setattr("src.pipeline.render.burn_subtitles", _fake_burn_subtitles)
    monkeypatch.setattr("src.pipeline.render.trim_video", _fake_trim_video)
    return calls


# --------------------------------------------------------------------------- #
# reframe — chỉ áp khi nguồn NGANG
# --------------------------------------------------------------------------- #


def test_nguon_ngang_co_buoc_reframe(spy) -> None:
    render_variant(
        "vid-ngang", SRC, [], _plan(), safe=TIKTOK, video_width=1920, video_height=1080
    )
    assert len(spy["reframe_blur"]) == 1
    assert spy["reframe_crop"] == []


def test_nguon_doc_khong_co_buoc_reframe(spy) -> None:
    render_variant(
        "vid-doc", SRC, [], _plan(), safe=TIKTOK, video_width=1080, video_height=1920
    )
    assert spy["reframe_blur"] == []
    assert spy["reframe_crop"] == []
    # Không reframe -> trim_video chạy thẳng trên nguồn gốc, không phải file trung gian.
    assert spy["trim_video"][0][0] == SRC


def test_thieu_kich_thuoc_nguon_khong_ep_reframe(spy) -> None:
    """Thiếu width/height (hiếm) -> coi như không đổi khung, không ném lỗi."""
    render_variant("vid-thieu-dim", SRC, [], _plan(), safe=TIKTOK)
    assert spy["reframe_blur"] == []
    assert spy["reframe_crop"] == []


def test_reframe_mode_crop_goi_dung_ham(spy) -> None:
    render_variant(
        "vid-crop",
        SRC,
        [],
        _plan(),
        safe=TIKTOK,
        video_width=1920,
        video_height=1080,
        reframe_mode="crop",
    )
    assert len(spy["reframe_crop"]) == 1
    assert spy["reframe_blur"] == []


def test_reframe_mode_la_bao_loi_ro_rang_khong_roi_ve_mac_dinh(spy) -> None:
    with pytest.raises(InvalidReframeModeError, match="zoom"):
        render_variant(
            "vid-mode-la",
            SRC,
            [],
            _plan(),
            safe=TIKTOK,
            video_width=1920,
            video_height=1080,
            reframe_mode="zoom",
        )
    # Lỗi phải ném TRƯỚC khi động vào ffmpeg — không âm thầm chạy blur.
    assert spy["reframe_blur"] == []
    assert spy["reframe_crop"] == []


def test_reframe_dung_chung_cho_nhieu_tap_khong_render_lai(spy) -> None:
    """Đổi khung không phụ thuộc platform/part — chỉ tốn công đúng MỘT lần
    cho cả video, các tập sau tái dùng file trung gian (idempotent)."""
    plan1 = _plan(part_index=1, part_total=2, start=0.0, end=30.0)
    plan2 = _plan(part_index=2, part_total=2, start=30.0, end=60.0)

    render_variant(
        "vid-chung", SRC, [], plan1, safe=TIKTOK, video_width=1920, video_height=1080
    )
    render_variant(
        "vid-chung", SRC, [], plan2, safe=TIKTOK, video_width=1920, video_height=1080
    )

    assert len(spy["reframe_blur"]) == 1, "phải tái dùng, không reframe lại cho tập 2"


# --------------------------------------------------------------------------- #
# hook — chỉ tập ĐẦU TIÊN, chỉ khi có hook_text
# --------------------------------------------------------------------------- #


def test_co_hook_text_tap_1_co_filter_tap_2_khong(spy) -> None:
    cues = [_cue(1, 1.0, 2.0), _cue(2, 40.0, 41.0)]
    plan1 = _plan(part_index=1, part_total=2, start=0.0, end=30.0)
    plan2 = _plan(part_index=2, part_total=2, start=30.0, end=60.0)

    render_variant(
        "vid-hook",
        SRC,
        cues,
        plan1,
        safe=TIKTOK,
        video_width=1080,
        video_height=1920,
        hook_text="Xem hết đừng bỏ lỡ!",
    )
    render_variant(
        "vid-hook",
        SRC,
        cues,
        plan2,
        safe=TIKTOK,
        video_width=1080,
        video_height=1920,
        hook_text="Xem hết đừng bỏ lỡ!",
    )

    assert len(spy["burn_subtitles"]) == 2
    _, _, _, kwargs_p1 = spy["burn_subtitles"][0]
    _, _, _, kwargs_p2 = spy["burn_subtitles"][1]
    assert kwargs_p1["hook_filter"] is not None
    assert kwargs_p1["hook_filter"].startswith("drawtext=")
    assert kwargs_p2["hook_filter"] is None


def test_khong_co_hook_text_khong_tap_nao_co_filter_hook(spy) -> None:
    cues = [_cue(1, 1.0, 2.0), _cue(2, 40.0, 41.0)]
    plan1 = _plan(part_index=1, part_total=2, start=0.0, end=30.0)
    plan2 = _plan(part_index=2, part_total=2, start=30.0, end=60.0)

    render_variant(
        "vid-nohook", SRC, cues, plan1, safe=TIKTOK, video_width=1080, video_height=1920
    )
    render_variant(
        "vid-nohook", SRC, cues, plan2, safe=TIKTOK, video_width=1080, video_height=1920
    )

    for _, _, _, kwargs in spy["burn_subtitles"]:
        assert kwargs["hook_filter"] is None


def test_hook_khong_co_cue_van_duoc_chen_khong_roi_ve_trim(spy) -> None:
    """Video không lời thoại (cues rỗng) nhưng có hook_text -> vẫn phải burn
    (re-encode) để chèn được drawtext — trim_video (-c copy) không lồng được
    filter nào."""
    render_variant(
        "vid-hook-khong-cue",
        SRC,
        [],
        _plan(),
        safe=TIKTOK,
        video_width=1080,
        video_height=1920,
        hook_text="Hook!",
    )
    assert spy["trim_video"] == []
    assert len(spy["burn_subtitles"]) == 1
    assert spy["burn_subtitles"][0][3]["hook_filter"] is not None


def test_hook_box_dung_lai_ham_task_5_khong_tu_tinh_lai(spy) -> None:
    """render_variant phải dùng ĐÚNG ``hook_box(safe)`` của Task 5, không tự
    tính lại vị trí — so khớp filter thật với filter dựng độc lập bên ngoài."""
    box = hook_box(TIKTOK)
    assert fits_in_safe_area(box, TIKTOK) is True  # đúng phép kiểm Task 2

    cues = [_cue(1, 1.0, 2.0)]
    render_variant(
        "vid-hook-box",
        SRC,
        cues,
        _plan(),
        safe=TIKTOK,
        video_width=1080,
        video_height=1920,
        hook_text="Coi liền kẻo lỡ!",
    )

    expected = build_hook_filter("Coi liền kẻo lỡ!", box, 1080, 1920)
    assert spy["burn_subtitles"][0][3]["hook_filter"] == expected


def test_hook_khong_safe_area_thi_bo_qua_khong_nem_loi(spy) -> None:
    """Thiếu ``safe`` (hiếm, phòng hờ) -> không tính được hộp hook, bỏ qua
    hook thay vì crash cả tập render."""
    cues = [_cue(1, 1.0, 2.0)]
    render_variant(
        "vid-hook-no-safe",
        SRC,
        cues,
        _plan(),
        video_width=1080,
        video_height=1920,
        hook_text="Hook!",
    )
    assert spy["burn_subtitles"][0][3]["hook_filter"] is None


# --------------------------------------------------------------------------- #
# Thứ tự filter: reframe TRƯỚC, hook/phụ đề SAU (điểm dễ sai nhất của task)
# --------------------------------------------------------------------------- #


def test_burn_chay_tren_file_da_reframe_khong_phai_nguon_goc(spy) -> None:
    cues = [_cue(1, 1.0, 2.0)]
    render_variant(
        "vid-thu-tu",
        SRC,
        cues,
        _plan(),
        safe=TIKTOK,
        video_width=1920,
        video_height=1080,
        hook_text="Hook!",
    )
    reframed_dst = spy["reframe_blur"][0][1]
    src_dung_de_burn = spy["burn_subtitles"][0][0]
    assert src_dung_de_burn == reframed_dst


def test_hook_toa_do_tinh_theo_khung_dich_khong_theo_khung_nguon(spy) -> None:
    """Nguồn 1920x1080 (ngang) nhưng hook phải tính theo khung ĐÍCH 1080x1920
    (dọc, sau reframe) — sai thứ tự sẽ tính nhầm theo 1920x1080 và chữ lệch
    ra ngoài khung khi hiện trên khung dọc thật."""
    cues = [_cue(1, 1.0, 2.0)]
    render_variant(
        "vid-toa-do",
        SRC,
        cues,
        _plan(),
        safe=TIKTOK,
        video_width=1920,
        video_height=1080,
        hook_text="Hook!",
    )
    hook_filter = spy["burn_subtitles"][0][3]["hook_filter"]
    expected_x_px = round(TIKTOK.left * 1080)  # theo bề ngang khung ĐÍCH 1080, không phải 1920
    assert f"x={expected_x_px}+" in hook_filter


# --------------------------------------------------------------------------- #
# trim_slow_intro — chỉ áp cho tập đầu, dựa trên cue của chính tập đó
# --------------------------------------------------------------------------- #


def test_trim_slow_intro_ap_dung_cho_tap_dau_khi_mo_dau_im_lang(spy) -> None:
    cues = [_cue(1, 5.0, 6.0)]  # mở đầu im lặng 5s > ngưỡng mặc định 2s
    render_variant(
        "vid-trim-intro", SRC, cues, _plan(), safe=TIKTOK, video_width=1080, video_height=1920
    )
    kwargs = spy["burn_subtitles"][0][3]
    assert kwargs["start"] == pytest.approx(5.0)
    assert kwargs["duration_sec"] == pytest.approx(25.0)


def test_trim_slow_intro_khong_ap_dung_cho_tap_thu_hai(spy) -> None:
    """Tập 2 là phần giữa video — mở đầu tập (dù có vẻ "im lặng" cục bộ)
    không phải mở đầu THẬT của cả video, không được cắt."""
    cues = [_cue(1, 35.0, 36.0)]  # cue đầu của tập 2, cách start tập 5s
    plan2 = _plan(part_index=2, part_total=2, start=30.0, end=60.0)
    render_variant(
        "vid-trim-tap2", SRC, cues, plan2, safe=TIKTOK, video_width=1080, video_height=1920
    )
    kwargs = spy["burn_subtitles"][0][3]
    assert kwargs["start"] == pytest.approx(30.0)
    assert kwargs["duration_sec"] == pytest.approx(30.0)


# --------------------------------------------------------------------------- #
# Idempotent — file variant đã tồn tại và hợp lệ thì bỏ qua toàn bộ
# --------------------------------------------------------------------------- #


def test_file_da_ton_tai_thi_bo_qua_khong_goi_reframe_hay_burn(spy, tmp_path) -> None:
    from reup_core.paths import variant_video

    plan = _plan()
    dst = variant_video("vid-idem", plan.target_platform, plan.part_index)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(b"da render roi")

    out = render_variant(
        "vid-idem",
        SRC,
        [_cue(1, 1.0, 2.0)],
        plan,
        safe=TIKTOK,
        video_width=1920,
        video_height=1080,
        hook_text="Hook!",
    )

    assert out == dst
    assert spy["reframe_blur"] == []
    assert spy["burn_subtitles"] == []
    assert spy["trim_video"] == []
