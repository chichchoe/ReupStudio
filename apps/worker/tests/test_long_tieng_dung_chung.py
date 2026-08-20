"""Hằng số xếp lịch lồng tiếng phải dùng CHUNG cho worker và API.

Dòng thời gian ở màn duyệt vẽ lớp giọng và bôi đỏ chỗ tràn — muốn vẽ đúng thì
phải tính bằng đúng luật worker dùng lúc dựng. Chép hằng số sang chỗ khác là
mở đường cho hai bên lệch nhau: giao diện báo xanh mà bản dựng thật vẫn tràn.
"""

from __future__ import annotations

from reup_core.long_tieng import (
    KHE_GIUA_HAI_CAU,
    TOC_DO_TOI_DA,
    TOC_DO_TOI_THIEU,
    tinh_cho_cau,
)


def test_cau_vua_khung_thi_khong_ep_khong_tran() -> None:
    r = tinh_cho_cau(bat_dau=0.0, cau_sau_bat_dau=3.0, do_dai_giong=1.0)
    assert r.he_so_toc_do == TOC_DO_TOI_THIEU
    assert r.tran_giay == 0.0


def test_muon_khoang_lang_phia_sau_truoc_khi_ep_nhanh() -> None:
    #: Cue kết thúc ở 1,0 nhưng câu sau mãi 3,0 mới bắt đầu -> có 2,92 giây
    #: dùng được. Giọng 2,5 giây vẫn vừa, KHÔNG cần ép.
    r = tinh_cho_cau(bat_dau=0.0, cau_sau_bat_dau=3.0, do_dai_giong=2.5)
    assert r.he_so_toc_do == TOC_DO_TOI_THIEU
    assert r.tran_giay == 0.0


def test_chua_khe_giua_hai_cau() -> None:
    r = tinh_cho_cau(bat_dau=0.0, cau_sau_bat_dau=1.0, do_dai_giong=0.5)
    assert abs(r.cho_trong_giay - (1.0 - KHE_GIUA_HAI_CAU)) < 1e-9


def test_ep_nhanh_khi_thieu_cho_nhung_khong_qua_tran() -> None:
    #: Cần gấp 3 lần chỗ trống -> chạm trần 1,5, không phải 3,0.
    r = tinh_cho_cau(bat_dau=0.0, cau_sau_bat_dau=1.08, do_dai_giong=3.0)
    assert r.he_so_toc_do == TOC_DO_TOI_DA


def test_van_tran_sau_khi_ep_het_co() -> None:
    r = tinh_cho_cau(bat_dau=0.0, cau_sau_bat_dau=1.08, do_dai_giong=3.0)
    #: 3,0 / 1,5 = 2,0 giây, chỗ trống 1,0 -> tràn 1,0 giây.
    assert abs(r.tran_giay - 1.0) < 1e-6


def test_cau_cuoi_khong_co_gi_phia_sau_de_dung():
    #: Không truyền ``cau_sau_bat_dau`` = câu cuối, không bao giờ tràn.
    r = tinh_cho_cau(bat_dau=0.0, cau_sau_bat_dau=None, do_dai_giong=9.9)
    assert r.he_so_toc_do == TOC_DO_TOI_THIEU and r.tran_giay == 0.0


def test_khong_co_giong_thi_khong_tinh() -> None:
    r = tinh_cho_cau(bat_dau=0.0, cau_sau_bat_dau=1.0, do_dai_giong=None)
    assert r.he_so_toc_do == TOC_DO_TOI_THIEU and r.tran_giay == 0.0


def test_khong_chia_cho_khong_khi_hai_cau_dinh_nhau() -> None:
    #: Câu sau bắt đầu trước cả khe hở -> chỗ trống <= 0. Không được nổ.
    r = tinh_cho_cau(bat_dau=1.0, cau_sau_bat_dau=1.02, do_dai_giong=0.5)
    assert r.cho_trong_giay == 0.0
    assert r.he_so_toc_do == TOC_DO_TOI_THIEU
