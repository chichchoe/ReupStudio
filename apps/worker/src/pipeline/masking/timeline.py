"""Biến vùng dò được thành mask ỔN ĐỊNH đủ để đem đi vá (M3).

Hàm THUẦN: không gọi mạng, không chạm model, không chạm DB.

``loc.py`` trả về vùng đúng chỗ nhưng chưa vá được ngay. Ba việc phải làm thêm,
cả ba đều xuất phát từ số đo trên video thật (2026-08-15) chứ không phải từ lo
xa:

1. **Nối khoảng hở.** Đo trên video Douyin: 2 trong 6 khung mẫu đọc ra 0 vùng
   chữ dù phụ đề vẫn đang hiện. Mask tắt ở những khung đó thì chữ gốc hiện lại
   nửa giây — nhấp nháy còn khó chịu hơn là không xoá.

2. **Nới biên thời gian.** Lấy mẫu 2 khung/giây nên biên lệch tới nửa giây: câu
   phụ đề bắt đầu TRƯỚC khung mẫu đầu tiên bắt được nó và tắt SAU khung mẫu
   cuối. Không nới thì đầu và đuôi mỗi câu vẫn còn nguyên chữ.

3. **Nới biên không gian.** Viền chữ có khử răng cưa; mask ôm sát đúng khung
   chữ sẽ để lại vệt mờ quanh chỗ vừa vá.
"""

from __future__ import annotations

from dataclasses import dataclass

from .kieu import VungCanXoa


@dataclass(frozen=True)
class ThamSoTimeline:
    """Núm vặn của bước dựng mask. Không hardcode ở chỗ khác."""

    #: Nới biên mỗi phía theo TỈ LỆ chiều cao vùng chữ. Nới theo tỉ lệ chứ không
    #: theo số cố định: cỡ chữ khác nhau giữa các video, mà vệt mờ để lại thì
    #: tỉ lệ thuận với cỡ chữ.
    le_theo_chieu_cao: float = 0.35
    #: Sàn nới biên theo phần trăm khung, phòng khi chữ quá nhỏ.
    le_toi_thieu: float = 0.006

    #: Nửa bước lấy mẫu — nới ra mỗi đầu đúng chừng này. Ở nhịp 2 khung/giây thì
    #: bước là 0,5 giây nên nới 0,25 giây mỗi đầu.
    nua_buoc_lay_mau: float = 0.25

    #: Khoảng hở thời gian còn nối được giữa hai lần thấy cùng một vùng. Đặt
    #: rộng hơn vài khung mẫu để chịu được lúc OCR đọc trượt, nhưng đủ hẹp để
    #: hai lần xuất hiện thật sự khác nhau không bị dính vào nhau.
    ho_toi_da: float = 1.5

    #: Hai vùng coi là "cùng chỗ" khi phần giao vượt mức này. Chỉ dùng cho việc
    #: nối một vùng với CHÍNH NÓ qua thời gian, nơi hai khung gần trùng khít.
    iou_cung_cho: float = 0.5

    #: Trần phình to khi gộp hai mask chồng nhau: khung gộp không được lớn hơn
    #: tổng diện tích hai mask nhân hệ số này. Chặn trường hợp hai dải mỏng bắt
    #: chéo nhau tạo ra một khung vuông to nuốt cả vùng hình vốn sạch.
    tran_phinh_khi_gop: float = 1.8


@dataclass(frozen=True)
class MaskRegion:
    """Một vùng sẽ bị xoá, đã nới biên và đã nối khoảng hở.

    Toạ độ phần trăm 0–1 (luật số 2 CLAUDE.md); ``bat_dau``/``ket_thuc`` tính
    bằng giây từ đầu video.
    """

    x: float
    y: float
    w: float
    h: float
    bat_dau: float
    ket_thuc: float
    diem: float
    ly_do: tuple[str, ...]

    def giao_nhau(self, khac: MaskRegion) -> float:
        trai = max(self.x, khac.x)
        tren = max(self.y, khac.y)
        phai = min(self.x + self.w, khac.x + khac.w)
        duoi = min(self.y + self.h, khac.y + khac.h)

        if phai <= trai or duoi <= tren:
            return 0.0

        chung = (phai - trai) * (duoi - tren)
        tong = self.w * self.h + khac.w * khac.h - chung
        return chung / tong if tong > 0 else 0.0


def _kep(gia_tri: float) -> float:
    return max(0.0, min(1.0, gia_tri))


def noi_bien(vung: VungCanXoa, tham_so: ThamSoTimeline) -> MaskRegion:
    """Nới vùng ra bốn phía và nới thời gian ra hai đầu."""
    le = max(tham_so.le_toi_thieu, vung.h * tham_so.le_theo_chieu_cao)

    trai = _kep(vung.x - le)
    tren = _kep(vung.y - le)
    phai = _kep(vung.x + vung.w + le)
    duoi = _kep(vung.y + vung.h + le)

    return MaskRegion(
        x=trai,
        y=tren,
        w=phai - trai,
        h=duoi - tren,
        bat_dau=max(0.0, vung.bat_dau - tham_so.nua_buoc_lay_mau),
        ket_thuc=vung.ket_thuc + tham_so.nua_buoc_lay_mau,
        diem=vung.diem,
        ly_do=vung.ly_do,
    )


def _gop(a: MaskRegion, b: MaskRegion) -> MaskRegion:
    """Gộp hai mask cùng chỗ thành một, khung bao trùm cả hai.

    Điểm lấy CAO NHẤT chứ không lấy trung bình: điểm dùng để xếp hạng vùng đáng
    ngờ trên giao diện, lấy trung bình sẽ làm loãng một vùng chắc chắn phải xoá
    khi nó dính với một vùng điểm thấp.
    """
    trai = min(a.x, b.x)
    tren = min(a.y, b.y)
    phai = max(a.x + a.w, b.x + b.w)
    duoi = max(a.y + a.h, b.y + b.h)

    #: Giữ thứ tự lý do và bỏ trùng — dict giữ thứ tự chèn từ Python 3.7.
    ly_do = tuple(dict.fromkeys(a.ly_do + b.ly_do))

    return MaskRegion(
        x=trai,
        y=tren,
        w=phai - trai,
        h=duoi - tren,
        bat_dau=min(a.bat_dau, b.bat_dau),
        ket_thuc=max(a.ket_thuc, b.ket_thuc),
        diem=max(a.diem, b.diem),
        ly_do=ly_do,
    )


def noi_khoang_ho(masks: list[MaskRegion], tham_so: ThamSoTimeline) -> list[MaskRegion]:
    """Nối các mask cùng chỗ mà chỉ hở nhau một quãng ngắn.

    Chỉ nối khi VỪA cùng chỗ VỪA gần nhau về thời gian. Bỏ điều kiện cùng chỗ
    thì phụ đề dưới đáy và khối tuyên bố trên đỉnh sẽ dính vào nhau thành một
    mask khổng lồ nuốt trọn khung hình.
    """
    ra: list[MaskRegion] = []

    for mask in sorted(masks, key=lambda m: m.bat_dau):
        for chi_so, da_co in enumerate(ra):
            cung_cho = da_co.giao_nhau(mask) >= tham_so.iou_cung_cho
            ho = mask.bat_dau - da_co.ket_thuc
            if cung_cho and ho <= tham_so.ho_toi_da:
                ra[chi_so] = _gop(da_co, mask)
                break
        else:
            ra.append(mask)

    return ra


def _chong_thoi_gian(a: MaskRegion, b: MaskRegion) -> bool:
    return a.bat_dau <= b.ket_thuc and b.bat_dau <= a.ket_thuc


def _chong_khong_gian(a: MaskRegion, b: MaskRegion) -> bool:
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


def gop_chong_nhau(masks: list[MaskRegion], tham_so: ThamSoTimeline) -> list[MaskRegion]:
    """Gộp các mask vừa chồng thời gian vừa chồng chỗ thành một.

    KHÔNG dùng IoU ở đây. Đo trên video rednote: ba dòng tuyên bố xếp chồng ở
    đỉnh khung có phần chồng chiếm hơn nửa mỗi dòng, nhưng IoU chỉ 0,44 và 0,40
    — dưới mọi ngưỡng hợp lý. IoU là thước đo sai cho dải mỏng nằm sát nhau, vì
    mẫu số cộng cả hai diện tích trong khi phần chồng bị giới hạn bởi dải mỏng
    hơn.

    Vì sao đáng gộp: vá riêng từng dòng vừa tốn nhiều lượt gọi model, vừa để
    lại đường nối giữa các vùng — LaMa dựng lại nền theo từng vùng độc lập nên
    hai vùng cạnh nhau không khớp nét.

    Lặp tới khi không gộp được nữa: gộp A với B có thể làm khung mới chạm sang
    C, và bỏ sót vòng đó thì kết quả phụ thuộc thứ tự đầu vào.
    """
    ra = list(masks)

    con_gop = True
    while con_gop:
        con_gop = False
        for i in range(len(ra)):
            for j in range(i + 1, len(ra)):
                a, b = ra[i], ra[j]
                if not (_chong_thoi_gian(a, b) and _chong_khong_gian(a, b)):
                    continue

                gop = _gop(a, b)
                if gop.w * gop.h > (a.w * a.h + b.w * b.h) * tham_so.tran_phinh_khi_gop:
                    continue

                ra = [m for k, m in enumerate(ra) if k not in (i, j)] + [gop]
                con_gop = True
                break
            if con_gop:
                break

    return ra


def dung_mask(vung: list[VungCanXoa], tham_so: ThamSoTimeline | None = None) -> list[MaskRegion]:
    """Từ vùng ``loc.py`` lọc ra, dựng danh sách mask sẵn sàng đem đi vá.

    Ba bước, thứ tự bắt buộc:

    1. **Nới biên** trước tiên. Nối/gộp trước thì phép so sánh làm việc trên
       khung chưa nới, và hai vùng sát nhau vừa đủ để dính sau khi nới sẽ bị bỏ
       sót.
    2. **Nối khoảng hở** — cùng một vùng xuất hiện lại sau khi OCR đọc trượt.
    3. **Gộp chồng nhau** — các vùng khác nhau nhưng dính vào nhau cùng lúc.
       Chạy sau cùng vì nó chỉ có nghĩa khi mỗi vùng đã liền mạch về thời gian.
    """
    tham_so = tham_so or ThamSoTimeline()

    da_noi_bien = [noi_bien(v, tham_so) for v in vung]
    da_noi_ho = noi_khoang_ho(da_noi_bien, tham_so)
    da_gop = gop_chong_nhau(da_noi_ho, tham_so)

    return sorted(da_gop, key=lambda m: (m.bat_dau, m.y))
