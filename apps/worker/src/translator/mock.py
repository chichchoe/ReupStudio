"""Translator giả — chạy được toàn bộ pipeline khi chưa có API key.

Hữu ích để test hạ tầng mà không tốn tiền.
"""

from __future__ import annotations

from .base import BaseTranslator


class MockTranslator(BaseTranslator):
    def translate_batch(
        self, texts: list[str], *, tone: str, glossary: dict[str, str]
    ) -> list[str]:
        return [f"[VI] {t}" for t in texts]

    def generate_title(self, transcript: str, *, count: int = 5) -> list[str]:
        return [f"Tiêu đề thử nghiệm #{i + 1}" for i in range(count)]
