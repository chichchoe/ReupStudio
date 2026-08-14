"""Nạp cookie cho yt-dlp qua cấu hình.

Đo bằng yt-dlp thật (2026-08-14): Douyin trả về
``ERROR: [Douyin] <id>: Fresh cookies (not necessarily logged in) are needed``
ngay cả với URL đúng chuẩn. Câu "not necessarily logged in" là điểm quan trọng
— chỉ cần cookie KHÁCH của một trình duyệt đã ghé douyin.com, không cần tài
khoản. Đây là chống bot của nền tảng, không vá bằng logic được.

Hai đường nạp, ưu tiên file vì nó chạy được cả trong Docker (nơi không có
trình duyệt nào để đọc):

- ``YTDLP_COOKIE_FILE``: đường dẫn file cookie dạng Netscape.
- ``YTDLP_COOKIES_FROM_BROWSER``: tên trình duyệt trên máy (chrome/firefox/...).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.downloaders.ytdlp_downloader import YtDlpDownloader


@pytest.fixture
def cau_hinh(monkeypatch):
    """Đặt cấu hình worker, cô lập khỏi file .env của máy đang chạy."""
    import src.downloaders.ytdlp_downloader as mod
    from src.config import Settings

    def _dat(**kw):
        monkeypatch.setattr(mod, "get_settings", lambda: Settings(_env_file=None, **kw))

    return _dat


def test_khong_cau_hinh_thi_khong_them_tuy_chon_cookie(cau_hinh, tmp_path) -> None:
    """Mặc định phải sạch — không tự đọc trình duyệt của người dùng khi chưa
    được yêu cầu."""
    cau_hinh()
    opts = YtDlpDownloader().build_opts(tmp_path)
    assert "cookiefile" not in opts
    assert "cookiesfrombrowser" not in opts


def test_cookie_file_duoc_dua_vao_opts(cau_hinh, tmp_path) -> None:
    f = tmp_path / "cookies.txt"
    f.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    cau_hinh(ytdlp_cookie_file=str(f))

    opts = YtDlpDownloader().build_opts(tmp_path)

    assert opts["cookiefile"] == str(f)
    assert "cookiesfrombrowser" not in opts


def test_ten_trinh_duyet_duoc_doi_thanh_dung_dinh_dang_yt_dlp(cau_hinh, tmp_path) -> None:
    """yt-dlp nhận một TUPLE ``(tên_trình_duyệt,)``, không phải chuỗi trần."""
    cau_hinh(ytdlp_cookies_from_browser="chrome")

    opts = YtDlpDownloader().build_opts(tmp_path)

    assert opts["cookiesfrombrowser"] == ("chrome",)


def test_file_cookie_duoc_uu_tien_hon_trinh_duyet(cau_hinh, tmp_path) -> None:
    """Cấu hình cả hai thì dùng file: nó chạy được trong Docker, còn đọc trình
    duyệt thì không."""
    f = tmp_path / "cookies.txt"
    f.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    cau_hinh(ytdlp_cookie_file=str(f), ytdlp_cookies_from_browser="chrome")

    opts = YtDlpDownloader().build_opts(tmp_path)

    assert opts["cookiefile"] == str(f)
    assert "cookiesfrombrowser" not in opts


def test_file_cookie_khong_ton_tai_thi_bao_loi_ro(cau_hinh, tmp_path) -> None:
    """Sai đường dẫn mà im lặng bỏ qua thì người dùng sẽ ngồi đoán vì sao vẫn
    bị chặn."""
    from src.errors import DownloadError

    cau_hinh(ytdlp_cookie_file=str(tmp_path / "khong-co-that.txt"))

    with pytest.raises(DownloadError) as loi:
        YtDlpDownloader().build_opts(tmp_path)

    assert "khong-co-that.txt" in str(loi.value)


def test_douyin_van_giu_header_rieng_khi_them_cookie(cau_hinh, tmp_path) -> None:
    """``extra_opts`` của từng nền tảng con không được cookie ghi đè mất."""
    from src.downloaders.douyin import DouyinDownloader

    cau_hinh(ytdlp_cookies_from_browser="chrome")

    opts = DouyinDownloader().build_opts(Path(tmp_path))

    assert opts["cookiesfrombrowser"] == ("chrome",)
    assert "Referer" in opts["http_headers"]
