"""Danh sách model LLM mà khoá hiện tại dùng được, đã lọc theo mục đích.

KHÔNG biết gì về HTTP/FastAPI (chỉ ném lỗi nghiệp vụ trong ``errors.py``) —
tầng router lo việc dịch lỗi thành status code.

Vì sao phải hỏi nhà cung cấp thay vì ghi cứng một danh sách: mỗi khoá được cấp
một bộ model khác nhau, và danh sách đổi liên tục (đã đổi hai lần trong một
tháng). Ghi cứng thì hoặc mời người dùng chọn model họ không có quyền dùng,
hoặc giấu mất model mới.

Việc lọc dùng ``reup_core.llm_models`` — hàm thuần, đã có test riêng. Ở đây chỉ
lo phần bẩn: gọi mạng, cache và báo lỗi cho tử tế.

Ngoại lệ có chủ ý với luật số 1 CLAUDE.md ("chạm mạng ngoài phải qua Celery"):
đây là một lượt GET vài chục KB dùng để đổ ô chọn, người dùng phải thấy kết quả
NGAY khi mở ô. Đẩy qua Celery thì frontend phải hỏi vòng lấy kết quả cho một
việc đáng lẽ tức thì. Bù lại phải chặn chặt hai đầu: hạn chờ ngắn
(``_TIMEOUT_SEC``) và cache 5 phút để không bao giờ gọi dồn.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from reup_core.llm_models import ModelPurpose, loc_theo_muc_dich
from reup_core.logging import get_logger

from ..config import get_settings
from ..errors import LlmAuthFailed, LlmUnavailable

log = get_logger(__name__)

#: Danh sách model gần như không đổi trong ngày. 5 phút đủ để mở ô chọn nhiều
#: lần mà chỉ tốn một lượt gọi, vẫn đủ ngắn để người vừa được cấp model mới
#: không phải khởi động lại API.
CACHE_TTL_SEC = 300

#: Ngắn hơn hạn chờ khi dịch (120s) rất nhiều: đây là lượt gọi CHẶN người dùng
#: đang chờ ô chọn hiện ra. Chờ 10 giây rồi báo "không gọi được" còn tử tế hơn
#: để họ nhìn vòng xoay cả phút.
_TIMEOUT_SEC = 10

#: Đủ đọc thông báo lỗi của nhà cung cấp (VD "API key not valid") nhưng không
#: đổ nguyên trang HTML của proxy vào thông báo lỗi.
_ERROR_BODY_CHARS = 400

#: Mã báo khoá không dùng được. Gọi lại bao nhiêu lần cũng hỏng y hệt nên phải
#: tách khỏi lỗi tạm thời, để frontend dẫn người dùng đi sửa cấu hình.
_AUTH_STATUS = frozenset({401, 403})


@dataclass(frozen=True)
class DanhSachModel:
    """Model dùng được, chia theo mục đích. Id đã bỏ tiền tố ``models/``."""

    translate: list[str]
    tts: list[str]
    #: Model cấu hình sẵn (``LLM_MODEL``) nếu khoá hiện tại dùng được nó.
    default: str = ""


#: Cache theo ĐỊA CHỈ nhà cung cấp: đổi ``LLM_BASE_URL`` mà vẫn trả danh sách
#: của bên cũ thì người dùng chọn phải model không tồn tại. Cố ý KHÔNG đưa khoá
#: API vào khoá cache — không giữ bí mật trong bộ nhớ lâu hơn mức cần thiết.
_cache: dict[str, tuple[float, DanhSachModel]] = {}


def _bay_gio() -> float:
    """Đồng hồ đơn điệu — tách hàm để test tua thời gian mà không phải chờ thật.

    Dùng ``monotonic`` chứ không ``time.time``: chỉnh giờ hệ thống hoặc lệch NTP
    không được làm cache sống mãi hay hết hạn tức thì.
    """
    return time.monotonic()


def models_url(base_url: str) -> str:
    """Ghép địa chỉ ``/models`` từ địa chỉ gốc.

    ``rstrip`` vì địa chỉ Gemini trong tài liệu chính thức có ``/`` ở cuối; dán
    nguyên vào ``.env`` mà ghép thẳng sẽ ra ``//models`` và nhận 404.
    """
    return f"{base_url.rstrip('/')}/models"


def _che_khoa(text: str, api_key: str) -> str:
    """Không bao giờ để khoá API lọt vào thông báo lỗi hay log.

    Nhiều nhà cung cấp chèn nguyên URL kèm ``?key=...`` vào thân lỗi; bê thẳng
    ra là rò khoá cho cả người dùng cuối lẫn file log.
    """
    if not api_key:
        return text
    return text.replace(api_key, "***")


def _bo_tien_to(model_id: str) -> str:
    """``models/gemini-3.5-flash-lite`` -> ``gemini-3.5-flash-lite``.

    Phần đầu không phải tên model; dán nguyên vào ``LLM_MODEL`` thì lượt gọi
    dịch hỏng.
    """
    return model_id.strip().removeprefix("models/")


def _doc_id_model(payload: object) -> list[str]:
    """Rút id model từ thân JSON, chấp nhận cả hai hình dạng đang gặp thật.

    - Tương thích OpenAI: ``{"data": [{"id": ...}]}``
    - Gemini bản gốc:     ``{"models": [{"name": ...}]}``

    Nhận cả hai vì cắm ``LLM_BASE_URL`` vào ``/v1beta`` thay vì
    ``/v1beta/openai`` là nhầm lẫn rất dễ xảy ra, và hỏng vì lý do đó thì thông
    báo lỗi chẳng giúp được gì.
    """
    if not isinstance(payload, dict):
        return []

    muc = payload.get("data") or payload.get("models") or []
    if not isinstance(muc, list):
        return []

    ids: list[str] = []
    for item in muc:
        # Ollama và vài bản tương thích trả thẳng danh sách chuỗi, không bọc object.
        ten = (item.get("id") or item.get("name")) if isinstance(item, dict) else item
        if isinstance(ten, str) and ten.strip():
            ids.append(ten)
    return ids


def _tai_danh_sach_id(base_url: str, api_key: str) -> list[str]:
    """Hỏi nhà cung cấp toàn bộ id model. Hỏng thì NÉM, không trả danh sách rỗng."""
    url = models_url(base_url)
    try:
        with httpx.Client(timeout=_TIMEOUT_SEC) as client:
            response = client.get(url, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError as exc:
        raise LlmUnavailable(
            f"Không gọi được nhà cung cấp LLM ({url}): {_che_khoa(str(exc), api_key)}. "
            "Kiểm tra mạng và LLM_BASE_URL."
        ) from exc

    status = response.status_code
    if status >= 400:
        chi_tiet = _che_khoa(_than_loi(response), api_key)
        if status in _AUTH_STATUS:
            raise LlmAuthFailed(
                f"Nhà cung cấp LLM từ chối khoá (HTTP {status}). Kiểm tra LLM_API_KEY "
                f"còn hạn và có quyền dùng {url}. Chi tiết: {chi_tiet}"
            )
        raise LlmUnavailable(f"Nhà cung cấp LLM trả HTTP {status} từ {url}. Chi tiết: {chi_tiet}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise LlmUnavailable(
            f"Nhà cung cấp LLM trả về thân không phải JSON từ {url} — thường là proxy "
            "hoặc trang đăng nhập chắn giữa. Kiểm tra LLM_BASE_URL."
        ) from exc

    ids = _doc_id_model(payload)
    if not ids:
        raise LlmUnavailable(
            f"Nhà cung cấp LLM không trả model nào từ {url}. Thường là khoá chưa bật "
            "quyền dùng API hoặc trỏ nhầm dự án — không phải chuyện bình thường."
        )
    return ids


def _than_loi(response) -> str:
    """Phần thân lỗi ngắn gọn, đủ để người dùng tự sửa cấu hình."""
    try:
        return str(response.json())[:_ERROR_BODY_CHARS]
    except ValueError:
        return str(getattr(response, "text", ""))[:_ERROR_BODY_CHARS]


def xoa_cache() -> None:
    """Quên danh sách đã nhớ. Dùng trong test và khi cấu hình LLM vừa đổi."""
    _cache.clear()


def liet_ke_models() -> DanhSachModel:
    """Model dùng được với khoá hiện tại, chia thành nhóm dịch và nhóm giọng nói.

    Ném ``LlmAuthFailed`` khi chưa có khoá hoặc khoá bị từ chối,
    ``LlmUnavailable`` khi không hỏi được nhà cung cấp. TUYỆT ĐỐI không nuốt
    lỗi rồi trả danh sách rỗng: người dùng sẽ thấy ô chọn trống và tưởng khoá
    của mình không có model nào, trong khi lỗi nằm ở chỗ khác hẳn.

    Nhóm rỗng CÓ THỂ là kết quả hợp lệ (khoá chỉ được cấp model sinh ảnh) —
    khác hẳn với ca nhà cung cấp không trả model nào, đã bị chặn ở
    ``_tai_danh_sach_id``.
    """
    settings = get_settings()
    if not settings.llm_api_key:
        raise LlmAuthFailed(
            "Chưa cấu hình LLM_API_KEY nên không hỏi được nhà cung cấp có những model nào."
        )

    base_url = settings.llm_base_url
    da_nho = _cache.get(base_url)
    if da_nho is not None and (_bay_gio() - da_nho[0]) < CACHE_TTL_SEC:
        return da_nho[1]

    ids = _tai_danh_sach_id(base_url, settings.llm_api_key)
    dich = [_bo_tien_to(m) for m in loc_theo_muc_dich(ids, ModelPurpose.TRANSLATE)]
    #: Model cấu hình sẵn, để giao diện chọn sẵn trong ô chọn. Trả rỗng nếu nó
    #: không nằm trong danh sách khoá hiện tại dùng được — thà để giao diện tự
    #: chọn còn hơn chọn sẵn một model gọi là hỏng.
    mac_dinh = _bo_tien_to(settings.llm_model or "")
    ket_qua = DanhSachModel(
        translate=dich,
        tts=[_bo_tien_to(m) for m in loc_theo_muc_dich(ids, ModelPurpose.TTS)],
        default=mac_dinh if mac_dinh in dich else "",
    )

    # Chỉ nhớ kết quả TỐT: lỗi mạng chốc lát mà ghim 5 phút thì người dùng bấm
    # thử lại vẫn thấy hỏng, không hiểu vì sao.
    _cache[base_url] = (_bay_gio(), ket_qua)
    log.info(
        "llm.models.loaded",
        base_url=base_url,
        tong=len(ids),
        so_dich=len(ket_qua.translate),
        so_tts=len(ket_qua.tts),
    )
    return ket_qua
