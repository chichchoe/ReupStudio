"""Đo lượng dùng LLM: mỗi lượt gọi phải đếm được token và số lượt.

Vì sao cần: dịch một video 34 phút (672 câu) mất 3 TIẾNG do liên tục đụng 429
của bậc miễn phí, mà không chỗ nào cho biết đã dùng bao nhiêu, còn bao nhiêu.

Đo ngày 2026-08-14 trên Gemini: API KHÔNG trả về header hạn mức nào
(``x-ratelimit-*``), nên không hỏi được nhà cung cấp. Thứ duy nhất họ trả là
khối ``usage`` trong thân phản hồi — đó là toàn bộ nguyên liệu ta có.

``pipeline/translate.py`` không được chạm DB (luật hai lớp của CLAUDE.md), nên
nó nhận một callback ``on_usage`` do tầng ``tasks/`` tiêm vào; ghi vào
``cost_logs`` là việc của tầng đó.
"""

from __future__ import annotations

import pytest

from src.pipeline.cues import Cue
from src.pipeline.translate import translate_cues
from src.translator import openai as openai_mod
from src.translator.base import LlmUsage


class _Response:
    def __init__(self, payload: dict):
        self.status_code = 200
        self._payload = payload
        self.headers = {}

    def json(self):
        return self._payload


def _tra_loi(noi_dung: str, usage: dict | None) -> _Response:
    body = {"choices": [{"message": {"content": noi_dung}}]}
    if usage is not None:
        body["usage"] = usage
    return _Response(body)


@pytest.fixture
def gia_lap(monkeypatch):
    hang_doi: list[_Response] = []

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            return hang_doi.pop(0)

    monkeypatch.setattr(openai_mod.httpx, "Client", FakeClient)
    monkeypatch.setattr(openai_mod, "_sleep", lambda giay: None)

    from src.config import Settings

    monkeypatch.setattr(
        openai_mod,
        "get_settings",
        lambda: Settings(_env_file=None, llm_api_key="khoa-gia", llm_model="model-gia"),
    )
    return hang_doi


def test_ghi_lai_token_tu_phan_hoi(gia_lap) -> None:
    gia_lap.append(
        _tra_loi('["Xin chào"]', {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 26})
    )
    t = openai_mod.OpenAITranslator()

    t.translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert t.usage.requests == 1
    assert t.usage.prompt_tokens == 9
    assert t.usage.completion_tokens == 4


def test_lay_total_tokens_nguyen_van_khong_tu_cong_lai(gia_lap) -> None:
    """Gemini trả 9 + 0 != 26 — token suy luận không nằm trong hai ô kia.

    Cộng tay ``prompt + completion`` sẽ đếm hụt và ước tính tiền bị thiếu.
    """
    gia_lap.append(
        _tra_loi('["Xin chào"]', {"prompt_tokens": 9, "completion_tokens": 0, "total_tokens": 26})
    )
    t = openai_mod.OpenAITranslator()

    t.translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert t.usage.total_tokens == 26


def test_cong_don_qua_nhieu_luot_goi(gia_lap) -> None:
    for _ in range(3):
        gia_lap.append(
            _tra_loi(
                '["Xin chào"]', {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 20}
            )
        )
    t = openai_mod.OpenAITranslator()

    for _ in range(3):
        t.translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert t.usage.requests == 3
    assert t.usage.total_tokens == 60


def test_nha_cung_cap_khong_tra_usage_thi_van_dem_duoc_so_luot(gia_lap) -> None:
    """Không phải nhà cung cấp nào cũng trả ``usage``. Thiếu token vẫn phải
    đếm đúng số lượt — hạn mức lượt/phút mới là thứ chặn ta lại."""
    gia_lap.append(_tra_loi('["Xin chào"]', None))
    t = openai_mod.OpenAITranslator()

    t.translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert t.usage.requests == 1
    assert t.usage.total_tokens == 0


def test_translate_cues_bao_usage_ve_cho_goi(monkeypatch) -> None:
    """``pipeline/`` không chạm DB — nó gọi callback, tầng ``tasks/`` tự ghi."""
    nhan_duoc: list[LlmUsage] = []

    class TranslatorGia:
        """Giả một translator thật: mỗi ``translate_batch`` = MỘT lượt gọi HTTP,
        và tự báo qua ``on_usage`` đúng tại chỗ gọi."""

        def __init__(self):
            self.usage = LlmUsage(model="model-gia")
            self.on_usage = None

        def translate_batch(self, texts, *, tone, glossary):
            self.usage.add(prompt_tokens=5, completion_tokens=5, total_tokens=12)
            if self.on_usage:
                self.on_usage(self.usage)
            return [f"vi:{t}" for t in texts]

    monkeypatch.setattr("src.pipeline.translate.get_translator", lambda model=None: TranslatorGia())

    cues = [Cue(i, i, i + 1, f"câu {i}") for i in range(5)]
    ra = translate_cues(cues, on_usage=nhan_duoc.append)

    assert len(ra) == 5
    assert len(nhan_duoc) == 1
    assert nhan_duoc[0].total_tokens == 12
    assert nhan_duoc[0].model == "model-gia"


def test_bao_mot_lan_cho_MOI_LUOT_GOI_khong_phai_moi_lo(monkeypatch) -> None:
    """Lô hỏng nở ra nhiều lượt gọi — bộ đếm phải thấy hết.

    Bài test này thay cho bản cũ "mỗi lô báo một lần". Hợp đồng đó SAI, đo thật
    ngày 2026-08-14 mới lộ: một lô lệch số dòng bị chia đôi rồi dịch từng dòng,
    4 lô sinh ra 189 lượt gọi mà ``cost_logs`` chỉ ghi 4 dòng.
    """
    dem: list[LlmUsage] = []

    class TranslatorHayLech:
        """Trả sai số dòng cho lô lớn -> bị chia đôi -> nhiều lượt gọi hơn số lô."""

        def __init__(self):
            self.usage = LlmUsage(model="m")
            self.on_usage = None

        def translate_batch(self, texts, *, tone, glossary):
            self.usage.add(total_tokens=2)
            if self.on_usage:
                self.on_usage(self.usage)
            if len(texts) > 1:
                return [f"vi:{t}" for t in texts] + ["dòng thừa"]
            return [f"vi:{t}" for t in texts]

    monkeypatch.setattr(
        "src.pipeline.translate.get_translator", lambda model=None: TranslatorHayLech()
    )
    monkeypatch.setattr("src.pipeline.translate.get_settings", lambda: _cau_hinh_lo(4))

    cues = [Cue(i, i, i + 1, f"câu {i}") for i in range(4)]
    translate_cues(cues, on_usage=dem.append)

    #: Một lô duy nhất, nhưng lô đó hỏng nên nở ra nhiều lượt gọi.
    assert len(dem) > 1


def _cau_hinh_lo(size: int):
    from src.config import Settings

    return Settings(_env_file=None, llm_batch_size=size)


def test_bao_usage_theo_TUNG_LUOT_GOI_khong_phai_tung_lo(gia_lap) -> None:
    """Chốt chặn cho lỗi đo được ngày 2026-08-14.

    Một lô lệch số dòng sẽ nở ra nhiều lượt gọi (chia đôi, rồi dịch từng dòng).
    Đo thật: 4 lô sinh 189 lượt gọi, nhưng ``cost_logs`` chỉ ghi 4 dòng vì báo
    theo lô. Hậu quả kép — sổ chi phí hụt gần 50 lần, và bộ giãn nhịp đọc từ
    bảng đó nên KHÔNG kích hoạt lần nào dù đang liên tục bị từ chối 429.

    Bộ đếm phải thấy đúng số lượt gọi HTTP thật.
    """
    for _ in range(3):
        gia_lap.append(
            _tra_loi(
                '["Xin chào"]', {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
            )
        )
    dem: list = []
    t = openai_mod.OpenAITranslator()
    t.on_usage = dem.append

    for _ in range(3):
        t.translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert len(dem) == 3, "mỗi lượt gọi HTTP phải báo đúng một lần"
