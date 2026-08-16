"""Trộn giọng Việt vào video: giọng Việt phải là tiếng CHÍNH.

Quan sát ngày 2026-08-16: người dùng báo "âm gốc không tắt và còn to hơn lồng
tiếng". Đo bản dựng ra thì đỉnh chỉ −39 dBFS, tức cả dải tiếng bị hạ mạnh.

Nguyên nhân: ``amix`` mặc định ``normalize=1`` — chia mỗi đầu vào cho số đầu
vào, nên giọng Việt còn một nửa (−6 dB) dù nó phải là tiếng chính.
"""

from __future__ import annotations

from src.ffmpeg.dub import loc_tron


def test_khong_de_amix_tu_chia_doi_am_luong() -> None:
    """Thiếu `normalize=0` là giọng Việt tụt còn 50%."""
    assert "normalize=0" in loc_tron(0.08)


def test_muc_am_goc_di_dung_vao_dai_goc() -> None:
    loc = loc_tron(0.08)

    assert "[0:a]volume=0.08[goc]" in loc
    #: Giọng Việt KHÔNG qua bộ lọc volume nào — nó vào amix nguyên vẹn.
    assert "[goc][1:a]amix" in loc


def test_muc_0_thi_bo_han_dai_goc() -> None:
    """Người dùng đặt 0 là muốn tắt hẳn tiếng gốc, không phải nhân với 0."""
    loc = loc_tron(0)

    assert "0:a" not in loc
    assert "amix" not in loc
    assert loc == "[1:a]anull[a]"


def test_muc_am_khong_the_lam_goc_to_hon_tieng_viet() -> None:
    """Cái người dùng thật sự cần: âm gốc luôn nhỏ hơn giọng đọc."""
    for muc in (0.05, 0.08, 0.18, 0.5):
        loc = loc_tron(muc)
        assert f"volume={muc}[goc]" in loc
        assert muc < 1.0, "âm gốc bằng hoặc to hơn giọng Việt là sai thiết kế"
