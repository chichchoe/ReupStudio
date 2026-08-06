"""Test parser URL nguồn — nền tảng TQ đổi format là hỏng ngầm, phải có test."""

from __future__ import annotations

import pytest
from reup_core.enums import SourcePlatform
from reup_core.source_url import parse_source_url


@pytest.mark.parametrize(
    ("url", "platform", "video_id"),
    [
        ("https://www.douyin.com/video/7312345678901234567", SourcePlatform.DOUYIN, "7312345678901234567"),
        ("https://v.douyin.com/iRxAbCd/", SourcePlatform.DOUYIN, "iRxAbCd"),
        ("https://www.bilibili.com/video/BV1xx411c7mD", SourcePlatform.BILIBILI, "BV1xx411c7mD"),
        ("https://www.kuaishou.com/short-video/3xabc123", SourcePlatform.KUAISHOU, "3xabc123"),
        ("https://www.xiaohongshu.com/explore/65a1b2c3d4e5f6", SourcePlatform.XIAOHONGSHU, "65a1b2c3d4e5f6"),
    ],
)
def test_nhan_dien_dung_nen_tang(url: str, platform: SourcePlatform, video_id: str) -> None:
    parsed = parse_source_url(url)
    assert parsed is not None
    assert parsed.platform is platform
    assert parsed.video_id == video_id


def test_link_co_tham_so_share_van_nhan_dien_duoc() -> None:
    url = "https://www.douyin.com/video/7312345678901234567?region=CN&mid=123&u_code=abc"
    parsed = parse_source_url(url)
    assert parsed is not None
    assert parsed.video_id == "7312345678901234567"


def test_link_rut_gon_duoc_danh_dau_provisional() -> None:
    parsed = parse_source_url("https://v.douyin.com/iRxAbCd/")
    assert parsed is not None and parsed.provisional is True


def test_url_khong_hop_le_tra_ve_none() -> None:
    assert parse_source_url("không phải url") is None
    assert parse_source_url("") is None
    assert parse_source_url("https://youtube.com/watch?v=abc") is None


def test_domain_quen_thuoc_nhung_khong_khop_mau() -> None:
    parsed = parse_source_url("https://www.douyin.com/discover?modal_id=999")
    assert parsed is not None
    assert parsed.platform is SourcePlatform.DOUYIN
    assert parsed.provisional is True
