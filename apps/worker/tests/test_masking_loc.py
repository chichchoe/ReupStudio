"""Lọc vùng chữ nào ĐÁNG XOÁ — phần khó nhất của M3.

Dò chữ thì thư viện làm hộ. Quyết định vùng nào đáng xoá thì không ai làm hộ
được, và sai ở đây hỏng video mà không ai biết cho tới khi đã đăng.

Ca làm nên module này: khi đo thử trên khung hình thật (2026-08-15), OCR đọc ra
vùng chữ ``2ama`` với tin cậy 0,63 — đó là hoạ tiết chữ in trên ÁO nhân vật.
Xoá thẳng mọi vùng OCR trả về sẽ xoá luôn hoạ tiết quần áo, biển hiệu, bao bì.

Bộ test này khoá HÀNH VI TƯƠNG ĐỐI (chữ đứng yên đáng ngờ hơn chữ di chuyển,
chữ Hán đáng ngờ hơn chữ Latin) chứ không khoá con số điểm cụ thể — ngưỡng còn
phải hiệu chỉnh trên khung hình thật, khoá số cứng ở đây thì mỗi lần hiệu chỉnh
lại phải sửa test.

Nguyên tắc bao trùm, lấy từ spec: **khi phân vân thì KHÔNG xoá.** Sót một
watermark thì người dùng thấy ngay và sửa tay được.
"""

from __future__ import annotations

from src.pipeline.masking.kieu import TextBox
from src.pipeline.masking.loc import NguongLoc, cham_diem, gom_thanh_vet, loc_vung_can_xoa

NGUONG = NguongLoc()


def _vet_dung_yen(
    text: str = "这是什么",
    *,
    y: float = 0.68,
    tin_cay: float = 0.92,
    so_khung: int = 8,
    doi_chu: bool = False,
) -> list[TextBox]:
    """Một vệt chữ đứng NGUYÊN một chỗ qua nhiều khung, cách nhau 0,5 giây."""
    return [
        TextBox(
            time=i * 0.5,
            x=0.18,
            y=y,
            w=0.64,
            h=0.05,
            text=f"{text}{i}" if doi_chu else text,
            confidence=tin_cay,
        )
        for i in range(so_khung)
    ]


def _vet_di_chuyen(text: str = "2ama", *, tin_cay: float = 0.63) -> list[TextBox]:
    """Chữ in trên áo: theo người nên mỗi khung một chỗ."""
    return [
        TextBox(
            time=i * 0.5,
            x=0.30 + i * 0.06,
            y=0.52 + i * 0.03,
            w=0.09,
            h=0.04,
            text=text,
            confidence=tin_cay,
        )
        for i in range(8)
    ]


# --------------------------------------------------------------------------- #
# Gom box thành vệt
# --------------------------------------------------------------------------- #


def test_cung_vi_tri_qua_nhieu_khung_thi_la_MOT_vet() -> None:
    vet = gom_thanh_vet(_vet_dung_yen(so_khung=6), NGUONG)

    assert len(vet) == 1
    assert len(vet[0].boxes) == 6


def test_phu_de_doi_cau_nhung_dung_yen_van_la_MOT_vet() -> None:
    """Phụ đề đổi chữ liên tục mà khung không nhúc nhích. Tách theo nội dung
    chữ sẽ băm một vệt phụ đề thành hàng chục vệt lẻ, mất sạch tín hiệu bền
    vị trí — tín hiệu mạnh nhất."""
    vet = gom_thanh_vet(_vet_dung_yen(so_khung=6, doi_chu=True), NGUONG)

    assert len(vet) == 1


def test_chu_di_chuyen_thi_khong_gom_thanh_mot_vet_dai() -> None:
    vet = gom_thanh_vet(_vet_di_chuyen(), NGUONG)

    assert max(len(v.boxes) for v in vet) < 8


def test_khong_co_box_nao_thi_khong_no() -> None:
    assert gom_thanh_vet([], NGUONG) == []
    assert loc_vung_can_xoa([], NGUONG) == []


# --------------------------------------------------------------------------- #
# Chấm điểm — khoá thứ tự tương đối, không khoá con số
# --------------------------------------------------------------------------- #


def test_chu_dung_yen_dang_ngo_hon_chu_di_chuyen() -> None:
    """Tín hiệu mạnh nhất: phụ đề đứng yên, chữ trên áo đi theo người."""
    dung = cham_diem(gom_thanh_vet(_vet_dung_yen(), NGUONG)[0], NGUONG).diem
    di = max(cham_diem(v, NGUONG).diem for v in gom_thanh_vet(_vet_di_chuyen(), NGUONG))

    assert dung > di


def test_chu_han_dang_ngo_hon_chu_latin_khi_moi_thu_khac_nhu_nhau() -> None:
    """Nguồn là video Trung Quốc. Chữ Latin thường là thương hiệu in trên vật thể."""
    han = cham_diem(gom_thanh_vet(_vet_dung_yen("这是什么"), NGUONG)[0], NGUONG)
    latin = cham_diem(gom_thanh_vet(_vet_dung_yen("Coca Cola"), NGUONG)[0], NGUONG)

    assert han.diem > latin.diem


def test_doi_chu_tai_cho_dang_ngo_hon_chu_dung_im_khong_doi() -> None:
    """Phụ đề đổi câu liên tục trong cùng một khung. Biển hiệu thì không bao
    giờ đổi chữ — đây là thứ tách phụ đề khỏi biển hiệu đứng yên trong nền."""
    phu_de = cham_diem(gom_thanh_vet(_vet_dung_yen(doi_chu=True), NGUONG)[0], NGUONG)
    bien_hieu = cham_diem(gom_thanh_vet(_vet_dung_yen(doi_chu=False), NGUONG)[0], NGUONG)

    assert phu_de.diem > bien_hieu.diem


def test_diem_luon_kem_ly_do_doc_duoc() -> None:
    """Người dùng phải hiểu vì sao máy định xoá một vùng, nếu không họ không
    thể duyệt được."""
    diem = cham_diem(gom_thanh_vet(_vet_dung_yen(), NGUONG)[0], NGUONG)

    assert diem.ly_do
    assert all(isinstance(x, str) and x for x in diem.ly_do)


# --------------------------------------------------------------------------- #
# Ca thật đã đo trên khung hình
# --------------------------------------------------------------------------- #


def test_phu_de_cung_o_65_71_phan_tram_thi_XOA() -> None:
    """Số đo thật: phụ đề nằm ở 65–71% chiều cao khung."""
    ra = loc_vung_can_xoa(_vet_dung_yen(y=0.68, doi_chu=True), NGUONG)

    assert len(ra) == 1
    assert 0.6 < ra[0].y < 0.75


def test_khoi_chu_tuyen_bo_tren_dinh_thi_XOA() -> None:
    """Số đo thật: khối chữ tuyên bố của người quay ở 2,4–7,2% trên đỉnh.

    Khối này KHÔNG đổi chữ và KHÔNG nằm giữa khung, nên nó chỉ qua được nhờ
    bền vị trí cộng chữ Hán — đúng ca kiểm tra xem hai tín hiệu đó có đủ không.
    """
    ra = loc_vung_can_xoa(_vet_dung_yen(y=0.024, so_khung=12), NGUONG)

    assert ra, "khối chữ tuyên bố trên đỉnh không bị bắt"


def test_chu_in_tren_ao_nhan_vat_thi_GIU() -> None:
    """Ca ``2ama`` tin cậy 0,63 — hỏng ở đây là hỏng video mà không ai biết."""
    ra = loc_vung_can_xoa(_vet_di_chuyen(), NGUONG)

    assert ra == [], f"xoá nhầm hoạ tiết áo: {ra}"


def test_tin_cay_qua_thap_thi_loai_thang_khong_cham_diem() -> None:
    """Đọc sai chữ rồi xoá theo là xoá vào chỗ không có chữ nào."""
    ra = loc_vung_can_xoa(_vet_dung_yen(tin_cay=0.2), NGUONG)

    assert ra == []


def test_xuat_hien_dung_mot_khung_thi_GIU() -> None:
    """Một khung duy nhất không đủ để nói vùng đó bền vị trí."""
    ra = loc_vung_can_xoa(_vet_dung_yen(so_khung=1), NGUONG)

    assert ra == []


# --------------------------------------------------------------------------- #
# Ràng buộc chung
# --------------------------------------------------------------------------- #


def test_toa_do_tra_ve_luon_la_phan_tram_0_1() -> None:
    """Luật số 2 CLAUDE.md. Trả pixel ra khỏi đây là mở đường cho lỗi lệch mask
    khi video đổi độ phân giải."""
    for vung in loc_vung_can_xoa(_vet_dung_yen(doi_chu=True), NGUONG):
        for gia_tri in (vung.x, vung.y, vung.w, vung.h):
            assert 0.0 <= gia_tri <= 1.0


def test_vung_giu_lai_khoang_thoi_gian_no_ton_tai() -> None:
    """Mask chỉ được áp trong khoảng nó thật sự xuất hiện, không áp cả video."""
    ra = loc_vung_can_xoa(_vet_dung_yen(so_khung=8, doi_chu=True), NGUONG)

    assert ra[0].bat_dau == 0.0
    assert ra[0].ket_thuc >= 3.5


def test_nang_nguong_thi_xoa_it_di_chu_khong_xoa_nhieu_hon() -> None:
    """Ngưỡng phải là núm vặn theo hướng an toàn: vặn chặt thì xoá ít lại."""
    long = loc_vung_can_xoa(_vet_dung_yen(doi_chu=True), NguongLoc(diem_can_xoa=1.0))
    chat = loc_vung_can_xoa(_vet_dung_yen(doi_chu=True), NguongLoc(diem_can_xoa=99.0))

    assert len(chat) <= len(long)
    assert chat == []


def test_diem_bang_dung_nguong_thi_KHONG_xoa() -> None:
    """Khi phân vân thì không xoá — phải VƯỢT ngưỡng mới xoá."""
    vet = gom_thanh_vet(_vet_dung_yen(doi_chu=True), NGUONG)[0]
    diem = cham_diem(vet, NGUONG).diem

    assert loc_vung_can_xoa(_vet_dung_yen(doi_chu=True), NguongLoc(diem_can_xoa=diem)) == []
