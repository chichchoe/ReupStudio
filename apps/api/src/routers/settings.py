"""Trang cấu hình — thay cho việc sửa tay file ``.env``.

Vì sao chuyển vào đây: ``.env`` nằm cạnh mã nguồn nên chỉ cần một lần
``git add -A`` bất cẩn là khoá API lên GitHub. Chuyện đó suýt xảy ra ngày
2026-08-16 và chỉ được chặn lại nhờ bộ quét bí mật của GitHub.

Bí mật KHÔNG BAO GIỜ đi ra khỏi API (luật số 6 CLAUDE.md): endpoint đọc trả về
chuỗi che, kèm cờ ``da_dat`` để giao diện phân biệt "đã có khoá" với "chưa có"
mà không cần biết giá trị.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from reup_core.settings_store import (
    KHOA_BI_MAT,
    KHOA_BOOTSTRAP,
    KhoaMaHoaThieu,
    doc_de_hien,
    ghi,
    sinh_khoa,
    xoa,
)
from sqlalchemy.orm import Session

from ..config import lam_moi_cau_hinh
from ..db import get_db
from ..errors import ApiError
from ..schemas.settings import (
    CauHinhOut,
    KetQuaCaiDatOut,
    KhoaMoiOut,
    MucCauHinhOut,
    NhomCauHinhOut,
    SuaCauHinhIn,
    ThongTinMayOut,
)
from ..services import he_thong

router = APIRouter(prefix="/settings", tags=["settings"])

#: Ô nào chỉ có vài giá trị hợp lệ thì cho CHỌN, không cho gõ tay. Gõ "smal"
#: thay vì "small" làm hỏng bước nhận dạng, mà lỗi chỉ hiện ra sau khi đã chờ
#: tải xong video.
LUA_CHON: dict[str, list[str]] = {
    "WHISPER_MODEL": ["tiny", "base", "small", "medium", "large-v3"],
    "WHISPER_DEVICE": ["auto", "cpu", "cuda"],
    "WHISPER_COMPUTE_TYPE": ["int8", "int8_float16", "float16", "float32"],
    "DEDUP_ENABLED": ["true", "false"],
    "SUB_MAX_LINES": ["1", "2", "3"],
    "YTDLP_COOKIES_FROM_BROWSER": ["", "chrome", "firefox", "edge", "safari"],
}

#: Ô số — giao diện hiện bàn phím số và chặn chữ ngay tại chỗ nhập.
KIEU_SO = {
    "LLM_BATCH_SIZE",
    "LLM_MAX_REQUESTS_PER_MIN",
    "LLM_MAX_REQUESTS_PER_DAY",
    "SUB_FONT_SIZE",
    "SUB_MAX_CHARS_PER_LINE",
    "SUB_MIN_DURATION",
    "DUB_ORIGINAL_VOLUME",
    "MONTHLY_BUDGET_USD",
    "MAX_CONCURRENT_RENDERS",
    "MAX_VIDEO_DURATION_SEC",
    "DOWNLOAD_TIMEOUT_SEC",
    "FFMPEG_TIMEOUT_SEC",
    "DEDUP_PHASH_FRAMES",
    "DEDUP_PHASH_MAX_DISTANCE",
    "DEDUP_PHASH_SCAN_LIMIT",
}


def _kieu_o(key: str) -> tuple[str, list[str]]:
    if key in LUA_CHON:
        return ("select", LUA_CHON[key])
    if key in KIEU_SO:
        return ("number", [])
    return ("text", [])


#: Gom theo nhóm và kèm mô tả để người dùng không phải đoán ý nghĩa từng biến.
#: Giữ nguyên tên biến làm khoá — đó vẫn là thứ ``.env`` và mã nguồn dùng.
#:
#: Sáu chặng của pipeline nằm CHUNG một mục "Xử lý video": tách thành sáu mục
#: riêng thì mỗi mục chỉ 2–5 ô, và sửa một video là phải nhảy qua bốn mục. Thứ
#: tự bên trong vẫn đi theo đúng thứ tự chạy — tải → nghe → dịch → phụ đề —
#: và mỗi chặng có một dòng phân cách, nên vẫn tìm được bằng mắt.
MUC_XU_LY = "Xử lý video"

#: ``(mục, phần, [(khoá, mô tả)])``. "Phần" chỉ là dòng phân cách bên trong
#: mục, không phải một mục riêng ở cột trái.
NHOM: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        MUC_XU_LY,
        "1 · Tải video",
        [
            ("YTDLP_COOKIES_FROM_BROWSER", "chrome · firefox · edge · safari"),
            ("YTDLP_COOKIE_FILE", "File cookie dạng Netscape — cách duy nhất chạy trong Docker"),
        ],
    ),
    (
        MUC_XU_LY,
        "2 · Nhận dạng giọng nói",
        [
            ("WHISPER_MODEL", "tiny · base · small · medium · large-v3"),
            ("WHISPER_DEVICE", "cuda · cpu · auto"),
            ("WHISPER_COMPUTE_TYPE", "int8_float16 cho GPU, int8 cho CPU"),
        ],
    ),
    (
        MUC_XU_LY,
        "3 · Dịch thuật",
        [
            #: Khoá và địa chỉ của từng nhà cung cấp KHÔNG nằm ở đây — chúng có
            #: mục riêng vì người dùng cấu hình nhiều bên cùng lúc.
            ("LLM_BATCH_SIZE", "Số câu gửi mỗi lượt gọi"),
            ("LLM_MAX_REQUESTS_PER_MIN", "Trần lượt/phút tự khai. 0 = không giới hạn"),
            ("LLM_MAX_REQUESTS_PER_DAY", "Trần lượt/ngày tự khai. 0 = không giới hạn"),
        ],
    ),
    (
        MUC_XU_LY,
        "4 · Phụ đề",
        [
            ("SUB_FONT", "Tên font"),
            ("SUB_FONT_SIZE", "Pixel ở khung chuẩn 1080×1920"),
            ("SUB_MAX_CHARS_PER_LINE", "Chữ to hơn thì số ký tự mỗi dòng phải nhỏ đi"),
            ("SUB_MAX_LINES", "Số dòng tối đa mỗi khung"),
            ("SUB_MIN_DURATION", "Giây tối thiểu mỗi khung phụ đề"),
        ],
    ),
    (
        MUC_XU_LY,
        "5 · Lồng tiếng",
        [
            (
                "DUB_ORIGINAL_VOLUME",
                "Mức âm gốc còn lại khi trộn giọng Việt. 0 = tắt hẳn tiếng gốc",
            ),
        ],
    ),
    (
        MUC_XU_LY,
        "Chống trùng",
        [
            ("DEDUP_ENABLED", "true · false"),
            ("DEDUP_PHASH_FRAMES", "Đổi số này là mọi pHash cũ hết so sánh được"),
            ("DEDUP_PHASH_MAX_DISTANCE", "Càng nhỏ càng chặt"),
            ("DEDUP_PHASH_SCAN_LIMIT", "Số video quét ngược khi so trùng"),
        ],
    ),
    (
        MUC_XU_LY,
        "Giới hạn an toàn",
        [
            ("MONTHLY_BUDGET_USD", "Trần chi tiêu tháng. 0 = không giới hạn"),
            ("MAX_CONCURRENT_RENDERS", "Số render chạy cùng lúc"),
            ("MAX_VIDEO_DURATION_SEC", "Video dài hơn mức này bị bỏ qua"),
            ("DOWNLOAD_TIMEOUT_SEC", "Timeout tải video"),
            ("FFMPEG_TIMEOUT_SEC", "Timeout mỗi lệnh ffmpeg"),
        ],
    ),
    (
        "Nền tảng đăng",
        "",
        [
            ("TIKTOK_CLIENT_KEY", "Lưu mã hoá"),
            ("TIKTOK_CLIENT_SECRET", "Lưu mã hoá"),
            ("YOUTUBE_CLIENT_ID", "Lưu mã hoá"),
            ("YOUTUBE_CLIENT_SECRET", "Lưu mã hoá"),
        ],
    ),
]


@router.get("", response_model=CauHinhOut)
def doc_cau_hinh(db: Session = Depends(get_db)):
    """Toàn bộ cấu hình, nhóm theo chủ đề. Bí mật luôn bị che."""
    da_luu = {m.key: m for m in doc_de_hien(db)}

    #: Nhiều "phần" cùng một "mục" thì dồn vào cùng một ``NhomCauHinhOut`` —
    #: cột trái chỉ hiện một dòng, phần chỉ là chỗ ngắt bên trong.
    theo_muc: dict[str, list[MucCauHinhOut]] = {}
    for ten, phan, cac_khoa in NHOM:
        for key, mo_ta in cac_khoa:
            row = da_luu.get(key)
            kieu, lua_chon = _kieu_o(key)
            theo_muc.setdefault(ten, []).append(
                MucCauHinhOut(
                    key=key,
                    mo_ta=mo_ta,
                    phan=phan,
                    kieu=kieu,
                    lua_chon=lua_chon,
                    value=row.value if row else "",
                    is_secret=key in KHOA_BI_MAT,
                    da_dat=bool(row and row.da_dat),
                )
            )

    nhom = [NhomCauHinhOut(ten=ten, muc=muc) for ten, muc in theo_muc.items()]

    return CauHinhOut(nhom=nhom, khoa_bootstrap=sorted(KHOA_BOOTSTRAP))


@router.put("", response_model=CauHinhOut)
def sua_cau_hinh(body: SuaCauHinhIn, db: Session = Depends(get_db)):
    """Lưu cấu hình.

    Ô bí mật để TRỐNG nghĩa là "giữ nguyên cái đang có", không phải "xoá đi" —
    giao diện không bao giờ nhận được giá trị thật nên nó luôn gửi lên chuỗi
    rỗng ở những ô người dùng không sửa.

    Ba biến bootstrap bị từ chối thẳng: ghi ``DATABASE_URL`` vào DB rồi đè lên
    biến đang dùng để tới DB thì lần khởi động sau không vào nổi database.
    """
    cham = [k for k in body.gia_tri if k.upper() in KHOA_BOOTSTRAP]
    if cham:
        raise ApiError(
            f"Không đổi được {', '.join(cham)} ở đây — chúng cần trước khi tới được "
            "database nên phải nằm trong .env."
        )

    try:
        for key, value in body.gia_tri.items():
            if value == "" and key.upper() not in KHOA_BI_MAT:
                xoa(db, key)
            else:
                ghi(db, key, value)
    except KhoaMaHoaThieu as exc:
        raise ApiError(str(exc)) from exc

    db.commit()
    #: Không có dòng này thì thay đổi chỉ có tác dụng sau khi khởi động lại.
    lam_moi_cau_hinh()
    return doc_cau_hinh(db)


@router.post("/sinh-khoa-ma-hoa", response_model=KhoaMoiOut)
def sinh_khoa_ma_hoa():
    """Sinh một khoá Fernet để người dùng dán vào ``.env``.

    KHÔNG tự ghi vào ``.env``: ghi hộ thì lần sau đổi khoá sẽ âm thầm làm mọi
    bí mật đang lưu không giải mã được nữa. Đây là thao tác một lần, và người
    dùng phải biết mình vừa đặt cái gì ở đâu.
    """
    return KhoaMoiOut(
        khoa=sinh_khoa(),
        huong_dan="Dán vào .env dòng SETTINGS_KEY=... rồi khởi động lại. "
        "Đổi khoá này sẽ làm mọi bí mật đang lưu không giải mã được nữa.",
    )


@router.get("/may", response_model=ThongTinMayOut)
def thong_tin_may(db: Session = Depends(get_db)):
    """Máy đang chạy là máy nào, và còn thiếu gì để chạy được."""
    return he_thong.kiem_tra_may(db)


@router.post("/cai-dat-nhanh", response_model=KetQuaCaiDatOut)
def cai_dat_nhanh(db: Session = Depends(get_db)):
    """Làm hộ những bước dựng máy mới mà API tự làm được."""
    return KetQuaCaiDatOut(da_lam=he_thong.cai_dat_nhanh(db))
