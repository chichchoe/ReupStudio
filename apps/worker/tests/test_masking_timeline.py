"""Biến vùng dò được thành mask ỔN ĐỊNH đủ để vá — hàm thuần, test kỹ.

``loc.py`` trả về vùng đúng chỗ nhưng chưa dùng vá được ngay, vì hai lý do đo
được trên video thật (2026-08-15):

1. **OCR bỏ sót khung.** Đo trên video Douyin: 2 trong 6 khung mẫu đọc ra 0
   vùng chữ dù phụ đề vẫn đang hiện. Mask tắt ở những khung đó thì chữ gốc hiện
   lại nửa giây — nhìn còn tệ hơn là không xoá, vì nó nhấp nháy.

2. **Lấy mẫu 2 khung/giây nên biên thời gian lệch tới nửa giây.** Câu phụ đề
   thường bắt đầu TRƯỚC khung mẫu đầu tiên bắt được nó và kết thúc SAU khung
   mẫu cuối. Không nới thì đầu và đuôi mỗi câu vẫn còn nguyên chữ.

Thêm một lý do nữa từ bản chất của việc vá: viền chữ có khử răng cưa, mask ôm
sát đúng khung chữ sẽ để lại vệt mờ quanh chỗ vừa vá.
"""

from __future__ import annotations

import pytest

from src.pipeline.masking.kieu import VungCanXoa
from src.pipeline.masking.timeline import ThamSoTimeline, dung_mask

TS = ThamSoTimeline()


def _vung(
    *,
    x: float = 0.2,
    y: float = 0.8,
    w: float = 0.6,
    h: float = 0.05,
    bat_dau: float = 2.0,
    ket_thuc: float = 4.0,
    diem: float = 3.5,
    ly_do: tuple[str, ...] = ("đứng yên qua 5 khung",),
) -> VungCanXoa:
    return VungCanXoa(
        x=x, y=y, w=w, h=h, bat_dau=bat_dau, ket_thuc=ket_thuc, diem=diem, ly_do=ly_do
    )


# --------------------------------------------------------------------------- #
# Nới biên
# --------------------------------------------------------------------------- #


def test_mask_rong_hon_khung_chu_o_ca_bon_phia() -> None:
    """Viền chữ có khử răng cưa. Ôm sát đúng khung chữ thì vá xong còn vệt mờ."""
    (m,) = dung_mask([_vung()], TS)

    assert m.x < 0.2
    assert m.y < 0.8
    assert m.x + m.w > 0.8
    assert m.y + m.h > 0.85


def test_noi_bien_khong_tran_ra_ngoai_khung() -> None:
    """Toạ độ âm hoặc quá 1 làm hỏng phép quy đổi sang pixel ở bước vá."""
    (m,) = dung_mask([_vung(x=0.0, y=0.0, w=1.0, h=1.0)], TS)

    assert m.x == 0.0
    assert m.y == 0.0
    assert m.x + m.w == pytest.approx(1.0)
    assert m.y + m.h == pytest.approx(1.0)


def test_chu_cao_hon_thi_noi_bien_nhieu_hon() -> None:
    """Nới theo TỈ LỆ chiều cao chữ, không nới một số cố định: cỡ chữ khác nhau
    giữa các video, mà vệt mờ để lại thì tỉ lệ thuận với cỡ chữ."""
    (nho,) = dung_mask([_vung(h=0.03)], TS)
    (to,) = dung_mask([_vung(h=0.10)], TS)

    assert to.h - 0.10 > nho.h - 0.03


# --------------------------------------------------------------------------- #
# Nới thời gian theo nhịp lấy mẫu
# --------------------------------------------------------------------------- #


def test_noi_thoi_gian_ra_hai_dau_theo_nhip_lay_mau() -> None:
    """Lấy mẫu 2 khung/giây nên câu bắt đầu tới nửa giây TRƯỚC khung bắt được."""
    (m,) = dung_mask([_vung(bat_dau=2.0, ket_thuc=4.0)], TS)

    assert m.bat_dau < 2.0
    assert m.ket_thuc > 4.0


def test_thoi_gian_bat_dau_khong_bao_gio_am() -> None:
    """Chữ xuất hiện ngay khung đầu video — nới ra trước số 0 là vô nghĩa."""
    (m,) = dung_mask([_vung(bat_dau=0.0, ket_thuc=2.0)], TS)

    assert m.bat_dau == 0.0


# --------------------------------------------------------------------------- #
# Nối khoảng hở — lý do chính module này tồn tại
# --------------------------------------------------------------------------- #


def test_cung_cho_ho_ngan_thi_NOI_lam_mot() -> None:
    """Đúng ca đo được: OCR đọc trượt vài khung giữa chừng. Không nối thì mask
    tắt ở đó và chữ gốc hiện lại, nhấp nháy còn khó chịu hơn không xoá."""
    ra = dung_mask([_vung(bat_dau=0.0, ket_thuc=1.0), _vung(bat_dau=2.0, ket_thuc=3.0)], TS)

    assert len(ra) == 1
    assert ra[0].bat_dau == 0.0
    assert ra[0].ket_thuc >= 3.0


def test_cung_cho_ho_dai_thi_GIU_RIENG() -> None:
    """Hai câu cách nhau nửa phút là hai lần xuất hiện khác nhau. Nối lại thành
    một sẽ vá cả đoạn giữa vốn sạch sẽ."""
    ra = dung_mask([_vung(bat_dau=0.0, ket_thuc=1.0), _vung(bat_dau=40.0, ket_thuc=41.0)], TS)

    assert len(ra) == 2


def test_khac_cho_thi_khong_noi_du_trung_thoi_gian() -> None:
    """Phụ đề dưới đáy và khối tuyên bố trên đỉnh cùng hiện một lúc, nhưng nối
    chúng lại sẽ tạo một mask khổng lồ nuốt trọn cả khung hình."""
    ra = dung_mask(
        [_vung(y=0.05, bat_dau=0.0, ket_thuc=5.0), _vung(y=0.85, bat_dau=0.0, ket_thuc=5.0)],
        TS,
    )

    assert len(ra) == 2


def test_noi_xong_thi_khung_bao_trum_ca_hai() -> None:
    """Câu sau dài hơn câu trước nên rộng hơn — mask phải phủ được câu rộng nhất."""
    ra = dung_mask(
        [
            _vung(x=0.30, w=0.40, bat_dau=0.0, ket_thuc=1.0),
            _vung(x=0.20, w=0.60, bat_dau=1.5, ket_thuc=2.5),
        ],
        TS,
    )

    assert len(ra) == 1
    assert ra[0].x <= 0.20
    assert ra[0].x + ra[0].w >= 0.80


def test_noi_xong_thi_giu_ly_do_cua_ca_hai() -> None:
    """Người dùng phải đọc được vì sao vùng này bị xoá, kể cả sau khi gộp."""
    ra = dung_mask(
        [
            _vung(bat_dau=0.0, ket_thuc=1.0, ly_do=("100% ký tự Hán",)),
            _vung(bat_dau=1.5, ket_thuc=2.5, ly_do=("đổi chữ 3 lần tại chỗ",)),
        ],
        TS,
    )

    gop = " ".join(ra[0].ly_do)
    assert "Hán" in gop
    assert "đổi chữ" in gop


def test_noi_xong_lay_diem_cao_nhat() -> None:
    """Điểm dùng để xếp hạng vùng đáng ngờ trên giao diện. Lấy trung bình sẽ
    làm loãng một vùng chắc chắn phải xoá khi nó dính với một vùng điểm thấp."""
    ra = dung_mask(
        [
            _vung(bat_dau=0.0, ket_thuc=1.0, diem=2.1),
            _vung(bat_dau=1.5, ket_thuc=2.5, diem=3.9),
        ],
        TS,
    )

    assert ra[0].diem == pytest.approx(3.9)


# --------------------------------------------------------------------------- #
# Gộp mask chồng nhau cùng lúc
# --------------------------------------------------------------------------- #


def test_hai_mask_cham_nhau_cung_luc_thi_GOP() -> None:
    """Ca thật, số đo nguyên văn từ video rednote (2026-08-15).

    Ba dòng tuyên bố ở đỉnh khung. Sau khi nới biên chúng chồng lên nhau rõ
    rệt, nhưng IoU chỉ đạt 0,44 và 0,40 — dưới ngưỡng gộp. IoU là thước đo SAI
    cho các dòng chữ xếp chồng: hai dải mỏng nằm sát nhau luôn cho IoU thấp dù
    phần chồng chiếm hơn nửa mỗi dải.

    Vá riêng từng dòng vừa tốn ba lượt gọi model, vừa để lại đường nối giữa các
    vùng vừa vá — LaMa dựng lại nền theo từng vùng độc lập nên hai vùng cạnh
    nhau không khớp nét.
    """
    ra = dung_mask(
        [
            _vung(x=0.556, y=0.024, w=0.336, h=0.023, bat_dau=0.0, ket_thuc=20.0),
            _vung(x=0.560, y=0.039, w=0.325, h=0.022, bat_dau=0.0, ket_thuc=20.0),
            _vung(x=0.504, y=0.052, w=0.439, h=0.022, bat_dau=0.0, ket_thuc=20.0),
        ],
        TS,
    )

    assert len(ra) == 1
    assert ra[0].y <= 0.017
    assert ra[0].y + ra[0].h >= 0.080


def test_hai_mask_cham_nhau_nhung_KHAC_luc_thi_khong_gop() -> None:
    """Chồng chỗ mà không chồng thời gian thì gộp lại sẽ vá thừa cả quãng giữa."""
    ra = dung_mask(
        [
            _vung(y=0.30, h=0.05, bat_dau=0.0, ket_thuc=2.0),
            _vung(y=0.32, h=0.05, bat_dau=60.0, ket_thuc=62.0),
        ],
        TS,
    )

    assert len(ra) == 2


def test_hai_mask_cung_luc_nhung_ROI_NHAU_thi_khong_gop() -> None:
    """Hai dòng phụ đề cách xa nhau theo chiều dọc. Gộp lại sẽ nuốt luôn khoảng
    hình ở giữa, tức xoá mất phần hình vốn sạch."""
    ra = dung_mask(
        [
            _vung(y=0.10, h=0.05, bat_dau=0.0, ket_thuc=5.0),
            _vung(y=0.80, h=0.05, bat_dau=0.0, ket_thuc=5.0),
        ],
        TS,
    )

    assert len(ra) == 2


# --------------------------------------------------------------------------- #
# Ràng buộc chung
# --------------------------------------------------------------------------- #


def test_khong_co_vung_nao_thi_khong_no() -> None:
    assert dung_mask([], TS) == []


def test_ket_qua_sap_theo_thoi_gian() -> None:
    """Bước vá duyệt video một lượt từ đầu tới cuối, mask lộn xộn thì phải sắp
    lại ở đó — làm ở đây một lần cho xong."""
    ra = dung_mask(
        [
            _vung(y=0.10, bat_dau=30.0, ket_thuc=31.0),
            _vung(y=0.50, bat_dau=5.0, ket_thuc=6.0),
            _vung(y=0.85, bat_dau=12.0, ket_thuc=13.0),
        ],
        TS,
    )

    assert [m.bat_dau for m in ra] == sorted(m.bat_dau for m in ra)


def test_toa_do_luon_phan_tram_0_1() -> None:
    for m in dung_mask([_vung(), _vung(y=0.02, h=0.04)], TS):
        for gia_tri in (m.x, m.y, m.w, m.h):
            assert 0.0 <= gia_tri <= 1.0
