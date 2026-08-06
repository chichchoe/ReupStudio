"""Test parser URL kênh — dùng cho POST /source-channels/resolve (không gọi mạng)."""

from __future__ import annotations

import pytest
from reup_core.enums import SourcePlatform
from reup_core.source_url import parse_channel_url


@pytest.mark.parametrize(
    ("url", "platform", "external_id"),
    [
        (
            "https://www.douyin.com/user/MS4wLjABAAAAabc123",
            SourcePlatform.DOUYIN,
            "MS4wLjABAAAAabc123",
        ),
        ("https://space.bilibili.com/123456789", SourcePlatform.BILIBILI, "123456789"),
        ("https://www.kuaishou.com/profile/3xkc9def", SourcePlatform.KUAISHOU, "3xkc9def"),
        (
            "https://www.xiaohongshu.com/user/profile/5f1a2b3c4d5e6f",
            SourcePlatform.XIAOHONGSHU,
            "5f1a2b3c4d5e6f",
        ),
    ],
)
def test_nhan_dien_dung_nen_tang_va_id_kenh(
    url: str, platform: SourcePlatform, external_id: str
) -> None:
    parsed = parse_channel_url(url)
    assert parsed is not None
    assert parsed.platform is platform
    assert parsed.external_id == external_id
    assert parsed.url == url


def test_url_video_thuong_khong_phai_url_kenh_thi_tra_ve_none() -> None:
    assert parse_channel_url("https://www.douyin.com/video/123") is None


def test_chuoi_rac_tra_ve_none() -> None:
    assert parse_channel_url("không phải url") is None
    assert parse_channel_url("") is None
    assert parse_channel_url("https://youtube.com/watch?v=abc") is None
