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
    """Toạ độ âm hoặc quá 1 làm hỏng phép quy đổi sang pixel ở bước vá.

    Gọi thẳng ``noi_bien`` chứ không qua ``dung_mask``: một vùng phủ trọn khung
    hình bị chốt diện tích ở cuối ``dung_mask`` loại bỏ — đúng như mong muốn —
    nên đi đường đó thì không kiểm được phép kẹp toạ độ.
    """
    from src.pipeline.masking.timeline import noi_bien

    m = noi_bien(_vung(x=0.0, y=0.0, w=1.0, h=1.0), TS)

    assert m.x == 0.0
    assert m.y == 0.0
    assert m.x + m.w == pytest.approx(1.0)
    assert m.y + m.h == pytest.approx(1.0)


def test_vung_phu_gan_tron_khung_bi_BO_o_chot_cuoi() -> None:
    """Chốt cuối: mask quá lớn bị bỏ hẳn, không bị cắt nhỏ.

    Cắt nhỏ sẽ xoá một phần tuỳ tiện của vùng đó. Bỏ hẳn thì chữ còn nguyên —
    người dùng thấy ngay và sửa tay được.
    """
    assert dung_mask([_vung(x=0.0, y=0.0, w=1.0, h=1.0)], TS) == []


def test_chu_cao_hon_thi_noi_bien_nhieu_hon() -> None:
    """Nới theo TỈ LỆ chiều cao chữ, không nới một số cố định: cỡ chữ khác nhau
    giữa các video, mà vệt mờ để lại thì tỉ lệ thuận với cỡ chữ.

    Gọi thẳng ``noi_bien``: vùng chữ cao 10% khung sau khi nới vượt trần chiều
    cao và bị ``dung_mask`` loại — đúng như mong muốn, nhưng đi đường đó thì
    không kiểm được phép nới.
    """
    from src.pipeline.masking.timeline import noi_bien

    nho = noi_bien(_vung(h=0.03), TS)
    to = noi_bien(_vung(h=0.10), TS)

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


def test_gop_KHONG_duoc_no_day_chuyen_thanh_mask_nuot_ca_khung() -> None:
    """Ca hỏng thật, phát hiện khi chạy trên video rednote đầy đủ (2026-08-15).

    Mask cuối cùng ghi vào DB là 96% × 89% khung hình, phủ suốt 123 giây — máy
    định xoá gần trọn video. Trần chống phình chỉ so khung GỘP với hai khung
    vừa gộp, nên mỗi bước đều lọt: A+B hơi to, (A+B)+C hơi to hơn, cứ thế lớn
    dần cho tới khi nuốt cả khung.

    Phụ đề và watermark luôn NHỎ. Một mask chiếm phần lớn khung hình không bao
    giờ đúng, bất kể nó lớn lên theo đường nào — nên phải chặn bằng trần TUYỆT
    ĐỐI, không phải trần tương đối.
    """
    #: Sáu dải chữ rải khắp khung, chồng thời gian, mỗi cặp kề nhau chồng chỗ
    #: một chút — đúng hình dạng dẫn tới vụ nổ dây chuyền.
    vung = [
        _vung(x=0.05, y=0.02 + i * 0.14, w=0.9, h=0.13, bat_dau=0.0, ket_thuc=120.0)
        for i in range(6)
    ]

    ra = dung_mask(vung, TS)

    for m in ra:
        assert m.w * m.h <= TS.dien_tich_toi_da, (
            f"mask nuốt {m.w * m.h:.0%} khung hình — chắc chắn xoá nhầm cả hình"
        )


# --------------------------------------------------------------------------- #
# Mask không được sống lâu hơn bằng chứng
# --------------------------------------------------------------------------- #


def test_mask_khong_song_lau_hon_bang_chung_thay_duoc() -> None:
    """Ca hỏng thật, video Douyin 14 phút (2026-08-15).

    Một vệt chỉ 6 khung bằng chứng — tức 3 giây ở nhịp 2 khung/giây — lại sinh
    ra mask sống 839 giây, đúng bằng cả video. Nhìn khung hình ở giây 300 thì
    chỗ đó KHÔNG có chữ nào, máy vẫn vá.

    Nguyên nhân: phép nối so khoảng hở với ``ket_thuc`` đã bị kéo dài sau mỗi
    lần nối, nên cửa sổ cứ trượt về phía trước và nuốt mọi lần chữ xuất hiện ở
    vùng lân cận trong suốt video.

    Hậu quả đo được: 113 mask chồng nhau phủ 71% khung hình, video 14 phút chạy
    hơn 4 tiếng.
    """
    #: Bốn lần chữ xuất hiện, mỗi lần 1 giây, cách nhau đúng 1 giây — đủ gần để
    #: phép nối cũ chuỗi hết lại thành một mask dài 60 giây.
    vung = [_vung(y=0.72, h=0.05, bat_dau=t, ket_thuc=t + 1.0) for t in (0.0, 2.0, 4.0, 6.0)]
    #: Rồi một lần nữa ở tận cuối video.
    vung.append(_vung(y=0.72, h=0.05, bat_dau=60.0, ket_thuc=61.0))

    ra = dung_mask(vung, TS)

    tong_song = sum(m.ket_thuc - m.bat_dau for m in ra)
    assert tong_song < 20.0, (
        f"mask sống tổng {tong_song:.0f}s trong khi chỉ thấy chữ 5 lần x 1 giây"
    )


def test_chu_hien_lien_tuc_thi_van_duoc_noi_thanh_mot() -> None:
    """Không được siết tới mức phá luôn ca đúng: chữ hiện liên tục thì mask
    phải liền một dải, nếu không nó nhấp nháy."""
    vung = [_vung(y=0.72, h=0.05, bat_dau=t / 2, ket_thuc=t / 2 + 0.5) for t in range(20)]

    ra = dung_mask(vung, TS)

    assert len(ra) == 1
    assert ra[0].ket_thuc - ra[0].bat_dau >= 9.0
