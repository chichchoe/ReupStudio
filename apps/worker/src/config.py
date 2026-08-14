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
    #: Địa chỉ gốc của API tương thích OpenAI. Gemini, Groq, OpenRouter,
    #: DeepSeek và Ollama đều nói đúng giao thức ``/chat/completions`` này, nên
    #: đổi nhà cung cấp chỉ tốn 3 dòng .env (``LLM_BASE_URL`` + ``LLM_MODEL`` +
    #: ``LLM_API_KEY``), không sửa code, không thêm thư viện. Dùng với
    #: ``LLM_PROVIDER=openai``.
    llm_base_url: str = "https://api.openai.com/v1"

    # --- tải video ---
    #: Đường dẫn file cookie dạng Netscape. Một số nền tảng (Douyin) từ chối
    #: mọi request không có cookie, kể cả cookie khách chưa đăng nhập. Ưu tiên
    #: cách này hơn đọc trình duyệt vì nó chạy được cả trong Docker.
    ytdlp_cookie_file: str = ""
    #: Tên trình duyệt để yt-dlp tự đọc cookie: chrome | firefox | edge | safari.
    #: Chỉ dùng được khi worker chạy THẲNG trên máy có trình duyệt đó — trong
    #: Docker không có trình duyệt nào để đọc.
    ytdlp_cookies_from_browser: str = ""

    # --- nhận dạng giọng nói ---
    whisper_model: str = "large-v3"
    whisper_device: str = "auto"  # auto | cuda | cpu
    whisper_compute_type: str = "int8_float16"

    # --- phụ đề ---
    sub_font: str = "Be Vietnam Pro"
    #: Cỡ chữ tính bằng PIXEL ở khung chuẩn 1080×1920 (xem
    #: ``pipeline/subtitle_ass.py::SUB_REFERENCE_HEIGHT``); khung khác quy đổi
    #: theo tỉ lệ chiều cao. 104px ≈ 5,4% chiều cao — cỡ thông dụng của video
    #: ngắn. Giá trị cũ 54px chỉ chiếm 2,8%, là cỡ phụ đề phim chiếu rạp, xem
    #: trên điện thoại quá nhỏ.
    sub_font_size: int = 104
    #: Đi kèm cỡ chữ: 104px × 0,5 ≈ 52px/ký tự, khung rộng 1080 trừ lề 2×54
    #: còn 972px -> khoảng 18–22 ký tự một dòng. Giá trị cũ 42 hợp với cỡ chữ
    #: cũ; giữ nguyên 42 với chữ to gấp đôi là chắc chắn tràn.
    sub_max_chars_per_line: int = 22
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
