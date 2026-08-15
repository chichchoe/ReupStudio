"""Lọc xem vùng chữ nào ĐÁNG XOÁ — phần khó nhất của M3.

Hàm THUẦN: không gọi mạng, không chạm model, không chạm DB. Đây là nơi đặt
phần lớn test tự động của chặng này.

Vì sao module này tồn tại: khi đo thử trên khung hình thật (2026-08-15), OCR
đọc ra vùng chữ ``2ama`` với tin cậy 0,63 — đó là hoạ tiết chữ in trên ÁO nhân
vật. Xoá thẳng mọi vùng OCR trả về sẽ xoá luôn hoạ tiết quần áo, biển hiệu, bao
bì sản phẩm. Dò thì thư viện làm hộ; quyết định vùng nào đáng xoá thì không.

Cách làm: gom các box gần trùng vị trí qua nhiều khung thành một VỆT, rồi chấm
điểm từng vệt theo năm tín hiệu cộng lại. Không tín hiệu nào một mình đủ để kết
luận.

**Nguyên tắc bao trùm: khi phân vân thì KHÔNG xoá.** Sót một watermark thì
người dùng thấy ngay và sửa tay được; xoá nhầm mặt người hay hoạ tiết áo thì
hỏng video mà không ai biết cho tới khi đã đăng. Vì vậy điểm phải VƯỢT ngưỡng
chứ không phải chạm ngưỡng.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .kieu import TextBox, VungCanXoa

#: Khoảng mã chữ Hán thường gặp. Nguồn của dự án là video Trung Quốc nên đây là
#: tín hiệu mạnh; chữ Latin ở khung hình Trung Quốc thường là thương hiệu in
#: trên vật thể chứ không phải phụ đề.
_CHU_HAN = re.compile(r"[一-鿿㐀-䶿]")


@dataclass(frozen=True)
class NguongLoc:
    """Các núm vặn của bộ lọc. Không hardcode ở chỗ khác.

    Trọng số dưới đây là điểm KHỞI ĐẦU, chưa hiệu chỉnh trên nhiều video. Chúng
    được chọn để tín hiệu bền vị trí lấn át các tín hiệu còn lại: đó là thứ duy
    nhất tách được phụ đề khỏi chữ in trên áo, còn các tín hiệu khác chỉ hỗ trợ.
    """

    #: Dưới mức này thì loại thẳng, không chấm điểm — đọc sai chữ rồi xoá theo
    #: là xoá vào chỗ không có chữ nào.
    tin_cay_toi_thieu: float = 0.45
    #: Hai box coi là cùng một vệt khi phần giao vượt mức này.
    iou_cung_vet: float = 0.45

    #: CỔNG CHẶN ngôn ngữ: vệt phải có ít nhất ngần này tỉ lệ ký tự Hán, HOẶC
    #: đổi chữ thật sự nhiều lần tại chỗ, thì mới được xoá.
    #:
    #: Vì sao phải là cổng chứ không phải điểm cộng — đo trên video Douyin 14
    #: phút (2026-08-15): logo tĩnh trên áo trẻ con và khối chữ tuyên bố tĩnh
    #: của người quay giống hệt nhau ở MỌI tín hiệu khác (đều đứng yên, đều tin
    #: cậy cao, đều nằm trong khung). Chúng chỉ khác nhau ở ngôn ngữ. Quét bốn
    #: bộ trọng số đều không tách được: mức chặt nhất vẫn xoá nhầm 'THE FUTURE'
    #: và 'TIME TRIES ALL' trên áo.
    #:
    #: Nguồn của dự án là video Trung Quốc: phụ đề cứng và chữ overlay của
    #: người quay đều là chữ Hán, còn chữ Latin trong khung gần như luôn là
    #: thương hiệu in trên vật thể. Bỏ sót phụ đề Latin hiếm gặp là cái giá rẻ
    #: hơn nhiều so với xoá mất hoạ tiết quần áo.
    ti_le_han_toi_thieu: float = 0.3

    #: Số câu KHÁC HẲN nhau tại cùng một chỗ, đủ để kết luận đây là vệt phụ đề
    #: kể cả khi không có chữ Hán.
    so_cau_du_ket_luan: int = 3

    #: Hai chuỗi giống nhau tới mức này thì coi là CÙNG MỘT dòng chữ, không
    #: phải "đổi chữ".
    #:
    #: Đo trên video Douyin 14 phút (2026-08-15): áo trẻ con in ``TIME TRIES
    #: ALL``, OCR đọc ra ``TIMETRIESALL`` / ``TMETRIESALL`` / ``TIME TRIESALL``
    #: / ``IETRIESALL`` — cùng một logo, mỗi khung một kiểu. Đếm nhiễu đó là
    #: "đổi chữ" cộng cho logo tĩnh đủ điểm để vượt ngưỡng: điểm nhảy từ ~1,4
    #: lên ~2,9, và máy xoá mất chữ trên áo trẻ con.
    #:
    #: Hai câu thoại khác nhau thì giống nhau dưới 30%, nên 0,75 tách sạch hai
    #: loại mà không đụng tới tín hiệu thật.
    giong_nhau_coi_la_mot: float = 0.75

    #: Chiều cao khung bao của một vệt không được vượt quá ngần này lần chiều
    #: cao box ĐẦU TIÊN của vệt đó.
    #:
    #: Vệt gom theo box gần nhất nên một dải phụ đề trôi dần theo thời gian sẽ
    #: nối thành MỘT vệt có khung bao rất cao — đo trên video rednote: dải cao
    #: 6% khung nở thành 32% và phủ suốt 2 phút. Mask như vậy vá cả phần hình
    #: vốn sạch nằm giữa hai câu.
    #:
    #: Chỉ siết chiều cao, không siết bề rộng: câu dài ngắn khác nhau nên bề
    #: rộng nở ra là chuyện bình thường.
    cao_toi_da_cua_vet: float = 1.8

    #: CỔNG CHẶN, không phải điểm: vệt xuất hiện dưới ngần này khung thì loại
    #: thẳng. Phụ đề hay watermark muốn đọc được thì phải tồn tại ít nhất nửa
    #: giây, tức ít nhất 2 mẫu ở nhịp 2 khung/giây. Chữ chỉ thoáng qua một khung
    #: là vật thể đang di chuyển hoặc OCR đọc hớ.
    #:
    #: Cổng này quan trọng vì chữ Hán + tin cậy cao đã cho ~2,3 điểm dù chỉ xuất
    #: hiện một khung — đủ vượt ngưỡng. Nhãn chữ Hán trên bao bì sản phẩm lướt
    #: qua ống kính sẽ bị xoá oan nếu không có cổng.
    so_khung_toi_thieu: int = 2

    #: Số khung để tín hiệu bền vị trí đạt điểm tối đa.
    so_khung_ben_vung: int = 4

    #: Tổng điểm phải VƯỢT mức này mới xoá. Hiệu chỉnh 2026-08-15 trên hai video
    #: thật, tổng 29 vệt:
    #:
    #:   xoá đúng   phụ đề, khối tuyên bố, watermark kênh   2,66 – 3,91
    #:   giữ đúng   crocs · 439.00 · 10001 · BEST           1,21 – 1,72
    #:
    #: Khoảng trống giữa hai nhóm là 0,94 điểm — đặt ngưỡng ở giữa để cả hai
    #: phía đều còn biên an toàn. Bản đầu đặt 2,8 theo phỏng đoán và đã bỏ lọt
    #: phụ đề ngắn hiển thị 1,5 giây.
    diem_can_xoa: float = 2.0

    #: Dải giữa khung — nơi mặt người thường ở, nên chữ ở đây đáng ngờ hơn.
    #:
    #: Mép dưới 0,92 chứ không phải 0,85: đo được phụ đề Douyin nằm ở 87% chiều
    #: cao, còn phụ đề rednote ở 70%. Vị trí phụ đề thay đổi nhiều theo nguồn,
    #: nên đây là tín hiệu YẾU — nó chỉ hỗ trợ, không bao giờ tự quyết.
    dai_giua_tren: float = 0.25
    dai_giua_duoi: float = 0.92

    trong_so: dict[str, float] = field(
        default_factory=lambda: {
            "ben_vi_tri": 1.6,
            "doi_chu_tai_cho": 1.2,
            "tin_cay": 0.6,
            "dai_giua": 0.5,
            "chu_han": 1.0,
        }
    )


@dataclass(frozen=True)
class VetChu:
    """Các box gần trùng vị trí qua nhiều khung — một "vệt" chữ theo thời gian."""

    boxes: tuple[TextBox, ...]

    @property
    def bao(self) -> tuple[float, float, float, float]:
        """Khung bao trọn cả vệt, theo phần trăm 0–1."""
        trai = min(b.x for b in self.boxes)
        tren = min(b.y for b in self.boxes)
        phai = max(b.x + b.w for b in self.boxes)
        duoi = max(b.y + b.h for b in self.boxes)
        return (trai, tren, phai - trai, duoi - tren)

    @property
    def bat_dau(self) -> float:
        return min(b.time for b in self.boxes)

    @property
    def ket_thuc(self) -> float:
        return max(b.time for b in self.boxes)


@dataclass(frozen=True)
class DiemLoc:
    diem: float
    ly_do: tuple[str, ...]


def ti_le_chu_han(text: str) -> float:
    """Tỉ lệ ký tự Hán trên tổng số ký tự không phải khoảng trắng."""
    chu = [c for c in text if not c.isspace()]
    if not chu:
        return 0.0
    return sum(1 for c in chu if _CHU_HAN.match(c)) / len(chu)


def dem_cau_khac_nhau(cac_chu: list[str], nguong_giong: float) -> int:
    """Số dòng chữ KHÁC HẲN nhau, bỏ qua nhiễu đọc của OCR.

    Gom các chuỗi giống nhau trên ``nguong_giong`` vào cùng một nhóm rồi đếm
    nhóm. So với chuỗi ĐẦU TIÊN của mỗi nhóm chứ không so đôi một: nhiễu OCR
    xoay quanh một chuỗi gốc, nên lấy chuỗi gốc làm mốc là đủ và rẻ hơn hẳn.
    """
    nhom: list[str] = []

    for chu in (" ".join(c.split()) for c in cac_chu):
        if not chu:
            continue
        if not any(SequenceMatcher(None, chu, g).ratio() >= nguong_giong for g in nhom):
            nhom.append(chu)

    return len(nhom)


def gom_thanh_vet(boxes: list[TextBox], nguong: NguongLoc) -> list[VetChu]:
    """Gom box qua các khung thành vệt, dựa trên VỊ TRÍ chứ không dựa vào chữ.

    Gom theo nội dung chữ sẽ băm một vệt phụ đề thành hàng chục vệt lẻ — phụ đề
    đổi câu liên tục mà khung không nhúc nhích — và mất sạch tín hiệu bền vị
    trí, tín hiệu mạnh nhất đang có.
    """
    if not boxes:
        return []

    theo_thoi_gian = sorted(boxes, key=lambda b: (b.time, b.y, b.x))
    vet: list[list[TextBox]] = []

    for box in theo_thoi_gian:
        for nhom in vet:
            #: So với box GẦN NHẤT của vệt, không phải box đầu tiên: chữ chạy
            #: chậm sẽ trôi xa dần khỏi điểm xuất phát nhưng luôn gần khung
            #: trước nó, và ta muốn nó vẫn được nối thành một vệt để thấy rõ là
            #: nó đang di chuyển.
            if nhom[-1].giao_nhau(box) < nguong.iou_cung_vet:
                continue

            #: Nhưng phải chặn vệt nở dọc mãi — xem ``cao_toi_da_cua_vet``.
            #: Vượt trần thì TÁCH vệt mới thay vì nối tiếp: hai câu ở hai độ cao
            #: khác nhau đúng là hai mask khác nhau.
            tren = min(b.y for b in [*nhom, box])
            duoi = max(b.y + b.h for b in [*nhom, box])
            if (duoi - tren) > nhom[0].h * nguong.cao_toi_da_cua_vet:
                continue

            nhom.append(box)
            break
        else:
            vet.append([box])

    return [VetChu(tuple(nhom)) for nhom in vet]


def qua_cong_ngon_ngu(vet: VetChu, nguong: NguongLoc) -> bool:
    """Vệt có đủ dấu hiệu là chữ CẦN XOÁ về mặt ngôn ngữ không?

    Qua cổng nếu có đủ tỉ lệ ký tự Hán, HOẶC đổi chữ thật sự nhiều lần tại chỗ
    — nhánh sau để không bỏ sót phụ đề không phải chữ Hán. Xem
    ``ti_le_han_toi_thieu`` để biết vì sao đây là cổng chặn chứ không phải điểm.
    """
    han = max(ti_le_chu_han(b.text) for b in vet.boxes)
    if han >= nguong.ti_le_han_toi_thieu:
        return True

    so_cau = dem_cau_khac_nhau([b.text for b in vet.boxes], nguong.giong_nhau_coi_la_mot)
    return so_cau >= nguong.so_cau_du_ket_luan


def cham_diem(vet: VetChu, nguong: NguongLoc) -> DiemLoc:
    """Cộng điểm năm tín hiệu. Không tín hiệu nào một mình đủ để kết luận."""
    ts = nguong.trong_so
    diem = 0.0
    ly_do: list[str] = []

    # --- 1. Bền vị trí. Phụ đề và overlay đứng gần như cố định qua nhiều khung;
    #        chữ in trên áo đi theo người nên vệt của nó rất ngắn.
    ben = min(1.0, len(vet.boxes) / nguong.so_khung_ben_vung)
    if ben > 0:
        diem += ben * ts["ben_vi_tri"]
        ly_do.append(f"đứng yên qua {len(vet.boxes)} khung")

    # --- 2. Đổi chữ tại chỗ. Phụ đề đổi câu liên tục trong cùng một khung;
    #        biển hiệu hay bao bì thì không bao giờ đổi chữ. Đây là thứ tách
    #        phụ đề khỏi chữ tĩnh nằm sẵn trong cảnh quay.
    #
    #        Đếm số câu KHÁC HẲN nhau, không đếm số chuỗi khác nhau: OCR đọc
    #        cùng một dòng chữ mỗi khung một kiểu (xem ``giong_nhau_coi_la_mot``).
    so_cau = dem_cau_khac_nhau([b.text for b in vet.boxes], nguong.giong_nhau_coi_la_mot)
    if len(vet.boxes) > 1 and so_cau > 1:
        ti_le_doi = (so_cau - 1) / (len(vet.boxes) - 1)
        diem += ti_le_doi * ts["doi_chu_tai_cho"]
        ly_do.append(f"đổi chữ {so_cau} lần tại chỗ")

    # --- 3. Tin cậy OCR, quy về 0–1 tính từ ngưỡng sàn.
    tin_cay = sum(b.confidence for b in vet.boxes) / len(vet.boxes)
    con_lai = 1.0 - nguong.tin_cay_toi_thieu
    phan_tin_cay = (tin_cay - nguong.tin_cay_toi_thieu) / con_lai if con_lai > 0 else 0.0
    phan_tin_cay = max(0.0, min(1.0, phan_tin_cay))
    diem += phan_tin_cay * ts["tin_cay"]
    ly_do.append(f"tin cậy {tin_cay:.2f}")

    # --- 4. Dải giữa khung — nơi mặt người thường ở.
    _, tren, _, cao = vet.bao
    tam_doc = tren + cao / 2
    if nguong.dai_giua_tren <= tam_doc <= nguong.dai_giua_duoi:
        diem += ts["dai_giua"]
        ly_do.append(f"nằm giữa khung ({tam_doc:.0%} chiều cao)")

    # --- 5. Ngôn ngữ.
    han = max(ti_le_chu_han(b.text) for b in vet.boxes)
    if han > 0:
        diem += han * ts["chu_han"]
        ly_do.append(f"{han:.0%} ký tự Hán")

    return DiemLoc(diem=diem, ly_do=tuple(ly_do))


def loc_vung_can_xoa(boxes: list[TextBox], nguong: NguongLoc | None = None) -> list[VungCanXoa]:
    """Từ danh sách box OCR đọc được, trả về các vùng đáng xoá.

    Box có tin cậy dưới sàn bị loại TRƯỚC khi gom vệt: để nó vào sẽ kéo dài vệt
    một cách giả tạo và làm tín hiệu bền vị trí sai lệch.
    """
    nguong = nguong or NguongLoc()

    du_tin_cay = [b for b in boxes if b.confidence >= nguong.tin_cay_toi_thieu]
    ra: list[VungCanXoa] = []

    for vet in gom_thanh_vet(du_tin_cay, nguong):
        #: Hai cổng chặn chạy TRƯỚC chấm điểm — xem ``so_khung_toi_thieu`` và
        #: ``ti_le_han_toi_thieu``.
        if len(vet.boxes) < nguong.so_khung_toi_thieu:
            continue
        if not qua_cong_ngon_ngu(vet, nguong):
            continue
        diem = cham_diem(vet, nguong)
        if diem.diem <= nguong.diem_can_xoa:
            continue
        x, y, w, h = vet.bao
        ra.append(
            VungCanXoa(
                x=x,
                y=y,
                w=w,
                h=h,
                bat_dau=vet.bat_dau,
                ket_thuc=vet.ket_thuc,
                diem=diem.diem,
                ly_do=diem.ly_do,
            )
        )

    return ra
