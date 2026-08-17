"""Cấu hình API — đọc từ biến môi trường / .env. Không hardcode gì."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"), extra="ignore", case_sensitive=False
    )

    database_url: str = "postgresql+psycopg://reup:reup@localhost:5432/reup"
    #: Khoá giải mã bí mật trong bảng ``app_settings``. Bí mật DUY NHẤT còn phải
    #: nằm trong ``.env`` — xem ``reup_core/settings_store.py``.
    settings_key: str = ""
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
    llm_model: str = "deepseek/deepseek-v4-flash-0731"
    #: Bên dịch chọn sẵn ở tab Chờ dịch. API chỉ đọc để trả cho giao diện;
    #: worker mới là chỗ thật sự gọi. Tên khớp ``apps/worker/src/config.py``.
    llm_provider: str = "openrouter"
    #: Bên đọc và giọng chọn sẵn — cùng lý do như trên.
    tts_provider: str = "openrouter"
    tts_giong: str = ""
    tts_model: str = ""
    #: Địa chỉ VoiceStudio chạy tại máy — API chỉ đọc để hỏi danh sách giọng.
    voicestudio_base_url: str = ""
    #: Trần hạn mức tự đặt — nhà cung cấp không trả header hạn mức nào nên phải
    #: tự khai và tự đếm. 0 = không giới hạn.
    llm_max_requests_per_min: int = 0
    llm_max_requests_per_day: int = 0
    #: Trần chi tiêu tháng (USD). 0 = không giới hạn.
    monthly_budget_usd: float = 200.0


def _dam_bao_chung_chi_ssl() -> None:
    """Trỏ Python vào bộ chứng chỉ của ``certifi`` nếu môi trường chưa có.

    Bản Python 3.14 tải từ python.org KHÔNG kèm bộ chứng chỉ hệ thống, nên mọi
    lời gọi HTTPS ném ``CERTIFICATE_VERIFY_FAILED``. Đặt ở đây thay vì bắt người
    chạy nhớ ``SSL_CERT_FILE=...`` trước mỗi lệnh: quên một lần là sinh ra một
    lỗi trông như "khoá API sai" trong khi khoá hoàn toàn đúng.
    """
    if os.getenv("SSL_CERT_FILE"):
        return
    try:
        import certifi
    except ImportError:
        return
    os.environ["SSL_CERT_FILE"] = certifi.where()
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())


#: Đã đọc cấu hình từ DB chưa. Đọc lại mỗi lần gọi sẽ thành một truy vấn DB cho
#: MỖI lời gọi ``get_settings()``, mà hàm đó được gọi ở khắp nơi.
_da_nap = False


def _nap_tu_db() -> None:
    """Đổ cấu hình từ bảng ``app_settings`` vào biến môi trường.

    Chạy TRƯỚC khi dựng ``Settings()``: pydantic đọc từ biến môi trường, nên
    đổ vào đây là mọi chỗ dùng phía sau chạy nguyên như cũ, không phải sửa
    một dòng nào.

    DB không tới được thì BỎ QUA im lặng và rơi về ``.env``: lúc chạy migration
    lần đầu bảng còn chưa tồn tại, mà cả ứng dụng không được chết vì chuyện đó.
    """
    global _da_nap
    if _da_nap:
        return
    #: Cửa thoát cho test. Không có nó thì mọi test dựa vào giá trị MẶC ĐỊNH sẽ
    #: đọc phải database của người đang chạy — test xanh hay đỏ tuỳ máy, và đó
    #: là loại test tệ nhất vì nó không nói lên điều gì.
    if os.getenv("REUP_BO_QUA_CAU_HINH_DB"):
        _da_nap = True
        return
    #: Đặt cờ TRƯỚC khi làm gì: ``Settings()`` dưới đây có thể gọi lại
    #: ``get_settings()`` gián tiếp, và không có cờ thì thành đệ quy vô hạn.
    _da_nap = True
    _dam_bao_chung_chi_ssl()

    try:
        #: Vòng luẩn quẩn phải gỡ: hàm này cần DATABASE_URL để tới DB, nhưng
        #: DATABASE_URL nằm trong ``.env`` mà chỉ pydantic mới đọc được, và
        #: pydantic thì chạy SAU hàm này. Dựng một ``Settings`` sơ bộ chỉ từ
        #: ``.env`` để lấy hai biến bootstrap, rồi mới đọc DB.
        so_bo = Settings()
        os.environ.setdefault("DATABASE_URL", so_bo.database_url)
        if so_bo.settings_key:
            os.environ.setdefault("SETTINGS_KEY", so_bo.settings_key)

        from reup_core.db import session_scope
        from reup_core.settings_store import nap_vao_moi_truong

        with session_scope() as db:
            nap_vao_moi_truong(db)
    except Exception as exc:
        #: Không tới được DB thì vẫn chạy tiếp bằng ``.env`` — nhưng PHẢI kêu.
        #: Nuốt im lặng ở đây từng giấu mất một lỗi kết nối suốt nhiều giờ.
        import logging

        logging.getLogger(__name__).warning("cau_hinh.doc_db_that_bai", exc_info=exc)


def lam_moi_cau_hinh() -> None:
    """Buộc đọc lại cấu hình từ DB ở lần ``get_settings()`` kế tiếp.

    Gọi sau khi người dùng bấm Lưu trên trang cấu hình — không có nó thì thay
    đổi chỉ có tác dụng sau khi khởi động lại tiến trình.
    """
    global _da_nap
    _da_nap = False
    get_settings.cache_clear()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _nap_tu_db()
    s = Settings()
    #: Đẩy MEDIA_ROOT vào biến môi trường để ``reup_core.paths`` nhìn thấy.
    #:
    #: ``paths.py`` đọc bằng ``os.getenv``, còn thiết lập này nạp từ ``.env``
    #: qua pydantic — hai đường khác nhau, nên nếu không nối lại thì giá trị
    #: khai trong ``.env`` KHÔNG có tác dụng gì.
    os.environ.setdefault("MEDIA_ROOT", s.media_root)
    return s
