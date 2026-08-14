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
    def __init__(self, model: str | None = None) -> None:
        #: Model của RIÊNG lượt chạy này. Người dùng chọn model cho từng video
        #: ở tab "Chờ dịch" (lưu vào ``process_config["llm_model"]``), nên không
        #: thể đọc thẳng ``settings.llm_model`` ở mọi nơi — đó chỉ là mặc định
        #: khi người dùng chưa chọn.
        self.model = model or get_settings().llm_model
        self.usage = LlmUsage(model=self.model)

    @abstractmethod
    def translate_batch(
        self, texts: list[str], *, tone: str, glossary: dict[str, str]
    ) -> list[str]:
        """Dịch một lô câu, TRẢ VỀ ĐÚNG SỐ PHẦN TỬ như đầu vào."""

    @abstractmethod
    def generate_title(self, transcript: str, *, count: int = 5) -> list[str]:
        """Sinh tiêu đề tiếng Việt hấp dẫn từ nội dung video."""


def get_translator(model: str | None = None) -> BaseTranslator:
    """Tạo translator theo nhà cung cấp đã cấu hình.

    ``model`` là lựa chọn của RIÊNG video đang xử lý (người dùng chọn ở tab
    "Chờ dịch"). Không truyền thì dùng ``LLM_MODEL`` mặc định.
    """
    provider = get_settings().llm_provider.lower()
    if provider == "anthropic":
        from .anthropic import AnthropicTranslator

        return AnthropicTranslator(model)
    if provider == "openai":
        from .openai import OpenAITranslator

        return OpenAITranslator(model)
    from .mock import MockTranslator

    return MockTranslator(model)
