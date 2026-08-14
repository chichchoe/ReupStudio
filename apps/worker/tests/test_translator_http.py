"""Lớp gọi LLM qua HTTP: đổi nhà cung cấp bằng cấu hình, chịu được 429.

Hai điều bộ test này khoá:

1. **Địa chỉ lấy từ cấu hình, không hardcode.** Gemini, Groq, OpenRouter,
   DeepSeek đều nói đúng giao thức ``/chat/completions`` của OpenAI — đổi nhà
   cung cấp chỉ nên tốn 3 dòng ``.env``, không sửa code.
2. **429 phải retry có chờ.** Bậc miễn phí chặn theo phút (Gemini ~10–15
   lượt/phút, Groq 6.000 token/phút). Một video dài chia thành nhiều lô dịch
   sẽ đụng trần giữa chừng; không retry thì hỏng cả job vì một lỗi tạm thời.
"""

from __future__ import annotations

import httpx
import pytest

from src.errors import TranslateError
from src.translator import openai as openai_mod


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "http://x"),
                response=httpx.Response(self.status_code),
            )

    def json(self):
        return self._payload


def _ok(noi_dung: str) -> _Response:
    return _Response(200, {"choices": [{"message": {"content": noi_dung}}]})


@pytest.fixture
def gia_lap(monkeypatch):
    """Thay httpx.Client bằng bản giả, ghi lại URL đã gọi và trả lời theo hàng đợi."""
    ghi_nhan: dict = {"urls": [], "cho": []}
    hang_doi: list[_Response] = []

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            ghi_nhan["urls"].append(url)
            ghi_nhan.setdefault("headers", headers)
            return hang_doi.pop(0)

    monkeypatch.setattr(openai_mod.httpx, "Client", FakeClient)
    monkeypatch.setattr(openai_mod, "_sleep", lambda giay: ghi_nhan["cho"].append(giay))
    ghi_nhan["hang_doi"] = hang_doi
    return ghi_nhan


def _cau_hinh(monkeypatch, **kw):
    """Cấu hình cô lập hoàn toàn khỏi máy đang chạy.

    ``_env_file=None`` bắt buộc: không có nó, ``Settings`` đọc file ``.env``
    thật của lập trình viên, và bài test "mặc định là OpenAI" sẽ đỏ hay xanh
    tuỳ người chạy đang cấu hình nhà cung cấp nào — loại test tệ nhất, vì nó
    báo động sai ở máy này và im lặng bỏ sót ở máy khác.
    """
    from src.config import Settings

    mac_dinh = {"llm_api_key": "khoa-gia", "llm_model": "model-gia"}
    monkeypatch.setattr(
        openai_mod, "get_settings", lambda: Settings(_env_file=None, **{**mac_dinh, **kw})
    )


# --- Địa chỉ lấy từ cấu hình -------------------------------------------


def test_goi_dung_dia_chi_theo_llm_base_url(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch, llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai")
    gia_lap["hang_doi"].append(_ok('["Xin chào"]'))

    openai_mod.OpenAITranslator().translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert gia_lap["urls"] == [
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    ]


def test_dau_gach_cheo_thua_o_cuoi_khong_lam_hong_dia_chi(gia_lap, monkeypatch) -> None:
    """Địa chỉ Gemini trong tài liệu có ``/`` ở cuối — dán nguyên vào .env
    không được sinh ra ``//chat/completions``."""
    _cau_hinh(monkeypatch, llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    gia_lap["hang_doi"].append(_ok('["Xin chào"]'))

    openai_mod.OpenAITranslator().translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert "//chat/completions" not in gia_lap["urls"][0]


def test_khong_cau_hinh_thi_van_dung_openai_nhu_cu(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_ok('["Xin chào"]'))

    openai_mod.OpenAITranslator().translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert gia_lap["urls"][0] == "https://api.openai.com/v1/chat/completions"


# --- Chịu được 429 -----------------------------------------------------


def test_gap_429_thi_cho_roi_goi_lai(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].extend([_Response(429), _ok('["Xin chào"]')])

    ket_qua = openai_mod.OpenAITranslator().translate_batch(
        ["你好"], tone="doi_thuong", glossary={}
    )

    assert ket_qua == ["Xin chào"]
    assert len(gia_lap["urls"]) == 2
    assert gia_lap["cho"], "phải chờ trước khi gọi lại, không được nện liên tiếp"


def test_moi_lan_thu_lai_cho_lau_hon_lan_truoc(gia_lap, monkeypatch) -> None:
    """Chờ tăng dần — trần của bậc miễn phí tính theo phút, gọi lại ngay lập
    tức chỉ tốn thêm một lượt bị từ chối."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].extend([_Response(429), _Response(429), _ok('["Xin chào"]')])

    openai_mod.OpenAITranslator().translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert gia_lap["cho"] == sorted(gia_lap["cho"])
    assert gia_lap["cho"][1] > gia_lap["cho"][0]


def test_ton_trong_retry_after_cua_nha_cung_cap(gia_lap, monkeypatch) -> None:
    """Nhà cung cấp nói rõ phải chờ bao lâu thì nghe theo, đừng tự đoán."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].extend([_Response(429, headers={"Retry-After": "7"}), _ok('["Xin chào"]')])

    openai_mod.OpenAITranslator().translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert gia_lap["cho"][0] == 7


def test_het_luot_thu_lai_thi_bao_loi_ro_la_do_qua_han_muc(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].extend([_Response(429)] * 10)

    with pytest.raises(TranslateError) as loi:
        openai_mod.OpenAITranslator().translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert "429" in str(loi.value) or "hạn mức" in str(loi.value)


def test_loi_400_khong_retry_vi_goi_lai_cung_hong(gia_lap, monkeypatch) -> None:
    """Sai tên model hay sai key thì gọi lại bao nhiêu lần cũng thế — báo ngay."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].extend([_Response(400), _ok('["Xin chào"]')])

    with pytest.raises(TranslateError):
        openai_mod.OpenAITranslator().translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert len(gia_lap["urls"]) == 1


def test_khong_bao_gio_ghi_khoa_api_vao_thong_bao_loi(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch, llm_api_key="khoa-that-khong-duoc-lo")
    gia_lap["hang_doi"].extend([_Response(400)])

    with pytest.raises(TranslateError) as loi:
        openai_mod.OpenAITranslator().translate_batch(["你好"], tone="doi_thuong", glossary={})

    assert "khoa-that-khong-duoc-lo" not in str(loi.value)
