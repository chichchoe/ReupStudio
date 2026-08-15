"""Test parser URL nguồn — nền tảng TQ đổi format là hỏng ngầm, phải có test."""

from __future__ import annotations

import pytest
from reup_core.enums import SourcePlatform
from reup_core.source_url import parse_source_url


@pytest.mark.parametrize(
    ("url", "platform", "video_id"),
    [
        (
            "https://www.douyin.com/video/7312345678901234567",
            SourcePlatform.DOUYIN,
            "7312345678901234567",
        ),
        ("https://v.douyin.com/iRxAbCd/", SourcePlatform.DOUYIN, "iRxAbCd"),
        ("https://www.bilibili.com/video/BV1xx411c7mD", SourcePlatform.BILIBILI, "BV1xx411c7mD"),
        ("https://www.kuaishou.com/short-video/3xabc123", SourcePlatform.KUAISHOU, "3xabc123"),
        (
            "https://www.xiaohongshu.com/explore/65a1b2c3d4e5f6",
            SourcePlatform.XIAOHONGSHU,
            "65a1b2c3d4e5f6",
        ),
        # Nguồn ngoài Trung Quốc — yt-dlp tải được, không có lý do chặn ở cổng vào.
        ("https://www.youtube.com/watch?v=aqz-KE-bpKQ", SourcePlatform.YOUTUBE, "aqz-KE-bpKQ"),
        ("https://youtu.be/aqz-KE-bpKQ", SourcePlatform.YOUTUBE, "aqz-KE-bpKQ"),
        ("https://www.youtube.com/shorts/abc123_-XY", SourcePlatform.YOUTUBE, "abc123_-XY"),
        (
            "https://www.tiktok.com/@user.name/video/7123456789012345678",
            SourcePlatform.TIKTOK,
            "7123456789012345678",
        ),
        ("https://www.instagram.com/reel/Cabc123_-X/", SourcePlatform.INSTAGRAM, "Cabc123_-X"),
        ("https://www.facebook.com/reel/1234567890", SourcePlatform.FACEBOOK, "1234567890"),
        (
            "https://x.com/someone/status/1234567890123456789",
            SourcePlatform.TWITTER,
            "1234567890123456789",
        ),
        (
            "https://twitter.com/someone/status/1234567890123456789",
            SourcePlatform.TWITTER,
            "1234567890123456789",
        ),
    ],
)
def test_nhan_dien_dung_nen_tang(url: str, platform: SourcePlatform, video_id: str) -> None:
    parsed = parse_source_url(url)
    assert parsed is not None
    assert parsed.platform is platform
    assert parsed.video_id == video_id


@pytest.mark.parametrize(
    "url",
    [
        "https://vm.tiktok.com/ZSabcdef/",
        "https://fb.watch/aBcD1234/",
        "https://b23.tv/aBcD12",
    ],
)
def test_link_rut_gon_cua_nen_tang_moi_cung_la_provisional(url: str) -> None:
    parsed = parse_source_url(url)
    assert parsed is not None and parsed.provisional is True


def test_link_douyin_dang_modal_id_nhan_dien_duoc() -> None:
    """Dạng URL Douyin dùng khi bấm video trong trang khám phá.

    Đo bằng yt-dlp thật (2026-08-14): dạng ``/jingxuan/vlog?modal_id=...`` bị
    trả về ``ERROR: Unsupported URL``, trong khi ``/video/<id>`` thì nhận. Nên
    phải bóc ID ra chứ không đưa nguyên URL xuống bước tải.
    """
    parsed = parse_source_url("https://www.douyin.com/jingxuan/vlog?modal_id=7665256127663312179")
    assert parsed is not None
    assert parsed.platform is SourcePlatform.DOUYIN
    assert parsed.video_id == "7665256127663312179"
    assert parsed.provisional is False


def test_link_modal_id_duoc_viet_lai_ve_dang_chuan() -> None:
    """URL lưu vào DB (và đưa cho yt-dlp) phải là dạng yt-dlp hiểu được."""
    parsed = parse_source_url("https://www.douyin.com/jingxuan/vlog?modal_id=7665256127663312179")
    assert parsed is not None
    assert parsed.url == "https://www.douyin.com/video/7665256127663312179"


def test_link_douyin_dang_chuan_giu_nguyen_khong_bi_viet_lai() -> None:
    goc = "https://www.douyin.com/video/7312345678901234567?region=CN"
    parsed = parse_source_url(goc)
    assert parsed is not None
    assert parsed.url == "https://www.douyin.com/video/7312345678901234567"


def test_link_nen_tang_khac_giu_nguyen_url() -> None:
    """Chỉ Douyin có dạng URL cần viết lại — đừng đụng vào nguồn khác."""
    goc = "https://www.youtube.com/watch?v=aqz-KE-bpKQ&t=30s"
    parsed = parse_source_url(goc)
    assert parsed is not None
    assert parsed.url == goc


def test_link_co_tham_so_share_van_nhan_dien_duoc() -> None:
    url = "https://www.douyin.com/video/7312345678901234567?region=CN&mid=123&u_code=abc"
    parsed = parse_source_url(url)
    assert parsed is not None
    assert parsed.video_id == "7312345678901234567"


def test_link_rut_gon_duoc_danh_dau_provisional() -> None:
    parsed = parse_source_url("https://v.douyin.com/iRxAbCd/")
    assert parsed is not None and parsed.provisional is True


def test_url_khong_hop_le_tra_ve_none() -> None:
    """Chỉ thứ KHÔNG phải URL mới bị loại ở cổng vào.

    Trước đây hàm này còn từ chối cả `youtube.com` — nay bỏ, vì yt-dlp phía sau
    tải được hơn 1800 site và `get_downloader` đã có sẵn fallback. Đoán ở cổng
    vào chỉ chặn nhầm nguồn hợp lệ; để bước tải báo lỗi thật thì chính xác hơn.
    """
    assert parse_source_url("không phải url") is None
    assert parse_source_url("") is None
    assert parse_source_url("ftp://example.com/a.mp4") is None


def test_domain_quen_thuoc_nhung_khong_khop_mau() -> None:
    """URL Douyin không mang ID video nào — vẫn nhận, ID để tạm.

    Trước đây ví dụ ở đây là ``/discover?modal_id=999``; từ khi có mẫu
    ``modal_id`` thì dạng đó bóc được ID thật, không còn là ví dụ đúng cho
    nhánh dự phòng nữa.
    """
    parsed = parse_source_url("https://www.douyin.com/discover")
    assert parsed is not None
    assert parsed.platform is SourcePlatform.DOUYIN
    assert parsed.provisional is True


@pytest.mark.parametrize(
    "url",
    [
        "https://vimeo.com/76979871",
        "https://example.com/clip.mp4",
        "https://www.nicovideo.jp/watch/sm9",
    ],
)
def test_nguon_la_van_duoc_nhan_de_yt_dlp_thu(url: str) -> None:
    parsed = parse_source_url(url)
    assert parsed is not None
    assert parsed.platform is SourcePlatform.OTHER
    #: ID chỉ là tạm — ID thật lấy được sau khi yt-dlp đọc metadata.
    assert parsed.provisional is True
    assert parsed.video_id.startswith("u")


def test_domain_gan_giong_khong_bi_nhan_nham() -> None:
    """``netflix.com`` kết thúc bằng ``x.com`` — so khớp bằng ``endswith`` trần
    sẽ gán nhầm nền tảng. Phải khớp trọn nhãn tên miền."""
    parsed = parse_source_url("https://www.netflix.com/title/80100172")
    assert parsed is not None
    assert parsed.platform is SourcePlatform.OTHER

    parsed = parse_source_url("https://khongphaidouyin.com/video/1")
    assert parsed is not None
    assert parsed.platform is SourcePlatform.OTHER
