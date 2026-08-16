"""Cấu hình nhà cung cấp AI: lưu khoá, hỏi danh sách model.

Khoá mã hoá bằng cùng cơ chế với ``app_settings`` (luật số 6 CLAUDE.md) và
KHÔNG BAO GIỜ ra khỏi API — endpoint đọc chỉ trả cờ "đã đặt khoá hay chưa".
"""

from __future__ import annotations

from typing import Any

from reup_core.ai_providers import DANH_MUC, hoi_model_chi_tiet
from reup_core.llm_models import ModelPurpose, phan_loai
from reup_core.models import AiProvider
from reup_core.settings_store import fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ApiError, NotFound


def danh_sach(db: Session) -> list[dict[str, Any]]:
    """Mọi nhà cung cấp trong danh mục, kèm trạng thái đã cấu hình hay chưa."""
    da_luu = {r.ma: r for r in db.scalars(select(AiProvider))}

    ra: list[dict[str, Any]] = []
    for ma, nha in DANH_MUC.items():
        row = da_luu.get(ma)
        ra.append(
            {
                "ma": ma,
                "ten": nha.ten,
                "ghi_chu": nha.ghi_chu,
                "trang_lay_khoa": nha.trang_lay_khoa,
                "base_url_mac_dinh": nha.base_url,
                "base_url": (row.base_url if row else "") or "",
                #: Ollama chạy tại máy, không cần khoá — nếu không thì giao diện
                #: hiện "chưa đặt khoá" mãi mãi cho một thứ vốn không có khoá.
                "can_khoa": ma != "ollama",
                "da_dat_khoa": bool(row and row.api_key_encrypted),
                "enabled": bool(row.enabled) if row else False,
                "model_goi_y": nha.model_goi_y,
            }
        )
    return ra


def luu(
    db: Session, ma: str, *, api_key: str | None, base_url: str | None, enabled: bool
) -> AiProvider:
    """Lưu cấu hình một nhà cung cấp.

    ``api_key`` rỗng nghĩa là GIỮ NGUYÊN khoá đang có, không phải xoá: giao
    diện không bao giờ nhận được khoá thật nên nó luôn gửi chuỗi rỗng ở ô người
    dùng không sửa.
    """
    if ma not in DANH_MUC:
        raise NotFound(f"Không biết nhà cung cấp '{ma}'")

    row = db.get(AiProvider, ma)
    if row is None:
        row = AiProvider(ma=ma)
        db.add(row)

    if api_key:
        row.api_key_encrypted = fernet().encrypt(api_key.encode()).decode()
    row.base_url = (base_url or "").strip() or None
    row.enabled = enabled

    db.flush()
    return row


def xoa_khoa(db: Session, ma: str) -> None:
    """Gỡ khoá của một nhà cung cấp — dùng khi đổi tài khoản hoặc nghi lộ khoá."""
    row = db.get(AiProvider, ma)
    if row is not None:
        row.api_key_encrypted = None
        row.enabled = False
        db.flush()


def lay_khoa(db: Session, ma: str) -> str:
    """Khoá đã giải mã. CHỈ dùng trong tiến trình, không trả ra API."""
    row = db.get(AiProvider, ma)
    if row is None or not row.api_key_encrypted:
        return ""
    try:
        return fernet().decrypt(row.api_key_encrypted.encode()).decode()
    except Exception:
        #: Đổi SETTINGS_KEY mà quên nhập lại khoá — coi như chưa cấu hình, chứ
        #: không làm sập cả trang.
        return ""


def models(db: Session, ma: str, muc_dich: str = "translate") -> list[str]:
    """Hỏi thẳng nhà cung cấp xem khoá này dùng được model nào, rồi LỌC theo việc.

    Hỏi trực tiếp thay vì để người dùng gõ tay: gõ sai một ký tự thì lỗi chỉ
    hiện ra lúc dịch, sau khi đã chờ tải và nhận dạng xong.
    """
    if ma not in DANH_MUC:
        raise NotFound(f"Không biết nhà cung cấp '{ma}'")

    row = db.get(AiProvider, ma)
    khoa = lay_khoa(db, ma)
    if DANH_MUC[ma].ma != "ollama" and not khoa:
        raise ApiError(f"Chưa dán khoá cho {DANH_MUC[ma].ten}.")

    try:
        #: Hỏi bản CHI TIẾT để lấy cả phần nhà cung cấp khai về khả năng model.
        #: Đoán qua tên là quy tắc đẻ ra từ danh mục Gemini; OpenRouter khai rõ
        #: ``output_modalities`` nên đoán tên ở đó vừa thừa vừa sai.
        chi_tiet = hoi_model_chi_tiet(ma, khoa, (row.base_url if row else "") or "")
    except ValueError as exc:
        raise ApiError(f"Không hỏi được danh sách model: {exc}") from exc

    tat_ca = [m.ma for m in chi_tiet]
    dich = ModelPurpose(muc_dich) if muc_dich in {"translate", "tts"} else ModelPurpose.TRANSLATE
    loc = [m.ma for m in chi_tiet if phan_loai(m.ma, dau_ra=m.dau_ra) is dich]

    #: Lọc rỗng thì XỬ LÝ KHÁC NHAU tuỳ việc, không dùng chung một đường lui.
    #:
    #: Dịch: trả nguyên danh sách. Bộ phân loại dựa trên tên, mà nhà cung cấp
    #: mới có thể đặt tên theo kiểu nó chưa biết; một model văn bản lạ thường
    #: vẫn dịch được, thà hiện thừa còn hơn hiện ô rỗng.
    #:
    #: Giọng đọc: TRẢ RỖNG. Một model văn bản không bao giờ đọc thành tiếng
    #: được, nên đường lui kia biến "bên này không có model đọc tiếng" thành
    #: "đây, 413 giọng cho bạn chọn". Chọn phải một cái là bước lồng tiếng
    #: hỏng — đúng kiểu hỏng vừa làm mất trắng một video.
    if dich is ModelPurpose.TTS:
        return loc
    return loc or tat_ca
