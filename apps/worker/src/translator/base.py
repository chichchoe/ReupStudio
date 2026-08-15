"""Lớp trừu tượng cho dịch thuật — đổi nhà cung cấp không đụng tới pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..config import get_settings


@dataclass
class LlmUsage:
    """Lượng đã dùng của MỘT lượt chạy dịch — token và số lượt gọi.

    Đo ngày 2026-08-14: Gemini KHÔNG trả header hạn mức nào, nên khối ``usage``
    trong thân phản hồi là nguyên liệu duy nhất để biết đã tiêu bao nhiêu.

    ``total_tokens`` lấy NGUYÊN VĂN từ nhà cung cấp, không cộng lại từ
    ``prompt + completion``: Gemini trả 9 + 0 = 26 vì token suy luận không nằm
    trong hai ô kia, cộng tay sẽ đếm hụt.

    ``requests`` đếm được cả khi nhà cung cấp không trả ``usage`` — và đó mới
    là con số chặn ta lại ở bậc miễn phí (trần tính theo lượt/phút).
    """

    model: str
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    #: Mốc thời gian từng lượt gọi, để đếm lượt/phút cho đúng thay vì gộp cuối.
    timestamps: list[float] = field(default_factory=list)

    def add(
        self,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        at: float | None = None,
    ) -> None:
        import time

        self.requests += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += total_tokens
        self.timestamps.append(at if at is not None else time.time())


class BaseTranslator(ABC):
    def __init__(self, model: str | None = None, *, api_key: str = "", base_url: str = "") -> None:
        #: Khoá và địa chỉ của RIÊNG lượt chạy này, lấy từ nhà cung cấp người
        #: dùng chọn ở tab "Chờ dịch" (bảng ``ai_providers``). Rỗng thì rơi về
        #: cấu hình chung — giữ cho video cũ, lưu trước khi có nhiều nhà cung
        #: cấp, vẫn chạy được.
        self.api_key = api_key
        self.base_url = base_url
        #: Model của RIÊNG lượt chạy này. Người dùng chọn model cho từng video
        #: ở tab "Chờ dịch" (lưu vào ``process_config["llm_model"]``), nên không
        #: thể đọc thẳng ``settings.llm_model`` ở mọi nơi — đó chỉ là mặc định
        #: khi người dùng chưa chọn.
        self.model = model or get_settings().llm_model
        self.usage = LlmUsage(model=self.model)
        #: Gọi sau MỖI lượt gọi HTTP, không phải mỗi lô. Tầng ``tasks/`` gắn
        #: vào để ghi ``cost_logs``. Một lô lệch số dòng nở ra nhiều lượt gọi
        #: (chia đôi, rồi dịch từng dòng) — đo thật 2026-08-14: 4 lô sinh 189
        #: lượt gọi. Báo theo lô làm sổ chi phí hụt gần 50 lần, và bộ giãn nhịp
        #: đọc từ bảng đó nên không kích hoạt lần nào dù liên tục bị từ chối.
        self.on_usage = None

    def _bao_usage(self) -> None:
        """Báo cho chỗ gọi biết vừa tốn thêm một lượt. An toàn khi chưa gắn."""
        if self.on_usage is not None:
            self.on_usage(self.usage)

    @abstractmethod
    def translate_batch(
        self, texts: list[str], *, tone: str, glossary: dict[str, str]
    ) -> list[str]:
        """Dịch một lô câu, TRẢ VỀ ĐÚNG SỐ PHẦN TỬ như đầu vào."""

    @abstractmethod
    def generate_title(self, transcript: str, *, count: int = 5) -> list[str]:
        """Sinh tiêu đề tiếng Việt hấp dẫn từ nội dung video."""


def get_translator(
    model: str | None = None, *, api_key: str = "", base_url: str = "", provider: str = ""
) -> BaseTranslator:
    """Tạo translator theo nhà cung cấp đã cấu hình.

    ``model``, ``api_key``, ``base_url`` là lựa chọn của RIÊNG video đang xử lý
    (người dùng chọn nhà cung cấp và model ở tab "Chờ dịch"). Không truyền thì
    dùng cấu hình chung.

    Anthropic nói giao thức riêng nên có lớp riêng; mọi bên còn lại — Gemini,
    OpenRouter, DeepSeek, Ollama — đều tương thích OpenAI nên dùng chung một
    lớp, chỉ khác địa chỉ gốc.
    """
    provider = (provider or get_settings().llm_provider).lower()
    if provider == "anthropic":
        from .anthropic import AnthropicTranslator

        return AnthropicTranslator(model, api_key=api_key, base_url=base_url)
    if provider == "openai":
        from .openai import OpenAITranslator

        return OpenAITranslator(model, api_key=api_key, base_url=base_url)
    #: Có khoá thì chắc chắn KHÔNG phải mock — người dùng vừa dán khoá thật ở
    #: trang cấu hình, rơi về mock ở đây sẽ cho ra bản dịch giả mà vẫn báo xong.
    if api_key:
        from .openai import OpenAITranslator

        return OpenAITranslator(model, api_key=api_key, base_url=base_url)

    from .mock import MockTranslator

    return MockTranslator(model)
