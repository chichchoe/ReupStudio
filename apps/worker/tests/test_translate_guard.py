"""LLM trả sai số dòng là lỗi âm thầm nguy hiểm nhất — phải có chốt chặn."""

from __future__ import annotations

from src.errors import TranslateError
from src.pipeline.cues import Cue
from src.pipeline.translate import _translate_with_guard, chunk


class _CountMismatchTranslator:
    """Luôn trả thiếu một dòng."""

    def __init__(self) -> None:
        self.calls = 0

    def translate_batch(self, texts, *, tone, glossary):
        self.calls += 1
        if len(texts) == 1:  # fallback từng dòng thì trả đúng
            return ["OK"]
        return ["thiếu"] * (len(texts) - 1)


class _AlwaysFailTranslator:
    def translate_batch(self, texts, *, tone, glossary):
        raise TranslateError("hết hạn mức")


def test_chunk_chia_dung() -> None:
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert chunk([], 3) == []


def test_sai_so_dong_thi_fallback_tung_dong() -> None:
    translator = _CountMismatchTranslator()
    out = _translate_with_guard(translator, ["a", "b", "c"], "doi_thuong", {})
    assert len(out) == 3
    assert out == ["OK", "OK", "OK"]
    assert translator.calls >= 3  # 2 lần thử lô + 3 lần từng dòng


def test_loi_hoan_toan_thi_giu_nguyen_text_goc() -> None:
    out = _translate_with_guard(_AlwaysFailTranslator(), ["a", "b"], "doi_thuong", {})
    assert out == ["a", "b"]  # thà giữ tiếng Trung còn hơn mất dòng


def test_cue_with_text_khong_doi_timestamp() -> None:
    cue = Cue(0, 1.0, 2.0, "中文")
    new = cue.with_text("tiếng Việt")
    assert (new.start, new.end, new.i) == (1.0, 2.0, 0)
    assert new.text == "tiếng Việt"
