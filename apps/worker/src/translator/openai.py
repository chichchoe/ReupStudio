"""Dịch qua API tương thích OpenAI.

Không chỉ riêng OpenAI: Gemini, Groq, OpenRouter, DeepSeek và Ollama đều nói
đúng giao thức ``/chat/completions`` này. Đổi nhà cung cấp chỉ tốn ba dòng
``.env`` — ``LLM_BASE_URL``, ``LLM_MODEL``, ``LLM_API_KEY`` — không sửa code,
không thêm thư viện (module này dùng ``httpx`` trần, không SDK).

Có retry cho lỗi tạm thời vì các bậc miễn phí chặn theo phút (Gemini ~10–15
lượt/phút, Groq 6.000 token/phút): một video dài chia thành nhiều lô dịch chắc
chắn sẽ đụng trần giữa chừng, và hỏng cả job vì một lần bị từ chối tạm thời là
lãng phí toàn bộ công đã làm trước đó.
"""

from __future__ import annotations

import time

import httpx

from ..config import get_settings
from ..errors import TranslateError
from ._json import extract_json_array
from .base import BaseTranslator
from .prompts import SYSTEM_PROMPT, TITLE_PROMPT, build_user_prompt

#: Cho phép test thay bằng hàm không thật sự ngủ.
_sleep = time.sleep

_TIMEOUT_SEC = 120
#: Số lần gọi LẠI (tổng số lượt gọi tối đa = con số này + 1).
_MAX_RETRIES = 4
#: Chờ 2s, 4s, 8s, 16s. Trần bậc miễn phí tính theo phút nên chờ tăng dần là
#: cách rẻ nhất để vượt qua, thay vì nện liên tiếp và ăn thêm lượt từ chối.
_BACKOFF_BASE_SEC = 2.0
#: Chỉ những mã này mới đáng gọi lại. 400/401/404 (sai model, sai key) thì gọi
#: lại bao nhiêu lần cũng hỏng y hệt — báo ngay cho người dùng sửa cấu hình.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
#: Giữ đủ để đọc thông báo lỗi của nhà cung cấp (VD "model not found") nhưng
#: không đổ cả trang HTML vào log.
_ERROR_BODY_CHARS = 400


def chat_url(base_url: str) -> str:
    """Ghép địa chỉ ``/chat/completions`` từ địa chỉ gốc.

    Địa chỉ Gemini trong tài liệu chính thức có dấu ``/`` ở cuối; dán nguyên
    vào ``.env`` mà ghép thẳng sẽ ra ``//chat/completions``.
    """
    return f"{base_url.rstrip('/')}/chat/completions"


def _thoi_gian_cho(response, lan_thu: int) -> float:
    """Giây cần chờ trước khi gọi lại — ưu tiên con số nhà cung cấp đưa ra."""
    retry_after = (getattr(response, "headers", None) or {}).get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return _BACKOFF_BASE_SEC * (2**lan_thu)


def _mo_ta_loi(response, status: int, lan_thu: int, url: str) -> str:
    """Thông báo lỗi đủ để người dùng tự sửa cấu hình, không phải đoán."""
    try:
        chi_tiet = str(response.json())[:_ERROR_BODY_CHARS]
    except Exception:  # noqa: BLE001 - thân lỗi không phải JSON cũng vẫn hữu ích
        chi_tiet = str(getattr(response, "text", ""))[:_ERROR_BODY_CHARS]

    if status == 429:
        return (
            f"LLM trả 429 (quá hạn mức) sau {lan_thu + 1} lượt gọi tới {url}. "
            "Bậc miễn phí chặn theo phút — giảm LLM_BATCH_SIZE hoặc đợi rồi chạy lại. "
            f"Chi tiết: {chi_tiet}"
        )
    return f"LLM trả HTTP {status} từ {url}. Chi tiết: {chi_tiet}"


class OpenAITranslator(BaseTranslator):
    def _ghi_usage(self, data: dict) -> None:
        """Cộng dồn lượng đã dùng của lượt gọi vừa xong.

        Nhà cung cấp không trả ``usage`` (một số bản tương thích OpenAI bỏ
        trống) thì vẫn phải đếm ĐƯỢC SỐ LƯỢT — ở bậc miễn phí, trần lượt/phút
        mới là thứ chặn ta lại, không phải token.
        """
        usage = data.get("usage") or {}
        self.usage.add(
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            #: Nguyên văn, KHÔNG cộng lại từ prompt + completion — xem LlmUsage.
            total_tokens=int(usage.get("total_tokens") or 0),
        )

    def _call(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        settings = get_settings()
        if not settings.llm_api_key:
            raise TranslateError("Chưa cấu hình LLM_API_KEY")

        url = chat_url(settings.llm_base_url)
        payload = {
            "model": self.model,
            "temperature": 0.3,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

        def che_khoa(text: str) -> str:
            """Không bao giờ để khoá API lọt vào thông báo lỗi hay log."""
            return text.replace(settings.llm_api_key, "***")

        for lan_thu in range(_MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=_TIMEOUT_SEC) as client:
                    response = client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                raise TranslateError(f"Không gọi được LLM ({url}): {che_khoa(str(exc))}") from exc

            status = getattr(response, "status_code", 200)
            if status < 400:
                data = response.json()
                self._ghi_usage(data)
                return data["choices"][0]["message"]["content"]

            con_thu_duoc = status in _RETRY_STATUS and lan_thu < _MAX_RETRIES
            if not con_thu_duoc:
                raise TranslateError(che_khoa(_mo_ta_loi(response, status, lan_thu, url)))

            _sleep(_thoi_gian_cho(response, lan_thu))

        raise TranslateError("Không gọi được LLM")  # pragma: no cover - vòng lặp luôn thoát

    def translate_batch(
        self, texts: list[str], *, tone: str, glossary: dict[str, str]
    ) -> list[str]:
        raw = self._call(SYSTEM_PROMPT, build_user_prompt(texts, tone, glossary))
        result = extract_json_array(raw)
        if result is None:
            raise TranslateError(f"LLM không trả về JSON hợp lệ: {raw[:300]}")
        return result

    def generate_title(self, transcript: str, *, count: int = 5) -> list[str]:
        raw = self._call(
            "Bạn là người viết tiêu đề video ngắn cho thị trường Việt Nam.",
            TITLE_PROMPT.format(count=count, transcript=transcript[:3000]),
            max_tokens=1024,
        )
        return extract_json_array(raw) or []
