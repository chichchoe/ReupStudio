"""Cấu hình worker."""

from __future__ import annotations

import os
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
    #: Khoá giải mã bí mật trong bảng ``app_settings``. Bí mật DUY NHẤT còn phải
    #: nằm trong ``.env`` — xem ``reup_core/settings_store.py``.
    settings_key: str = ""
    redis_url: str = "redis://localhost:6379/0"
    media_root: str = "./media"
    log_level: str = "INFO"

    # --- dịch thuật ---
    #: Bên và model dùng khi video chưa chọn riêng. Người dùng vẫn đổi được cho
    #: từng video ở tab Chờ dịch; đây chỉ là cái được chọn sẵn.
    llm_provider: str = "openrouter"
    llm_api_key: str = ""
    llm_model: str = "deepseek/deepseek-v4-flash-0731"
    llm_batch_size: int = 25
    #: Địa chỉ gốc của API tương thích OpenAI. Gemini, Groq, OpenRouter,
    #: DeepSeek và Ollama đều nói đúng giao thức ``/chat/completions`` này, nên
    #: đổi nhà cung cấp chỉ tốn 3 dòng .env (``LLM_BASE_URL`` + ``LLM_MODEL`` +
    #: ``LLM_API_KEY``), không sửa code, không thêm thư viện. Dùng với
    #: ``LLM_PROVIDER=openai``.
    llm_base_url: str = "https://api.openai.com/v1"
    #: Đơn giá USD cho MỘT TRIỆU token, theo bảng giá nhà cung cấp. Bậc miễn
    #: phí để 0 — khi đó cột ``cost_logs.cost_usd`` luôn bằng 0 và con số chặn
    #: ta lại là SỐ LƯỢT, không phải tiền.
    llm_price_input_per_1m: float = 0.0
    llm_price_output_per_1m: float = 0.0
    #: Trần hạn mức tự đặt. Gemini KHÔNG trả header hạn mức nào (đo 2026-08-14)
    #: nên không hỏi được nhà cung cấp — phải tự khai và tự đếm. Xem hạn mức
    #: thật của dự án tại aistudio.google.com/rate-limit.
    #: 0 = không giới hạn.
    llm_max_requests_per_min: int = 0
    llm_max_requests_per_day: int = 0

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

    # --- lồng tiếng ---
    #: Bên đọc và giọng mặc định. ``edge`` miễn phí; ``openrouter`` và
    #: ``gemini`` tính tiền/hạn mức nên đổi mặc định sang chúng là quyết định
    #: có chủ ý, không phải mặc định an toàn.
    tts_provider: str = "openrouter"
    tts_giong: str = ""
    tts_model: str = ""
    #: Âm GỐC bị hạ xuống mức này khi trộn giọng Việt vào. 0 = tắt hẳn.
    #: Không tắt mặc định vì nhạc nền và tiếng động hiện trường là một phần nội
    #: dung; nhưng 0,18 vẫn còn nghe rõ lời gốc chen vào lời Việt, nên hạ xuống
    #: 0,08 — đủ để còn nhạc nền, không đủ để tranh tiếng với giọng đọc.
    dub_original_volume: float = 0.08

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
    #: Trần chi tiêu tháng (USD) cho mọi dịch vụ ngoài, cộng từ ``cost_logs``.
    #: Vượt trần thì DỪNG HẲN việc dịch, chờ người dùng cho phép — chốt ngày
    #: 2026-08-14, đúng tinh thần M8-BE-04 "hạn mức chi tiêu cứng".
    #: 0 = không giới hạn.
    monthly_budget_usd: float = 200.0
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
