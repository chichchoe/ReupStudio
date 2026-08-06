"""Test chuẩn hoá phụ đề — sai ở đây là chữ tràn màn hình MỌI video."""

from __future__ import annotations

from src.pipeline.cues import Cue
from src.pipeline.subtitle_format import (
    FormatOptions,
    format_cues,
    merge_short_cues,
    wrap_text,
)

OPTS = FormatOptions()


class TestWrapText:
    def test_cau_ngan_khong_bi_ngat(self) -> None:
        assert wrap_text("Anh nghĩ tôi sẽ quay lại sao?", 42, 2) == "Anh nghĩ tôi sẽ quay lại sao?"

    def test_cau_dai_bi_cat_thanh_hai_dong(self) -> None:
        text = "Ba năm qua thứ tôi chờ đợi không phải là lời xin lỗi của anh mà là ngày tôi tỉnh ra"
        out = wrap_text(text, 42, 2)
        lines = out.split("\n")
        assert len(lines) == 2
        assert lines[0] and lines[1]

    def test_khong_cat_giua_tu(self) -> None:
        out = wrap_text("một hai ba bốn năm sáu bảy tám chín mười", 12, 5)
        for line in out.split("\n"):
            assert not line.startswith(" ") and not line.endswith(" ")

    def test_tu_dai_hon_gioi_han_van_giu_nguyen(self) -> None:
        out = wrap_text("siêudàikhôngcókhoảngtrắngnàocả", 10, 2)
        assert out == "siêudàikhôngcókhoảngtrắngnàocả"

    def test_chuoi_rong(self) -> None:
        assert wrap_text("", 42, 2) == ""
        assert wrap_text("   ", 42, 2) == ""

    def test_khong_vuot_qua_so_dong_toi_da(self) -> None:
        text = " ".join(["từ"] * 60)
        out = wrap_text(text, 10, 2)
        assert out.count("\n") <= 1


class TestMergeShortCues:
    def test_khung_qua_ngan_duoc_gop_voi_khung_sau(self) -> None:
        cues = [Cue(0, 0.0, 0.3, "A"), Cue(1, 0.4, 2.0, "B")]
        out = merge_short_cues(cues, OPTS)
        assert len(out) == 1
        assert out[0].text == "A B"
        assert out[0].end == 2.0

    def test_khung_cuoi_qua_ngan_noi_vao_khung_truoc(self) -> None:
        cues = [Cue(0, 0.0, 2.0, "A"), Cue(1, 2.1, 2.3, "B")]
        out = merge_short_cues(cues, OPTS)
        assert len(out) == 1
        assert out[0].text == "A B"

    def test_danh_sach_rong(self) -> None:
        assert merge_short_cues([], OPTS) == []

    def test_khung_du_dai_khong_bi_gop(self) -> None:
        cues = [Cue(0, 0.0, 2.0, "A"), Cue(1, 2.5, 4.5, "B")]
        assert len(merge_short_cues(cues, OPTS)) == 2


class TestFormatCues:
    def test_bo_khung_rong(self) -> None:
        cues = [Cue(0, 0.0, 2.0, "A"), Cue(1, 2.5, 4.0, "   "), Cue(2, 4.5, 6.0, "B")]
        assert len(format_cues(cues)) == 2

    def test_dam_bao_thoi_luong_toi_thieu(self) -> None:
        out = format_cues([Cue(0, 0.0, 0.6, "Xin chào các bạn nhé")], FormatOptions(merge_below=0.1))
        assert out[0].duration >= 1.2 - 1e-6

    def test_khong_co_khung_nao_chong_thoi_gian(self) -> None:
        cues = [Cue(i, i * 1.0, i * 1.0 + 0.9, f"Câu số {i}") for i in range(6)]
        out = format_cues(cues)
        for prev, nxt in zip(out, out[1:], strict=False):
            assert prev.end <= nxt.start + 1e-6

    def test_moi_dong_khong_vuot_gioi_han_ky_tu(self) -> None:
        long_text = "Từ hôm nay tôi sẽ không nhân nhượng vì bất kỳ ai nữa dù người đó là ai đi chăng nữa"
        out = format_cues([Cue(0, 0.0, 5.0, long_text)])
        for cue in out:
            for line in cue.text.split("\n"):
                assert len(line) <= 42 or " " not in line

    def test_chi_muc_duoc_danh_lai_lien_tuc(self) -> None:
        cues = [Cue(99, 0.0, 2.0, "A"), Cue(50, 3.0, 5.0, "B"), Cue(7, 6.0, 8.0, "C")]
        out = format_cues(cues)
        assert [c.i for c in out] == list(range(len(out)))

    def test_danh_sach_rong_tra_ve_rong(self) -> None:
        assert format_cues([]) == []
