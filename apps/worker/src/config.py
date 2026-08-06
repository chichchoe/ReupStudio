"""Cấu hình worker."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Số khung pHash tối đa mà cột ``videos.phash`` (String(64)) còn chứa được.
#: Mỗi khung sinh ra 16 ký tự hex (64 bit) -> 4 khung x 16 = 64 ký tự, vừa khít.
MAX_DEDUP_PHASH_FRAMES = 4


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"), extra="ignore", case_sensitive=False
    )

    database_url: str = "postgresql+psycopg://reup:reup@localhost:5432/reup"
    redis_url: str = "redis://localhost:6379/0"
    media_root: str = "./media"
    log_level: str = "INFO"

    # --- dịch thuật ---
    llm_provider: str = "mock"  # anthropic | openai | mock
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-5"
    llm_batch_size: int = 25

    # --- nhận dạng giọng nói ---
    whisper_model: str = "large-v3"
    whisper_device: str = "auto"  # auto | cuda | cpu
    whisper_compute_type: str = "int8_float16"

    # --- phụ đề ---
    sub_font: str = "Be Vietnam Pro"
    sub_font_size: int = 54
    sub_max_chars_per_line: int = 42
    sub_max_lines: int = 2
    sub_min_duration: float = 1.2

    # --- chống trùng ---
    dedup_enabled: bool = True
    #: Số khung lấy mẫu cho pHash. ĐỔI SỐ NÀY = mọi pHash cũ trong DB hết so
    #: sánh được (khác độ dài chuỗi) — phải tính lại toàn bộ.
    dedup_phash_frames: int = 4
    #: Ngưỡng bit khác nhau tối đa trên TỔNG số bit (4 khung × 64 = 256 bit).
    #: Càng nhỏ càng chặt. 20 ≈ 5 bit/khung: bắt được bản mã hoá lại, hiếm khi
    #: nhầm hai video khác nhau.
    dedup_phash_max_distance: int = 20
    #: Chỉ quét ngần này video gần nhất khi so pHash — Postgres không so được
    #: khoảng cách Hamming, phải kéo về Python.
    dedup_phash_scan_limit: int = 500

    # --- giới hạn an toàn ---
    max_video_duration_sec: int = 600
    download_timeout_sec: int = 600
    ffmpeg_timeout_sec: int = 1800

    @field_validator("dedup_phash_frames")
    @classmethod
    def _kiem_tra_dedup_phash_frames(cls, v: int) -> int:
        """Chặn giá trị làm chuỗi pHash vượt độ rộng cột ``videos.phash``.

        Mỗi khung sinh 16 ký tự hex; cột là ``String(64)`` nên tối đa 4 khung.
        Vượt quá sẽ ném ``StringDataRightTruncation`` từ Postgres ngay bước
        download, cho MỌI video — không nới cột, chặn ở đầu vào.
        """
        if not 1 <= v <= MAX_DEDUP_PHASH_FRAMES:
            raise ValueError(
                f"dedup_phash_frames={v} không hợp lệ: phải trong khoảng "
                f"1..{MAX_DEDUP_PHASH_FRAMES} vì cột videos.phash chỉ rộng "
                f"64 ký tự (mỗi khung chiếm 16 ký tự hex)."
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
