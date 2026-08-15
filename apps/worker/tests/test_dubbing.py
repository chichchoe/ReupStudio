"""Xếp lịch lồng tiếng: câu tiếng Việt phải rơi đúng lúc nhân vật đang nói.

Đây là phần khó nhất của M8 và là phần DUY NHẤT test tự động được — giọng đọc
hay hay dở thì phải nghe, nhưng lệch thời gian thì tính ra được.

Vấn đề gốc: tiếng Việt dài hơn tiếng Trung. Một câu thoại 2 giây tiếng Trung
dịch ra có thể cần 3 giây để đọc. Không xử lý thì mỗi câu đẩy câu sau trễ dần,
tới cuối video tiếng nói lệch hình hàng chục giây.

Ba cách xử lý, module này dùng cả ba theo thứ tự:

1. Nói nhanh hơn, nhưng có TRẦN — quá 1,5 lần thì người Việt nghe không kịp.
2. Mượn khoảng lặng phía sau nếu câu tiếp theo còn xa.
3. Chấp nhận tràn, nhưng KHÔNG BAO GIỜ đẩy câu sau trễ đi.
"""

from __future__ import annotations

import pytest

from src.pipeline.cues import Cue
from src.pipeline.dubbing import ThamSoLongTieng, lap_lich_long_tieng

TS = ThamSoLongTieng()


def _cue(i: int, bat_dau: float, ket_thuc: float, text: str = "Xin chào các bạn") -> Cue:
    return Cue(i, bat_dau, ket_thuc, text)


# --------------------------------------------------------------------------- #
# Khớp thời gian
# --------------------------------------------------------------------------- #


def test_giong_doc_vua_khung_thi_giu_nguyen_toc_do() -> None:
    """Đọc nhanh hay chậm hơn mà không cần thiết đều làm giọng nghe méo."""
    (doan,) = lap_lich_long_tieng([_cue(0, 1.0, 4.0)], [2.9], TS)

    assert doan.he_so_toc_do == pytest.approx(1.0)


def test_giong_doc_dai_hon_cho_trong_thi_noi_nhanh_len() -> None:
    """Tiếng Việt dài hơn tiếng Trung — đây là ca thường gặp nhất.

    Phải có câu SAU thì mới có ràng buộc: câu cuối cùng không đụng vào ai nên
    cứ đọc thong thả, ép nhanh chỉ làm giọng méo vô ích.
    """
    cues = [_cue(0, 1.0, 3.0), _cue(1, 3.0, 5.0)]

    dau, _ = lap_lich_long_tieng(cues, [3.0, 1.0], TS)

    assert dau.he_so_toc_do > 1.0


def test_cau_cuoi_cung_khong_bi_ep_nhanh() -> None:
    """Không có câu nào phía sau để đụng, nên cứ đọc bình thường."""
    (doan,) = lap_lich_long_tieng([_cue(0, 1.0, 3.0)], [3.0], TS)

    assert doan.he_so_toc_do == pytest.approx(1.0)


def test_giong_doc_ngan_hon_khung_thi_KHONG_keo_cham_lai() -> None:
    """Kéo chậm để lấp đầy khung làm giọng nghe như đang ngái ngủ. Thà im lặng
    một chút còn hơn."""
    (doan,) = lap_lich_long_tieng([_cue(0, 1.0, 5.0)], [1.5], TS)

    assert doan.he_so_toc_do == pytest.approx(1.0)


def test_khong_bao_gio_noi_nhanh_qua_tran() -> None:
    """Quá 1,5 lần thì người Việt nghe không kịp. Thà tràn sang khoảng lặng."""
    (doan,) = lap_lich_long_tieng([_cue(0, 1.0, 2.0)], [10.0], TS)

    assert doan.he_so_toc_do <= TS.toc_do_toi_da


def test_muon_khoang_lang_phia_sau_khi_cau_sau_con_xa() -> None:
    """Câu sau cách 10 giây thì cứ đọc thong thả, không cần ép nhanh."""
    cues = [_cue(0, 1.0, 2.0), _cue(1, 12.0, 14.0)]

    dau, _ = lap_lich_long_tieng(cues, [2.5, 1.0], TS)

    assert dau.he_so_toc_do == pytest.approx(1.0)


def test_ep_nhanh_du_thi_khong_lan_sang_cau_ke_tiep() -> None:
    """Khi trần tốc độ còn đủ dư, phải ép vừa khít chứ không để chồng giọng."""
    cues = [_cue(0, 1.0, 2.0), _cue(1, 3.5, 5.0)]

    dau, sau = lap_lich_long_tieng(cues, [3.0, 1.0], TS)

    assert dau.ket_thuc <= sau.bat_dau + 0.01


def test_ep_het_tran_van_khong_du_thi_CHAP_NHAN_tran() -> None:
    """Đánh đổi đã chốt: thà chồng giọng một đoạn còn hơn hai lựa chọn kia.

    Đọc nhanh quá 1,5 lần thì người xem không bắt được ý — video vẫn "chạy"
    nhưng vô dụng. Cắt bớt câu thì mất nội dung mà không ai biết. Chồng giọng
    thì nghe ra ngay và sửa tay được.
    """
    cues = [_cue(0, 1.0, 2.0), _cue(1, 3.0, 5.0)]

    dau, sau = lap_lich_long_tieng(cues, [5.0, 1.0], TS)

    assert dau.he_so_toc_do == pytest.approx(TS.toc_do_toi_da)
    assert dau.ket_thuc > sau.bat_dau


def test_cau_sau_KHONG_bi_day_tre_di() -> None:
    """Câu trước tràn bao nhiêu cũng không được xê dịch câu sau — lệch hình dồn
    lại tới cuối video thành hàng chục giây."""
    cues = [_cue(0, 1.0, 2.0), _cue(1, 3.0, 5.0)]

    _, sau = lap_lich_long_tieng(cues, [9.0, 1.0], TS)

    assert sau.bat_dau == pytest.approx(3.0)


def test_moi_doan_bat_dau_dung_luc_cue_bat_dau() -> None:
    """Tiếng nói phải khớp lúc nhân vật mở miệng, không sớm không muộn."""
    cues = [_cue(0, 1.5, 3.0), _cue(1, 4.0, 6.0), _cue(2, 8.0, 9.0)]

    ra = lap_lich_long_tieng(cues, [1.4, 1.9, 0.9], TS)

    assert [d.bat_dau for d in ra] == [1.5, 4.0, 8.0]


# --------------------------------------------------------------------------- #
# Ràng buộc chung
# --------------------------------------------------------------------------- #


def test_khong_co_cue_nao_thi_khong_no() -> None:
    assert lap_lich_long_tieng([], [], TS) == []


def test_lech_so_luong_thi_bao_loi_ro() -> None:
    """Lệch số lượng nghĩa là có câu mất giọng hoặc giọng gán nhầm câu — hỏng
    âm thầm, phải dừng lại chứ không đoán."""
    from src.errors import ReupError

    with pytest.raises(ReupError):
        lap_lich_long_tieng([_cue(0, 1.0, 2.0)], [1.0, 2.0], TS)


def test_giong_rong_thi_bo_qua_cau_do() -> None:
    """TTS trả về file 0 giây khi câu chỉ có dấu câu. Giữ lại sẽ chia cho 0."""
    ra = lap_lich_long_tieng([_cue(0, 1.0, 2.0), _cue(1, 3.0, 4.0)], [0.0, 1.0], TS)

    assert len(ra) == 1
    assert ra[0].cue_index == 1


def test_do_dai_sau_khi_ep_tinh_dung() -> None:
    """Ép nhanh 2 lần thì đoạn 4 giây còn 2 giây. Sai công thức ở đây làm mọi
    phép kiểm chồng lấn phía trên vô nghĩa."""
    (doan,) = lap_lich_long_tieng([_cue(0, 0.0, 2.0)], [3.0], TS)

    assert doan.do_dai_sau_khi_ep == pytest.approx(3.0 / doan.he_so_toc_do)
