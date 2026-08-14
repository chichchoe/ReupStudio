"""Giãn nhịp chủ động để không đâm vào trần lượt/phút.

Đo thật 2026-08-14: video 34 phút (672 câu) dịch mất 3 TIẾNG vì bắn liên tiếp
vào model có trần 5 lượt/phút. Retry chỉ chữa lỗi TẠM THỜI — mỗi lượt bị từ
chối vẫn tính vào hạn mức, càng bắn càng lún.

BẢN ĐẦU CỦA CƠ CHẾ NÀY ĐÃ SAI, và bộ test cũ không bắt được:

Nó đếm mốc thời gian trong BỘ NHỚ của từng tiến trình. Worker chạy
``concurrency=2``, hai task song song mỗi bên tự thấy mình dưới trần, cộng lại
gấp đôi. Trần là của CẢ DỰ ÁN, không phải của từng tiến trình — đo trên video
thật mới lộ ra, test một tiến trình không thể thấy.

Nay đếm từ NGUỒN CHUNG: một hàm ``dem_luot_gan_day`` do tầng ``tasks/`` tiêm
vào, đằng sau nó là bảng ``cost_logs``. Mọi tiến trình worker nhìn chung một
con số.
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
    """Đồng hồ giả — không bài test nào phải chờ thật 60 giây."""
    trang_thai = {"da_ngu": []}
    monkeypatch.setattr(mod, "_sleep", lambda giay: trang_thai["da_ngu"].append(giay))
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
    """Trần 0 = không giới hạn. Không tự ý làm chậm khi chưa ai yêu cầu."""
    _cau_hinh(monkeypatch, batch=1, rpm=0)

    mod.translate_cues(_cues(3), dem_luot_gan_day=lambda: 999)

    assert dong_ho["da_ngu"] == []


def test_duoi_tran_thi_chay_thang(dong_ho, monkeypatch) -> None:
    _cau_hinh(monkeypatch, batch=1, rpm=15)

    mod.translate_cues(_cues(3), dem_luot_gan_day=lambda: 2)

    assert dong_ho["da_ngu"] == []


def test_cham_tran_thi_cho_roi_kiem_lai(dong_ho, monkeypatch) -> None:
    """Đếm từ nguồn chung: chờ tới khi con số tụt xuống dưới trần.

    Giả lập bộ đếm tụt dần — như khi các lượt cũ rơi khỏi cửa sổ 60 giây, hoặc
    khi tiến trình worker khác dịch xong.
    """
    _cau_hinh(monkeypatch, batch=1, rpm=15)
    dem = iter([15, 15, 3, 3, 3, 3])

    mod.translate_cues(_cues(2), dem_luot_gan_day=lambda: next(dem))

    assert len(dong_ho["da_ngu"]) == 2
    assert all(g > 0 for g in dong_ho["da_ngu"])


def test_dem_tu_nguon_chung_chu_khong_tu_dem_trong_bo_nho(dong_ho, monkeypatch) -> None:
    """Chốt chặn cho đúng lỗi cũ.

    Bộ đếm chung luôn báo ĐÃ CHẠM TRẦN dù tiến trình này chưa gọi lượt nào —
    đúng tình huống một worker khác đang dịch video khác. Bản cũ đếm trong RAM
    sẽ thấy 0 và bắn thẳng; bản mới phải chờ.
    """
    _cau_hinh(monkeypatch, batch=1, rpm=15)
    lan_goi = {"n": 0}

    def _dem():
        lan_goi["n"] += 1
        #: Ba lần đầu vẫn kẹt trần, sau đó tiến trình kia dịch xong.
        return 15 if lan_goi["n"] <= 3 else 0

    mod.translate_cues(_cues(1), dem_luot_gan_day=_dem)

    assert dong_ho["da_ngu"], "phải chờ dù tiến trình này chưa gọi lượt nào"


def test_khong_cho_vo_han_khi_tran_khong_bao_gio_tut(dong_ho, monkeypatch) -> None:
    """Bộ đếm kẹt trần mãi (hạn mức NGÀY đã hết) thì không được treo vĩnh viễn.

    Chờ tới ngưỡng rồi thôi — chốt chặn trần ngày ở tầng tasks mới là chỗ dừng
    hẳn, giãn nhịp không phải chỗ giải quyết chuyện đó.
    """
    _cau_hinh(monkeypatch, batch=1, rpm=15)

    mod.translate_cues(_cues(1), dem_luot_gan_day=lambda: 999)

    assert sum(dong_ho["da_ngu"]) <= mod.CHO_TOI_DA_GIAY + 0.01


def test_khong_tiem_bo_dem_thi_khong_gian_nhip(dong_ho, monkeypatch) -> None:
    """Script chạy tay không có DB — chạy thẳng, không phải dựng bộ đếm giả."""
    _cau_hinh(monkeypatch, batch=1, rpm=15)

    mod.translate_cues(_cues(3))

    assert dong_ho["da_ngu"] == []
