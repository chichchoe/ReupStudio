"""Cấu hình API — đọc từ biến môi trường / .env. Không hardcode gì."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"), extra="ignore", case_sensitive=False
    )

    database_url: str = "postgresql+psycopg://reup:reup@localhost:5432/reup"
    redis_url: str = "redis://localhost:6379/0"
    media_root: str = "./media"

    cors_origins: list[str] = ["http://localhost:3000"]
    log_level: str = "INFO"

    max_video_duration_sec: int = 600

    # --- LLM ---
    # Tên trường TRÙNG KHỚP ``apps/worker/src/config.py`` để cùng đọc một bộ
    # biến môi trường. Hai app độc lập (không import chéo) nên đây là chỗ duy
    # nhất giữ cho chúng hiểu cùng một ``.env``: đổi tên ở đây mà không đổi bên
    # kia thì API hiện một đằng, worker chạy một nẻo.
    #: Địa chỉ gốc của API tương thích OpenAI (Gemini, Groq, OpenRouter...).
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    #: Model mặc định. API chỉ đọc để trả về cho giao diện CHỌN SẴN trong ô
    #: chọn — việc dịch là của worker. Tên khớp ``apps/worker/src/config.py``
    #: để hai app đọc chung một dòng trong ``.env``.
    llm_model: str = ""
    #: Trần hạn mức tự đặt — nhà cung cấp không trả header hạn mức nào nên phải
    #: tự khai và tự đếm. 0 = không giới hạn.
    llm_max_requests_per_min: int = 0
    llm_max_requests_per_day: int = 0
    #: Trần chi tiêu tháng (USD). 0 = không giới hạn.
    monthly_budget_usd: float = 200.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
