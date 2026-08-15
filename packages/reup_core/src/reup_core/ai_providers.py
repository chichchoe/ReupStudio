"""Danh mục nhà cung cấp AI và cách hỏi họ có model gì.

Người dùng cấu hình nhiều bên cùng lúc rồi chọn bên nào cho từng video. Mỗi bên
chỉ cần DÁN KHOÁ; địa chỉ gốc và cách liệt kê model đã biết sẵn ở đây.

Bốn trong năm bên nói cùng một giao thức (``GET /models`` với header
``Authorization: Bearer``) vì đều tương thích OpenAI. Anthropic là ngoại lệ:
dùng header ``x-api-key`` kèm ``anthropic-version``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NhaCungCap:
    ma: str
    ten: str
    base_url: str
    #: Nơi lấy khoá, hiện trên giao diện để người dùng khỏi đi tìm.
    trang_lay_khoa: str
    ghi_chu: str = ""
    #: Anthropic dùng header riêng — xem ``_header``.
    kieu_xac_thuc: str = "bearer"
    #: Đường dẫn liệt kê model, nối sau ``base_url``.
    duong_dan_models: str = "/models"
    #: Model gợi ý khi chưa hỏi được danh sách (mạng hỏng, khoá sai).
    model_goi_y: list[str] = field(default_factory=list)


DANH_MUC: dict[str, NhaCungCap] = {
    "gemini": NhaCungCap(
        ma="gemini",
        ten="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        trang_lay_khoa="https://aistudio.google.com/apikey",
        ghi_chu="Có bậc miễn phí, không cần thẻ. Cũng là bên DUY NHẤT ở đây có TTS.",
        model_goi_y=["gemini-3.5-flash-lite", "gemini-2.5-flash"],
    ),
    "openrouter": NhaCungCap(
        ma="openrouter",
        ten="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        trang_lay_khoa="https://openrouter.ai/keys",
        ghi_chu="Một khoá dùng được model của nhiều hãng. Không có TTS.",
        model_goi_y=["deepseek/deepseek-chat", "google/gemini-flash-1.5"],
    ),
    "anthropic": NhaCungCap(
        ma="anthropic",
        ten="Anthropic Claude",
        base_url="https://api.anthropic.com/v1",
        trang_lay_khoa="https://console.anthropic.com/settings/keys",
        ghi_chu="Dịch sát nghĩa, hợp thoại phim. Trả phí, không có bậc miễn phí.",
        kieu_xac_thuc="x-api-key",
        model_goi_y=["claude-sonnet-5", "claude-haiku-4-5-20251001"],
    ),
    "deepseek": NhaCungCap(
        ma="deepseek",
        ten="DeepSeek",
        base_url="https://api.deepseek.com",
        trang_lay_khoa="https://platform.deepseek.com/api_keys",
        ghi_chu="Rẻ, dịch Trung–Việt tốt vì là model Trung Quốc.",
        model_goi_y=["deepseek-chat"],
    ),
    "openai": NhaCungCap(
        ma="openai",
        ten="OpenAI",
        base_url="https://api.openai.com/v1",
        trang_lay_khoa="https://platform.openai.com/api-keys",
        model_goi_y=["gpt-4o-mini"],
    ),
    "ollama": NhaCungCap(
        ma="ollama",
        ten="Ollama (chạy tại máy)",
        base_url="http://localhost:11434/v1",
        trang_lay_khoa="",
        ghi_chu="Không cần khoá, không tính tiền, không giới hạn. Chậm hơn.",
        model_goi_y=["qwen2.5:7b"],
    ),
}


def _header(nha: NhaCungCap, api_key: str) -> dict[str, str]:
    if nha.kieu_xac_thuc == "x-api-key":
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {api_key}"}


def che_khoa(text: str, api_key: str) -> str:
    """Không bao giờ để khoá lọt vào log hay thông báo lỗi (luật số 6)."""
    return text.replace(api_key, "***") if api_key else text


def hoi_danh_sach_model(
    ma: str, api_key: str, base_url: str = "", *, timeout: int = 20
) -> list[str]:
    """Hỏi thẳng nhà cung cấp xem khoá này dùng được model nào.

    Hỏi TRỰC TIẾP thay vì để người dùng gõ tay tên model: gõ sai một ký tự thì
    lỗi chỉ hiện ra lúc dịch, sau khi đã chờ tải và nhận dạng xong.

    Lỗi mạng hay khoá sai thì ném ``ValueError`` với thông báo ĐÃ CHE KHOÁ —
    chỗ gọi bắt và hiện lên giao diện.
    """
    nha = DANH_MUC.get(ma)
    if nha is None:
        raise ValueError(f"Không biết nhà cung cấp '{ma}'")

    goc = (base_url or nha.base_url).rstrip("/")
    req = urllib.request.Request(
        f"{goc}{nha.duong_dan_models}",
        headers={"Accept": "application/json", **_header(nha, api_key)},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as exc:
        than = exc.read().decode("utf-8", "replace")[:200]
        raise ValueError(f"HTTP {exc.code}: {che_khoa(than, api_key)}") from exc
    except Exception as exc:
        raise ValueError(che_khoa(str(exc), api_key)) from exc

    return _lay_ten_model(data)


def _lay_ten_model(data: object) -> list[str]:
    """Rút tên model từ nhiều hình dạng JSON khác nhau.

    OpenAI và tương thích trả ``{"data": [{"id": ...}]}``; Anthropic cũng vậy
    nhưng đôi khi kèm ``display_name``. Chấp nhận cả ``{"models": [...]}`` để
    không vỡ khi một bên đổi hình dạng.
    """
    if isinstance(data, dict):
        muc = data.get("data") or data.get("models") or []
    elif isinstance(data, list):
        muc = data
    else:
        return []

    ra: list[str] = []
    for m in muc:
        if isinstance(m, str):
            ra.append(m)
        elif isinstance(m, dict):
            ten = m.get("id") or m.get("name") or m.get("model")
            if ten:
                #: Gemini trả về "models/gemini-..." — bỏ tiền tố cho gọn.
                ra.append(str(ten).removeprefix("models/"))
    return sorted(set(ra))
