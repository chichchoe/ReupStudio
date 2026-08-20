"""Dịch lại KHÔNG được xoá công người dùng đã chữa tay.

Người dùng ngồi sửa 20 câu, rồi bấm "dịch lại toàn bộ bằng model khác" vì
những câu CÒN LẠI chưa ưng. Ghi đè tất thì 20 câu kia mất sạch, và mất im
lặng — không lỗi, không cảnh báo.
"""

from __future__ import annotations

from src.tasks.dich_lai import gop_giu_cau_sua_tay


def test_giu_cau_sua_tay_bo_qua_ban_dich_moi() -> None:
    cu = [
        {"i": 0, "start": 0.0, "end": 1.0, "text": "Người dùng chữa", "sua_tay": True},
        {"i": 1, "start": 1.0, "end": 2.0, "text": "Máy dịch cũ"},
    ]
    moi = [
        {"i": 0, "start": 0.0, "end": 1.0, "text": "Máy dịch lại"},
        {"i": 1, "start": 1.0, "end": 2.0, "text": "Máy dịch mới"},
    ]
    ra = gop_giu_cau_sua_tay(cu, moi)
    assert [c["text"] for c in ra] == ["Người dùng chữa", "Máy dịch mới"]
    assert ra[0]["sua_tay"] is True


def test_giu_nguyen_thu_tu_va_so_luong() -> None:
    cu = [{"i": i, "start": float(i), "end": i + 1.0, "text": f"cũ {i}"} for i in range(5)]
    moi = [{"i": i, "start": float(i), "end": i + 1.0, "text": f"mới {i}"} for i in range(5)]
    ra = gop_giu_cau_sua_tay(cu, moi)
    assert [c["i"] for c in ra] == [0, 1, 2, 3, 4]
    assert [c["text"] for c in ra] == [f"mới {i}" for i in range(5)]


def test_khong_co_cau_sua_tay_thi_lay_het_ban_moi() -> None:
    cu = [{"i": 0, "start": 0.0, "end": 1.0, "text": "cũ"}]
    moi = [{"i": 0, "start": 0.0, "end": 1.0, "text": "mới"}]
    assert gop_giu_cau_sua_tay(cu, moi)[0]["text"] == "mới"


def test_ban_moi_thieu_cau_thi_giu_cau_cu() -> None:
    #: Model trả thiếu câu là chuyện có thật. Bỏ luôn câu đó thì phụ đề hụt
    #: một đoạn mà video vẫn "xong".
    cu = [
        {"i": 0, "start": 0.0, "end": 1.0, "text": "cũ 0"},
        {"i": 1, "start": 1.0, "end": 2.0, "text": "cũ 1"},
    ]
    moi = [{"i": 0, "start": 0.0, "end": 1.0, "text": "mới 0"}]
    ra = gop_giu_cau_sua_tay(cu, moi)
    assert [c["text"] for c in ra] == ["mới 0", "cũ 1"]


def test_giu_nguyen_moc_thoi_gian_cua_ban_cu() -> None:
    #: Model có thể trả về mốc giờ khác. Mốc giờ do bước nhận dạng và chuẩn
    #: hoá tính ra — lấy theo bản dịch mới là mở đường cho phụ đề chồng nhau.
    cu = [{"i": 0, "start": 1.25, "end": 3.5, "text": "cũ"}]
    moi = [{"i": 0, "start": 99.0, "end": 100.0, "text": "mới"}]
    ra = gop_giu_cau_sua_tay(cu, moi)
    assert (ra[0]["start"], ra[0]["end"]) == (1.25, 3.5)
