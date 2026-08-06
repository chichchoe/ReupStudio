"""Dịch bằng Claude qua HTTP (không cần SDK riêng)."""

from __future__ import annotations

import httpx
from reup_core.logging import get_logger

from ..config import get_settings
from ..errors import TranslateError
from ._json import extract_json_array
from .base import BaseTranslator
from .prompts import SYSTEM_PROMPT, TITLE_PROMPT, build_user_prompt

log = get_logger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"


class AnthropicTranslator(BaseTranslator):
    def _call(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        settings = get_settings()
        if not settings.llm_api_key:
            raise TranslateError("Chưa cấu hình LLM_API_KEY")

        payload = {
            "model": settings.llm_model,
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": settings.llm_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(API_URL, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise TranslateError(
                f"LLM trả lỗi {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise TranslateError(f"Không gọi được LLM: {exc}") from exc

        blocks = data.get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")

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
