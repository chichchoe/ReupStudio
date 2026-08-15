"""Cue quá dài phải được CHIA thành nhiều cue nối tiếp, không dồn vào một khung.

Quan sát trên ảnh render thật (2026-08-14): phụ đề chiếm 8 dòng, che kín mặt
người, dù cấu hình để tối đa 2 dòng.

Chuỗi nguyên nhân:

1. Whisper gộp cả đoạn nói liền mạch thành MỘT cue dài 19 giây, ~200 ký tự.
2. ``wrap_text`` khi vượt ``max_lines`` thì DỒN phần thừa vào dòng cuối — cố ý,
   ghi rõ trong docstring: "thà chữ hơi dài còn hơn mất nội dung".
3. ``format_cues`` không có bước nào chia cue dài theo thời gian.
4. Kết quả: một dòng cực dài, libass tự ngắt tiếp thành 8 dòng hiển thị.

Cách sửa: chia cue theo thời gian, chia thời lượng theo số ký tự, ưu tiên cắt ở
dấu câu. ``max_lines`` khi đó mới có nghĩa thật.
"""

from __future__ import annotations

import pytest

from src.pipeline.cues import Cue
from src.pipeline.subtitle_format import FormatOptions, split_long_cues

#: Giống cấu hình thật đang chạy: 22 ký tự/dòng, tối đa 2 dòng -> 44 ký tự/cue.
OPTS = FormatOptions(max_chars_per_line=22, max_lines=2, min_duration=1.2)


def _tong_chu(cues: list[Cue]) -> str:
    return " ".join(c.text for c in cues)


def test_cue_vua_khung_thi_giu_nguyen() -> None:
    cues = [Cue(0, 0.0, 3.0, "Câu ngắn vừa đủ")]

    assert split_long_cues(cues, OPTS) == cues


def test_cue_qua_dai_bi_chia_thanh_nhieu_cue() -> None:
    dai = "Ba năm chờ đợi không phải để nghe lời xin lỗi mà để học cách yêu bản thân mình"
    ra = split_long_cues([Cue(0, 0.0, 12.0, dai)], OPTS)

    assert len(ra) > 1


def test_khong_mat_chu_nao_va_giu_dung_thu_tu() -> None:
    """Mất chữ hoặc đảo thứ tự là hỏng bản dịch mà video vẫn chạy — khó thấy nhất."""
    dai = "Ba năm chờ đợi không phải để nghe lời xin lỗi mà để học cách yêu bản thân mình"
    ra = split_long_cues([Cue(0, 0.0, 12.0, dai)], OPTS)

    assert _tong_chu(ra).split() == dai.split()


def test_moi_cue_sau_khi_chia_deu_vua_so_dong_cho_phep() -> None:
    dai = "Ba năm chờ đợi không phải để nghe lời xin lỗi mà để học cách yêu bản thân mình"
    ra = split_long_cues([Cue(0, 0.0, 12.0, dai)], OPTS)

    gioi_han = OPTS.max_chars_per_line * OPTS.max_lines
    for c in ra:
        assert len(c.text) <= gioi_han, f"cue còn dài quá: {c.text!r}"


def test_cac_cue_noi_tiep_nhau_va_phu_dung_khoang_goc() -> None:
    """Chồng lấn thì hai câu hiện cùng lúc; hở thì phụ đề nhấp nháy."""
    dai = "Ba năm chờ đợi không phải để nghe lời xin lỗi mà để học cách yêu bản thân mình"
    ra = split_long_cues([Cue(0, 2.0, 14.0, dai)], OPTS)

    assert ra[0].start == pytest.approx(2.0)
    assert ra[-1].end == pytest.approx(14.0)
    #: Cố ý KHÔNG strict: ``ra[1:]`` luôn ngắn hơn một phần tử.
    for truoc, sau in zip(ra, ra[1:], strict=False):
        assert sau.start == pytest.approx(truoc.end)


def test_cue_nhieu_chu_hon_thi_hien_lau_hon() -> None:
    """Chia đều thời gian sẽ khiến câu dài trôi quá nhanh để đọc kịp."""
    dai = "Một hai " + "chữ " * 30 + "kết thúc ở đây"
    ra = split_long_cues([Cue(0, 0.0, 20.0, dai)], OPTS)

    do_dai = [(len(c.text), c.duration) for c in ra]
    ngan_nhat = min(do_dai)
    dai_nhat = max(do_dai)
    assert dai_nhat[1] >= ngan_nhat[1]


def test_khong_chia_nho_hon_thoi_luong_toi_thieu() -> None:
    """Cue 2 giây mà chia 5 phần thì mỗi phần 0,4 giây — đọc không kịp.

    Thà để một cue hơi dài còn hơn một chuỗi cue nhấp nháy không ai đọc được.
    """
    dai = "Ba năm chờ đợi không phải để nghe lời xin lỗi mà để học cách yêu bản thân"
    ra = split_long_cues([Cue(0, 0.0, 2.0, dai)], OPTS)

    for c in ra:
        assert c.duration >= OPTS.min_duration - 0.01


def test_uu_tien_cat_o_dau_cau() -> None:
    """Cắt giữa mệnh đề đọc khó hơn hẳn cắt ở dấu chấm hay dấu phẩy."""
    text = "Anh tỉnh rồi sao. Đã ba năm rồi đấy anh biết không"
    ra = split_long_cues([Cue(0, 0.0, 10.0, text)], OPTS)

    assert ra[0].text.rstrip().endswith(".")


def test_nhieu_cue_dau_vao_thi_chi_chia_cue_dai() -> None:
    ngan = Cue(0, 0.0, 2.0, "Câu ngắn")
    dai = Cue(1, 2.0, 14.0, "Ba năm chờ đợi không phải để nghe lời xin lỗi mà để học cách yêu")

    ra = split_long_cues([ngan, dai], OPTS)

    assert ra[0] == ngan
    assert len(ra) > 2


def test_dau_phay_som_khong_duoc_don_phan_con_lai_vao_manh_cuoi() -> None:
    """Ca thật lấy từ bản render 2026-08-15, sau khi đã có bước chia.

    Câu mở đầu bằng "Được rồi," — dấu phẩy ở ký tự thứ 9. Bản chia đầu tiên ưu
    tiên dấu câu vô điều kiện nên cắt ngay tại đó, hết luôn số mảnh cho phép,
    rồi dồn 73 ký tự còn lại vào mảnh cuối. Chia xong mà vẫn tràn — đúng lỗi cũ
    chỉ đổi chỗ.

    Ưu tiên dấu câu chỉ được áp dụng khi mảnh đã đủ dài.
    """
    text = (
        "Được rồi, đây là một con voi, điểm hay là chúng có cái vòi siêu dài, "
        "thế thôi, chẳng còn gì để nói nữa."
    )
    ra = split_long_cues([Cue(0, 0.18, 19.18, text)], OPTS)

    gioi_han = OPTS.max_chars_per_line * OPTS.max_lines
    qua_dai = [c.text for c in ra if len(c.text) > gioi_han]
    assert not qua_dai, f"còn mảnh tràn: {qua_dai}"


def test_manh_dau_khong_duoc_ti_hon_so_voi_cac_manh_khac() -> None:
    """Mảnh 9 ký tự nhấp nháy 1,6 giây rồi biến mất — đọc rời rạc, khó chịu."""
    text = (
        "Được rồi, đây là một con voi, điểm hay là chúng có cái vòi siêu dài, "
        "thế thôi, chẳng còn gì để nói nữa."
    )
    ra = split_long_cues([Cue(0, 0.18, 19.18, text)], OPTS)

    ngan_nhat = min(len(c.text) for c in ra)
    assert ngan_nhat >= OPTS.max_chars_per_line * 0.5, [c.text for c in ra]


def test_danh_so_lai_lien_tuc_sau_khi_chia() -> None:
    """Số thứ tự trùng nhau làm file SRT/ASS khó đọc khi debug."""
    dai = "Ba năm chờ đợi không phải để nghe lời xin lỗi mà để học cách yêu bản thân mình"
    ra = split_long_cues([Cue(0, 0.0, 12.0, dai)], OPTS)

    assert [c.i for c in ra] == list(range(len(ra)))
