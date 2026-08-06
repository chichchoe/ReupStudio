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


@lru_cache
def get_settings() -> Settings:
    return Settings()
