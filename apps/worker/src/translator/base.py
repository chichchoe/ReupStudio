"""Lớp trừu tượng cho dịch thuật — đổi nhà cung cấp không đụng tới pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import get_settings


class BaseTranslator(ABC):
    @abstractmethod
    def translate_batch(
        self, texts: list[str], *, tone: str, glossary: dict[str, str]
    ) -> list[str]:
        """Dịch một lô câu, TRẢ VỀ ĐÚNG SỐ PHẦN TỬ như đầu vào."""

    @abstractmethod
    def generate_title(self, transcript: str, *, count: int = 5) -> list[str]:
        """Sinh tiêu đề tiếng Việt hấp dẫn từ nội dung video."""


def get_translator() -> BaseTranslator:
    provider = get_settings().llm_provider.lower()
    if provider == "anthropic":
        from .anthropic import AnthropicTranslator

        return AnthropicTranslator()
    if provider == "openai":
        from .openai import OpenAITranslator

        return OpenAITranslator()
    from .mock import MockTranslator

    return MockTranslator()
