"""Ghép câu dịch với câu gốc — sai ở đây là người duyệt đối chiếu nhầm câu.

Không ghép theo CHỈ SỐ được: ``format_cues`` gộp câu ngắn, tách câu dài rồi
đánh số lại từ 0, nên câu Việt thứ i không phải bản dịch của câu Trung thứ i.
Đo trên DB thật ngày 2026-08-20: 8/10 video lệch số câu, video tệ nhất lệch
7 giây và ghép ra chữ hoàn toàn không liên quan.

Ghép theo giao nhau thời gian thì đúng, vì mốc giờ của câu Việt bắt nguồn từ
chính câu Trung sinh ra nó.
"""

from __future__ import annotations

from reup_core.doi_chieu import CauDon, ghep_theo_thoi_gian, tu_dicts


def _c(i: int, start: float, end: float, text: str) -> CauDon:
    return CauDon(i=i, start=start, end=end, text=text)


class TestGhepTheoThoiGian:
    def test_mot_doi_mot(self) -> None:
        dich = [_c(0, 0.0, 1.0, "Xin chào"), _c(1, 1.0, 2.0, "Tạm biệt")]
        goc = [_c(0, 0.0, 1.0, "你好"), _c(1, 1.0, 2.0, "再见")]
        ra = ghep_theo_thoi_gian(dich, goc)
        assert [r.goc for r in ra] == ["你好", "再见"]

    def test_mot_cau_goc_bi_TACH_thanh_hai_cau_dich(self) -> None:
        #: format_cues tách câu dài -> hai câu dịch cùng trỏ về một câu gốc.
        dich = [_c(0, 0.0, 1.5, "Nửa đầu"), _c(1, 1.5, 3.0, "nửa sau")]
        goc = [_c(0, 0.0, 3.0, "一句很长的话")]
        ra = ghep_theo_thoi_gian(dich, goc)
        assert [r.goc for r in ra] == ["一句很长的话", "一句很长的话"]

    def test_hai_cau_goc_bi_GOP_thanh_mot_cau_dich(self) -> None:
        #: Hiện CẢ HAI, nối bằng " / " — cách ghép 1-1 sẽ giấu mất một câu.
        dich = [_c(0, 0.0, 2.0, "Đây rồi. Có ngay đây.")]
        goc = [_c(0, 0.0, 1.0, "来"), _c(1, 1.0, 2.0, "好嘞")]
        ra = ghep_theo_thoi_gian(dich, goc)
        assert ra[0].goc == "来 / 好嘞"

    def test_khong_co_cau_goc_nao_trung_gio(self) -> None:
        dich = [_c(0, 10.0, 11.0, "Không có gốc")]
        goc = [_c(0, 0.0, 1.0, "早")]
        ra = ghep_theo_thoi_gian(dich, goc)
        assert ra[0].goc == ""

    def test_cham_bien_khong_tinh_la_giao_nhau(self) -> None:
        #: goc kết thúc ĐÚNG lúc dich bắt đầu -> không chồng lấn, không ghép.
        dich = [_c(0, 1.0, 2.0, "Sau")]
        goc = [_c(0, 0.0, 1.0, "Trước")]
        assert ghep_theo_thoi_gian(dich, goc)[0].goc == ""

    def test_giu_nguyen_chi_so_moc_gio_va_chu_cua_ban_dich(self) -> None:
        dich = [_c(7, 3.25, 4.5, "Bảy")]
        ra = ghep_theo_thoi_gian(dich, [])
        assert (ra[0].i, ra[0].start, ra[0].end, ra[0].dich) == (7, 3.25, 4.5, "Bảy")

    def test_danh_sach_rong(self) -> None:
        assert ghep_theo_thoi_gian([], []) == []
        assert ghep_theo_thoi_gian([], [_c(0, 0.0, 1.0, "x")]) == []

    def test_tu_dicts_doc_dung_cot_cues(self) -> None:
        ra = tu_dicts([{"i": 2, "start": 1.5, "end": 3.0, "text": "x", "sua_tay": True}])
        assert ra == [CauDon(i=2, start=1.5, end=3.0, text="x")]

    def test_khong_bo_sot_khi_cau_goc_dai_trum_nhieu_cau_dich(self) -> None:
        #: Con trỏ quét không được nhảy qua câu gốc còn dùng cho câu dịch sau.
        dich = [_c(0, 0.0, 1.0, "a"), _c(1, 1.0, 2.0, "b"), _c(2, 2.0, 3.0, "c")]
        goc = [_c(0, 0.0, 3.0, "TRÙM")]
        assert [r.goc for r in ghep_theo_thoi_gian(dich, goc)] == ["TRÙM"] * 3
