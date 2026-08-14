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
        def __init__(self):
            self.usage = LlmUsage(model="model-gia")

        def translate_batch(self, texts, *, tone, glossary):
            self.usage.add(prompt_tokens=5, completion_tokens=5, total_tokens=12)
            return [f"vi:{t}" for t in texts]

    monkeypatch.setattr("src.pipeline.translate.get_translator", lambda model=None: TranslatorGia())

    cues = [Cue(i, i, i + 1, f"câu {i}") for i in range(5)]
    ra = translate_cues(cues, on_usage=nhan_duoc.append)

    assert len(ra) == 5
    assert len(nhan_duoc) == 1
    assert nhan_duoc[0].total_tokens == 12
    assert nhan_duoc[0].model == "model-gia"


def test_moi_lo_bao_usage_mot_lan(monkeypatch) -> None:
    """Báo theo TỪNG LÔ chứ không gộp cuối: cần biết mốc thời gian từng lượt
    để đếm lượt/phút cho đúng."""
    dem: list[LlmUsage] = []

    class TranslatorGia:
        def __init__(self):
            self.usage = LlmUsage(model="m")

        def translate_batch(self, texts, *, tone, glossary):
            self.usage.add(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            return [f"vi:{t}" for t in texts]

    monkeypatch.setattr("src.pipeline.translate.get_translator", lambda model=None: TranslatorGia())
    monkeypatch.setattr("src.pipeline.translate.get_settings", lambda: _cau_hinh_lo(2))

    cues = [Cue(i, i, i + 1, f"câu {i}") for i in range(5)]
    translate_cues(cues, on_usage=dem.append)

    assert len(dem) == 3  # 5 câu, lô 2 -> 3 lô


def _cau_hinh_lo(size: int):
    from src.config import Settings

    return Settings(_env_file=None, llm_batch_size=size)
