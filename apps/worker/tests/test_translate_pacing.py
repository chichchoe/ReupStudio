"""Giãn nhịp chủ động để không đâm vào trần lượt/phút.

Đo thật ngày 2026-08-14: video 34 phút (672 câu) dịch mất 3 TIẾNG. Nguyên nhân
không phải mạng chậm mà là bắn 27 lượt gọi liên tiếp vào một model có trần 5
lượt/phút — bị từ chối liên tục rồi lùi dần theo cấp số nhân.

Retry chỉ chữa lỗi TẠM THỜI. Trần tính theo phút là giới hạn CẤU TRÚC: cách
đúng là chủ động chờ cho vừa nhịp, thay vì bắn hết rồi bị chặn.
"""

from __future__ import annotations

import pytest

from src.pipeline import translate as mod
from src.pipeline.cues import Cue
from src.translator.base import LlmUsage


class TranslatorGia:
    def __init__(self):
        self.usage = LlmUsage(model="m")

    def translate_batch(self, texts, *, tone, glossary):
        self.usage.add(total_tokens=1)
        return [f"vi:{t}" for t in texts]


@pytest.fixture
def dong_ho(monkeypatch):
    """Đồng hồ giả: thời gian chỉ nhích khi có ai đó "ngủ"."""
    trang_thai = {"now": 1000.0, "da_ngu": []}

    def _now():
        return trang_thai["now"]

    def _sleep(giay):
        trang_thai["da_ngu"].append(giay)
        trang_thai["now"] += giay

    monkeypatch.setattr(mod, "_now", _now)
    monkeypatch.setattr(mod, "_sleep", _sleep)
    monkeypatch.setattr(mod, "get_translator", lambda: TranslatorGia())
    return trang_thai


def _cau_hinh(monkeypatch, *, batch: int, rpm: int):
    from src.config import Settings

    monkeypatch.setattr(
        mod,
        "get_settings",
        lambda: Settings(_env_file=None, llm_batch_size=batch, llm_max_requests_per_min=rpm),
    )


def _cues(n: int) -> list[Cue]:
    return [Cue(i, i, i + 1, f"câu {i}") for i in range(n)]


def test_khong_khai_tran_thi_khong_cho(dong_ho, monkeypatch) -> None:
    """Trần 0 = không giới hạn. Không được tự ý làm chậm khi chưa ai yêu cầu."""
    _cau_hinh(monkeypatch, batch=1, rpm=0)

    mod.translate_cues(_cues(5))

    assert dong_ho["da_ngu"] == []


def test_duoi_tran_thi_chay_thang_khong_cho(dong_ho, monkeypatch) -> None:
    _cau_hinh(monkeypatch, batch=1, rpm=10)

    mod.translate_cues(_cues(3))  # 3 lượt, trần 10 -> thoải mái

    assert dong_ho["da_ngu"] == []


def test_cham_tran_thi_cho_cho_qua_cua_so_mot_phut(dong_ho, monkeypatch) -> None:
    """Trần 2 lượt/phút, 3 lô -> lô thứ ba phải đợi lô đầu rơi khỏi cửa sổ."""
    _cau_hinh(monkeypatch, batch=1, rpm=2)

    mod.translate_cues(_cues(3))

    assert len(dong_ho["da_ngu"]) == 1
    assert dong_ho["da_ngu"][0] == pytest.approx(60.0, abs=0.1)


def test_cho_dung_bang_phan_con_lai_cua_cua_so(dong_ho, monkeypatch) -> None:
    """Không chờ thừa: chỉ chờ tới lúc lượt cũ nhất tròn 60 giây."""
    _cau_hinh(monkeypatch, batch=1, rpm=1)

    def _co_troi_thoi_gian(texts, *, tone, glossary):
        dong_ho["now"] += 20.0  # mỗi lượt gọi tốn 20 giây
        return [f"vi:{t}" for t in texts]

    t = TranslatorGia()
    t.translate_batch = _co_troi_thoi_gian
    monkeypatch.setattr(mod, "get_translator", lambda: t)

    mod.translate_cues(_cues(2))

    #: Lượt đầu xong ở mốc +20s; lô sau chỉ cần chờ nốt 40s cho tròn phút.
    assert dong_ho["da_ngu"][0] == pytest.approx(40.0, abs=0.1)


def test_lo_lon_hon_thi_it_luot_hon_nen_it_phai_cho(dong_ho, monkeypatch) -> None:
    """Chính là lý do tăng LLM_BATCH_SIZE: cùng số câu, lô to thì ít lượt gọi.

    100 câu, trần 2 lượt/phút: lô 10 -> 10 lượt (phải chờ nhiều lần);
    lô 50 -> 2 lượt (không phải chờ lần nào).
    """
    _cau_hinh(monkeypatch, batch=10, rpm=2)
    mod.translate_cues(_cues(100))
    lo_nho = len(dong_ho["da_ngu"])

    dong_ho["da_ngu"].clear()
    _cau_hinh(monkeypatch, batch=50, rpm=2)
    mod.translate_cues(_cues(100))
    lo_to = len(dong_ho["da_ngu"])

    assert lo_nho > 0
    assert lo_to == 0
