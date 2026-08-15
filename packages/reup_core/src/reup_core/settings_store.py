"""Đọc/ghi cấu hình ứng dụng trong DB, thay cho biến trong ``.env``.

Vì sao tồn tại: file ``.env`` nằm cạnh mã nguồn nên chỉ cần một lần
``git add -A`` bất cẩn là khoá API lên GitHub. Chuyện đó suýt xảy ra ngày
2026-08-16 và chỉ được chặn lại nhờ bộ quét bí mật của GitHub.

BA THỨ KHÔNG CHUYỂN ĐƯỢC vào đây, vì chúng cần TRƯỚC khi chạm được DB:

    DATABASE_URL   dùng để tới chính bảng này
    REDIS_URL      worker cần lúc khởi động
    SETTINGS_KEY   khoá giải mã chính cột value_encrypted

Nói cách khác: chuyển vào DB không xoá được ``.env``, nó rút ``.env`` từ 34
biến xuống còn 3 — và trong 3 cái đó chỉ có 1 là bí mật thật.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting

#: Tên biến môi trường chứa khoá Fernet. Đây là bí mật DUY NHẤT còn phải nằm
#: ngoài DB.
ENV_KEY_MA_HOA = "SETTINGS_KEY"

#: Ba biến bootstrap — có mặt ở đây để chỗ khác biết mà KHÔNG đưa vào trang cấu
#: hình, chứ không phải để đọc.
KHOA_BOOTSTRAP = frozenset({"DATABASE_URL", "REDIS_URL", ENV_KEY_MA_HOA})

#: Khoá phải mã hoá trước khi lưu (luật số 6 CLAUDE.md). Danh sách TƯỜNG MINH
#: chứ không đoán theo tên: đoán theo hậu tố "_KEY" sẽ bỏ sót
#: ``TIKTOK_CLIENT_SECRET`` và bắt nhầm ``SETTINGS_KEY``.
KHOA_BI_MAT = frozenset(
    {
        "LLM_API_KEY",
        "TIKTOK_CLIENT_KEY",
        "TIKTOK_CLIENT_SECRET",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
    }
)

#: Giá trị trả ra thay cho bí mật. KHÔNG bao giờ trả giá trị thật qua API.
CHE = "••••••••"


@dataclass(frozen=True)
class MucCauHinh:
    """Một dòng cấu hình đã sẵn sàng hiển thị."""

    key: str
    value: str
    is_secret: bool
    #: True khi bí mật đã có giá trị — giao diện cần phân biệt "đã đặt" với
    #: "chưa đặt", mà không được biết giá trị.
    da_dat: bool


class KhoaMaHoaThieu(RuntimeError):
    """Chưa có ``SETTINGS_KEY`` nên không đọc/ghi được bí mật."""


def fernet():
    from cryptography.fernet import Fernet

    khoa = os.getenv(ENV_KEY_MA_HOA, "").strip()
    if not khoa:
        raise KhoaMaHoaThieu(
            f"Chưa có {ENV_KEY_MA_HOA} trong .env — không mã hoá được bí mật. "
            f"Sinh một khoá mới bằng: python -c "
            f'"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(khoa.encode())


def sinh_khoa() -> str:
    """Sinh một khoá Fernet mới để người dùng dán vào ``.env``."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


def la_bi_mat(key: str) -> bool:
    return key.upper() in KHOA_BI_MAT


def ghi(db: Session, key: str, value: str) -> AppSetting:
    """Ghi một dòng cấu hình. Tự mã hoá nếu khoá nằm trong danh sách bí mật.

    Giá trị RỖNG với một bí mật nghĩa là "giữ nguyên cái đang có", không phải
    "xoá đi": giao diện không bao giờ nhận được giá trị thật nên nó gửi lên
    chuỗi rỗng mỗi khi người dùng lưu mà không sửa ô đó.
    """
    key = key.upper()
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, is_secret=la_bi_mat(key))
        db.add(row)

    if row.is_secret:
        if not value:
            return row
        row.value_encrypted = fernet().encrypt(value.encode()).decode()
        row.value_plain = None
    else:
        row.value_plain = value
        row.value_encrypted = None

    db.flush()
    return row


def xoa(db: Session, key: str) -> None:
    """Xoá hẳn một dòng — khi đó hệ thống rơi về biến môi trường rồi mặc định."""
    row = db.get(AppSetting, key.upper())
    if row is not None:
        db.delete(row)
        db.flush()


def doc_tat_ca_that(db: Session) -> dict[str, str]:
    """Mọi cấu hình kèm GIÁ TRỊ THẬT, đã giải mã. Chỉ dùng trong tiến trình.

    KHÔNG được trả thẳng kết quả này qua API — dùng ``doc_de_hien`` cho việc đó.

    Bí mật giải mã hỏng (đổi ``SETTINGS_KEY`` mà quên nhập lại) thì BỎ QUA dòng
    đó chứ không ném lỗi: cả ứng dụng không được chết vì một khoá API sai, và
    hệ thống sẽ rơi về biến môi trường như trước.
    """
    ra: dict[str, str] = {}
    for row in db.scalars(select(AppSetting)):
        if not row.is_secret:
            if row.value_plain is not None:
                ra[row.key] = row.value_plain
            continue
        if not row.value_encrypted:
            continue
        try:
            ra[row.key] = fernet().decrypt(row.value_encrypted.encode()).decode()
        except Exception:
            continue
    return ra


def doc_de_hien(db: Session) -> list[MucCauHinh]:
    """Mọi cấu hình để HIỂN THỊ — bí mật luôn bị che."""
    ra: list[MucCauHinh] = []
    for row in db.scalars(select(AppSetting).order_by(AppSetting.key)):
        if row.is_secret:
            da_dat = bool(row.value_encrypted)
            ra.append(MucCauHinh(row.key, CHE if da_dat else "", True, da_dat))
        else:
            gia_tri = row.value_plain or ""
            ra.append(MucCauHinh(row.key, gia_tri, False, bool(gia_tri)))
    return ra


def nap_vao_moi_truong(db: Session) -> int:
    """Đổ cấu hình từ DB vào ``os.environ``, trả về số biến đã đặt.

    Đây là chỗ nối giữa DB và các lớp ``Settings`` của pydantic — chúng đọc từ
    biến môi trường, nên đổ vào đây là mọi thứ phía sau chạy nguyên như cũ,
    không phải sửa một dòng nào ở chỗ dùng.

    DB ĐÈ LÊN ``.env``: trang cấu hình là nơi người dùng vừa bấm Lưu, còn
    ``.env`` là giá trị cũ họ không nhìn thấy. Ưu tiên ngược lại sẽ khiến nút
    Lưu trông như không ăn.

    KHÔNG đụng tới ba biến bootstrap, kể cả khi DB có dòng trùng tên.
    """
    dem = 0
    for key, value in doc_tat_ca_that(db).items():
        if key in KHOA_BOOTSTRAP:
            continue
        os.environ[key] = value
        dem += 1
    return dem
