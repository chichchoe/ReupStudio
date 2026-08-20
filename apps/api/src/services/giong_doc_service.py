"""Logic nghiệp vụ của thư viện giọng. KHÔNG biết gì về HTTP/FastAPI."""

from __future__ import annotations

import uuid
from pathlib import Path

import sqlalchemy as sa
from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.logging import get_logger
from reup_core.models import GiongDoc
from reup_core.paths import giong_tai_len
from sqlalchemy.orm import Session

from ..errors import ApiError, NotFound

log = get_logger(__name__)

#: Nguồn nào BẮT BUỘC phải có file tải lên. ``tam_tu_may`` tự dựng nên không cần.
NGUON_CAN_FILE = frozenset(
    {NguonGiong.TU_THU.value, NguonGiong.CAT_TU_FILE.value, NguonGiong.THUE_DOC.value}
)


def danh_sach(db: Session) -> list[GiongDoc]:
    """Mọi giọng, giọng mặc định đứng đầu rồi tới giọng mới nhất.

    Sắp xếp trong Python chứ không trong SQL: bảng này cỡ vài chục dòng, và
    cùng một luật sắp xếp còn được ``xoa()`` dùng lại để chọn giọng kế nhiệm.
    """
    rows = list(db.scalars(sa.select(GiongDoc)).all())
    return sorted(rows, key=lambda g: (not g.mac_dinh, g.created_at), reverse=False)


def lay(db: Session, giong_id: uuid.UUID) -> GiongDoc:
    row = db.get(GiongDoc, giong_id)
    if row is None:
        raise NotFound(f"Không tìm thấy giọng {giong_id}")
    return row


def giong_mac_dinh(db: Session) -> GiongDoc | None:
    """Giọng dùng khi video không chọn riêng. ``None`` khi bảng còn rỗng."""
    return db.scalar(sa.select(GiongDoc).where(GiongDoc.mac_dinh.is_(True)))


def tao(
    db: Session,
    *,
    ten: str,
    nguon: str,
    nha_cung_cap: str,
    ghi_chu: str = "",
    cat_tu_giay: float | None = None,
    cat_den_giay: float | None = None,
    co_file: bool = False,
) -> GiongDoc:
    """Tạo dòng giọng mới ở trạng thái ``dang_xu_ly``.

    Chỉ TẠO DÒNG — chuẩn hoá, gõ chữ, mã hoá và đọc thử chạy trong Celery
    (luật số 1 CLAUDE.md: cả chuỗi đó mất vài chục giây).
    """
    if nguon not in {n.value for n in NguonGiong}:
        raise ApiError(f"Nguồn giọng '{nguon}' không hợp lệ.")
    if nguon == NguonGiong.DUNG_SAN.value:
        raise ApiError("Giọng dựng sẵn chỉ đến từ danh sách nhà cung cấp, không thêm tay được.")
    if nguon in NGUON_CAN_FILE and not co_file:
        raise ApiError("Bạn chưa chọn file âm thanh cho giọng này.")
    if nguon == NguonGiong.CAT_TU_FILE.value:
        if cat_tu_giay is None or cat_den_giay is None or cat_den_giay <= cat_tu_giay:
            raise ApiError("Mốc cắt phải có cả điểm đầu và điểm cuối, và cuối phải sau đầu.")

    row = GiongDoc(
        ten=ten.strip() or "Giọng chưa đặt tên",
        nha_cung_cap=nha_cung_cap,
        ma_giong=None,
        model=None,
        ngon_ngu="vi",
        gioi_tinh="",
        nguon=nguon,
        ghi_chu=ghi_chu or None,
        trang_thai=TrangThaiGiong.DANG_XU_LY.value,
        canh_bao=[],
        cat_tu_giay=cat_tu_giay,
        cat_den_giay=cat_den_giay,
    )
    db.add(row)
    #: flush để có ``id`` ngay — router cần nó để ghi file tải lên vào đúng
    #: thư mục trước khi gửi task.
    db.flush()
    log.info("giong.tao", giong_id=str(row.id), nguon=nguon, nha=nha_cung_cap)
    return row


def luu_file_tai_len(giong_id: uuid.UUID, ten_file: str, noi_dung: bytes) -> Path:
    """Ghi file người dùng vừa tải lên vào thư mục của giọng.

    Ở service chứ không ở router: router chỉ được validate và gọi. Đường dẫn đi
    qua ``paths.py`` (luật số 3), đuôi file giữ nguyên để soi thư mục là biết
    file gốc là gì.
    """
    if not noi_dung:
        raise ApiError("File tải lên rỗng — chọn lại file khác.")
    dich = giong_tai_len(str(giong_id), Path(ten_file).suffix.lower())
    dich.write_bytes(noi_dung)
    log.info("giong.nhan_file", giong_id=str(giong_id), so_byte=len(noi_dung))
    return dich


def sua(
    db: Session,
    giong_id: uuid.UUID,
    *,
    ten: str | None = None,
    ghi_chu: str | None = None,
    mac_dinh: bool | None = None,
    mau_text: str | None = None,
) -> tuple[GiongDoc, bool]:
    """Sửa giọng. Trả ``(dòng, có cần dựng lại không)``.

    Chỉ ĐỔI CHỮ của đoạn mẫu mới phải dựng lại: bản ``codes.npz`` mã hoá theo
    chữ cũ, giữ nguyên là model clone đọc theo đúng chữ sai mà người dùng vừa
    sửa xong. Đổi tên hay ghi chú thì không đụng gì tới file.

    So sánh chữ MỚI với chữ CŨ chứ không coi "có gửi lên" là "đã đổi": giao
    diện gửi cả form mỗi lần Lưu, nên cách kia sẽ chạy lại Whisper mỗi lần
    người dùng sửa một dòng ghi chú.
    """
    row = lay(db, giong_id)

    if ten is not None and ten.strip():
        row.ten = ten.strip()
    if ghi_chu is not None:
        row.ghi_chu = ghi_chu or None

    can_dung_lai = False
    if mau_text is not None and mau_text.strip() != (row.mau_text or "").strip():
        row.mau_text = mau_text.strip()
        row.co_ma_hoa = False
        row.trang_thai = TrangThaiGiong.DANG_XU_LY.value
        row.loi = None
        can_dung_lai = True

    if mac_dinh:
        dat_mac_dinh(db, giong_id)

    db.flush()
    return row, can_dung_lai


def dat_mac_dinh(db: Session, giong_id: uuid.UUID) -> GiongDoc:
    """Chuyển cờ mặc định sang giọng này.

    Tắt cờ cũ rồi ``flush`` TRƯỚC khi bật cờ mới: chỉ số duy nhất một phần trên
    ``mac_dinh`` từ chối hai dòng ``true`` cùng lúc, nên gộp hai lệnh vào một
    lần ghi là ăn ``IntegrityError``.
    """
    row = lay(db, giong_id)
    if row.trang_thai != TrangThaiGiong.SAN_SANG.value:
        raise ApiError("Giọng này dựng chưa xong nên chưa đặt làm mặc định được.")

    db.execute(sa.update(GiongDoc).where(GiongDoc.mac_dinh.is_(True)).values(mac_dinh=False))
    db.flush()
    row.mac_dinh = True
    db.flush()
    log.info("giong.dat_mac_dinh", giong_id=str(giong_id))
    return row


def xoa(db: Session, giong_id: uuid.UUID) -> None:
    """Xoá một giọng. Giọng dựng sẵn thì không.

    Xoá giọng đang là mặc định thì chuyển mặc định sang giọng SẴN SÀNG cũ nhất
    còn lại. Để rỗng là mọi video sau đó không biết đọc bằng gì, và lỗi chỉ nổ
    ra ở worker giữa chừng pipeline.
    """
    row = lay(db, giong_id)
    if row.nguon == NguonGiong.DUNG_SAN.value:
        raise ApiError("Giọng dựng sẵn của nhà cung cấp thì không xoá được.")

    la_mac_dinh = row.mac_dinh
    db.delete(row)
    db.flush()

    if la_mac_dinh:
        con_lai = [g for g in danh_sach(db) if g.trang_thai == TrangThaiGiong.SAN_SANG.value]
        if con_lai:
            ke_nhiem = min(con_lai, key=lambda g: g.created_at)
            ke_nhiem.mac_dinh = True
            db.flush()
            log.info("giong.mac_dinh_chuyen", giong_id=str(ke_nhiem.id))
        else:
            log.warning("giong.khong_con_giong_nao_lam_mac_dinh")

    log.info("giong.xoa", giong_id=str(giong_id))
