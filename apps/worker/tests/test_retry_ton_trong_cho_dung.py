"""Bấm "xử lý lại" cũng phải dừng ở chỗ chờ chọn AI, không chạy thẳng.

Phát hiện khi thử tay: sau khi tách chain, ``process_video`` dùng nửa đầu nhưng
``retry_from_step`` vẫn dựng nguyên sáu bước cũ. Bước nhận dạng vẫn đặt trạng
thái ``review``, nhưng chain đã xếp sẵn các task phía sau nên chúng cứ chạy —
video đi thẳng tới ``ready`` và KHÔNG BAO GIỜ xuất hiện ở tab "Chờ dịch".

Đặt trạng thái không dừng được chain: ``pipeline_step`` chỉ bỏ qua khi video ở
``SKIPPED``. Muốn dừng thì phải không xếp task vào chain ngay từ đầu.
"""

from __future__ import annotations

from reup_core.enums import M1_STEPS_SAU_DICH, M1_STEPS_TRUOC_DICH, PipelineStep

from src.tasks.video import _cac_buoc_retry


def test_chay_lai_tu_dau_thi_dung_o_cho_cho_chon_ai() -> None:
    assert _cac_buoc_retry(None, tu_dong_dich=False) == M1_STEPS_TRUOC_DICH


def test_chay_lai_tu_giua_nua_dau_van_dung_dung_cho() -> None:
    ra = _cac_buoc_retry(PipelineStep.PROBE, tu_dong_dich=False)

    assert ra[0] is PipelineStep.PROBE
    assert ra[-1] is PipelineStep.TRANSCRIBE
    assert PipelineStep.TRANSLATE not in ra


def test_chay_lai_tu_buoc_dich_thi_chay_not_nua_sau() -> None:
    """Người dùng đã chọn AI và muốn dịch lại — không bắt họ quay về chờ nữa."""
    assert _cac_buoc_retry(PipelineStep.TRANSLATE, tu_dong_dich=False) == M1_STEPS_SAU_DICH


def test_chay_lai_tu_buoc_render_chi_render() -> None:
    ra = _cac_buoc_retry(PipelineStep.RENDER, tu_dong_dich=False)

    assert ra == (PipelineStep.RENDER,)


def test_bat_tu_dong_dich_thi_chay_mot_mach_nhu_cu() -> None:
    """Chặng M7 (luồng tự động) không có ai ngồi bấm nút."""
    ra = _cac_buoc_retry(None, tu_dong_dich=True)

    assert ra[0] is PipelineStep.DOWNLOAD
    assert ra[-1] is PipelineStep.RENDER


def test_buoc_khong_hop_le_thi_chay_lai_tu_dau() -> None:
    """Giữ hành vi cũ: tên bước lạ không được làm hỏng job, chỉ chạy lại từ đầu."""
    assert _cac_buoc_retry("buoc-khong-co-that", tu_dong_dich=False) == M1_STEPS_TRUOC_DICH
