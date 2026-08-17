"""Dịch hỏng hết thì phải DỪNG, không được trả về bản "dịch" vẫn nguyên tiếng gốc.

Quan sát ngày 2026-08-16: Google gỡ ``gemini-2.5-flash``, mọi lượt gọi trả 404.
Đường lui "dịch từng dòng, hỏng thì giữ nguyên" giữ lại cả 133 câu tiếng Trung,
rồi bước dịch báo XONG. Video đi tiếp qua lồng tiếng, xoá chữ cứng, render —
người dùng mở lên mới thấy phụ đề vẫn là tiếng Trung.

Giữ nguyên MỘT dòng hỏng thì hợp lý (còn hơn mất dòng). Giữ nguyên gần hết thì
không phải "vài dòng lẻ" mà là cả bước đã hỏng.
"""

from __future__ import annotations

import pytest

from src.errors import TranslateError
from src.pipeline.cues import Cue
from src.pipeline.translate import translate_cues


class TranslatorHongHet:
    """Mọi lượt gọi đều hỏng vì lỗi TẠM THỜI (mạng chập chờn, timeout).

    Cố ý không dùng lỗi 404: lỗi vĩnh viễn giờ dừng ngay từ lô đầu, không đi
    tới đường lui từng-dòng. Ở đây phải đi hết đường lui đó để kiểm cái chốt
    cuối — giữ nguyên gần hết tiếng gốc thì KHÔNG được coi là xong.
    """

    on_usage = None

    def translate_batch(self, texts, *, tone, glossary):
        raise TranslateError("Không gọi được LLM (https://...): timeout")

    def generate_title(self, transcript, *, count=5):
        return []


class TranslatorHongMotDong:
    """Đúng MỘT câu làm hỏng cả lô — trường hợp phải CHO QUA.

    Lô nào chứa câu đó cũng hỏng, nên `_translate_with_guard` chia đôi dần rồi
    xuống dịch từng dòng; lúc đó chỉ mình câu đó hỏng, các câu khác dịch được.
    Đây là hình dạng thật của một dòng có ký tự làm model nghẹn.
    """

    on_usage = None

    def __init__(self, hong_o: str) -> None:
        self._hong_o = hong_o

    def translate_batch(self, texts, *, tone, glossary):
        if self._hong_o in texts:
            raise TranslateError("một dòng lỗi vặt")
        return [f"[vi] {t}" for t in texts]


def _cues(n: int) -> list[Cue]:
    return [Cue(i, i * 2.0, i * 2.0 + 1.8, f"câu {i}") for i in range(n)]


def test_hong_het_thi_nem_loi_chu_khong_tra_ve_tieng_goc(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.pipeline.translate.get_translator", lambda *a, **k: TranslatorHongHet()
    )

    with pytest.raises(TranslateError, match="Không dịch được"):
        translate_cues(_cues(20))


def test_thong_bao_loi_noi_ro_bao_nhieu_cau_hong(monkeypatch) -> None:
    """Người dùng phải biết vì sao dừng, không phải đoán."""
    monkeypatch.setattr(
        "src.pipeline.translate.get_translator", lambda *a, **k: TranslatorHongHet()
    )

    with pytest.raises(TranslateError) as loi:
        translate_cues(_cues(12))

    assert "12/12" in str(loi.value)
    assert "timeout" in str(loi.value)


def test_mot_dong_hong_van_cho_qua(monkeypatch) -> None:
    """Giữ nguyên một dòng còn hơn mất dòng — đừng chặt tay quá."""
    monkeypatch.setattr(
        "src.pipeline.translate.get_translator",
        lambda *a, **k: TranslatorHongMotDong("câu 3"),
    )

    ra = translate_cues(_cues(20))

    assert len(ra) == 20
    assert ra[3].text == "câu 3"  # giữ nguyên
    assert ra[0].text == "[vi] câu 0"


def test_dich_binh_thuong_khong_bi_dung(monkeypatch) -> None:
    class Tot:
        on_usage = None

        def translate_batch(self, texts, *, tone, glossary):
            return [f"[vi] {t}" for t in texts]

    monkeypatch.setattr("src.pipeline.translate.get_translator", lambda *a, **k: Tot())

    ra = translate_cues(_cues(30))

    assert [c.text for c in ra][:2] == ["[vi] câu 0", "[vi] câu 1"]


class TranslatorModelBiGo:
    """Model bị nhà cung cấp gỡ — chia nhỏ lô bao nhiêu cũng hỏng y hệt."""

    on_usage = None

    def __init__(self, tin: str = "LLM trả HTTP 404 ... no longer available") -> None:
        self.so_lan_goi = 0
        self._tin = tin

    def translate_batch(self, texts, *, tone, glossary):
        self.so_lan_goi += 1
        raise TranslateError(self._tin, status=404)


def test_model_bi_go_thi_dung_ngay_khong_chia_nho_lo(monkeypatch) -> None:
    """133 câu từng nở ra hàng chục lượt gọi 404 mất 40 giây.

    Kết luận biết được ngay từ lượt đầu, chia đôi lô chỉ tốn thêm thời gian.
    """
    tr = TranslatorModelBiGo()
    monkeypatch.setattr("src.pipeline.translate.get_translator", lambda *a, **k: tr)

    with pytest.raises(TranslateError, match="404"):
        translate_cues(_cues(60))

    #: Hai lượt của lô đầu là đủ; chia đôi rồi từng dòng là hàng chục lượt.
    assert tr.so_lan_goi <= 2, f"gọi {tr.so_lan_goi} lượt cho một lỗi vĩnh viễn"


class _TraLoi404:
    """Thân lỗi 404 thật của OpenRouter — hai biến thể khác hẳn nhau."""

    def __init__(self, than: dict) -> None:
        self._than = than

    def json(self) -> dict:
        return self._than


def test_404_chinh_sach_du_lieu_noi_ro_phai_lam_gi() -> None:
    """Biến thể KHÔNG kèm metadata — gặp thật ngày 2026-08-17 với
    `google/gemini-3.7-flash`. Không bắt riêng thì người dùng nhận nguyên khối
    JSON và không biết phải bấm gì."""
    from src.translator.openai import _goi_y_khi_bi_chan

    goi_y = _goi_y_khi_bi_chan(
        _TraLoi404(
            {
                "error": {
                    "message": "No endpoints available matching your guardrail "
                    "restrictions and data policy. Configure: "
                    "https://openrouter.ai/settings/privacy",
                    "code": 404,
                }
            }
        )
    )

    assert "settings/privacy" in goi_y
    assert "openai/" in goi_y  # chỉ luôn model thay thế dùng được


def test_404_chan_nha_cung_cap_liet_ke_ben_duoc_phep() -> None:
    """Biến thể CÓ metadata — nói rõ bên nào phục vụ, bên nào tài khoản cho phép."""
    from src.translator.openai import _goi_y_khi_bi_chan

    goi_y = _goi_y_khi_bi_chan(
        _TraLoi404(
            {
                "error": {
                    "message": "No allowed providers... Providers serving "
                    "deepseek/deepseek-v3.2: deepseek, fireworks...",
                    "metadata": {"requested_providers": ["openai", "minimax"]},
                }
            }
        )
    )

    assert "openai, minimax" in goi_y


def test_loi_404_khac_thi_khong_doan_bua() -> None:
    """404 vì lý do khác (model gõ sai tên) thì đừng bịa ra lời khuyên sai."""
    from src.translator.openai import _goi_y_khi_bi_chan

    assert _goi_y_khi_bi_chan(_TraLoi404({"error": {"message": "No such model"}})) == ""


def test_thong_bao_doi_chu_van_phai_dung_ngay(monkeypatch) -> None:
    """Chốt "404 thì dừng" phải xét MÃ, không dò chữ trong thông báo.

    Gặp thật ngày 2026-08-17: bản đầu dò chuỗi "HTTP 404"; sau đó thông báo 404
    được viết lại cho dễ hiểu ("Tài khoản OpenRouter không được dùng model
    này…"), mất chuỗi đó, và chốt im lặng thôi ăn — video 111 câu nở ra 111
    lượt gọi đều hỏng y hệt trước khi dừng.
    """
    tr = TranslatorModelBiGo(
        "Tài khoản OpenRouter không được dùng model này: thiết lập quyền riêng tư "
        "đang chặn nhà cung cấp phục vụ nó."
    )
    monkeypatch.setattr("src.pipeline.translate.get_translator", lambda *a, **k: tr)

    with pytest.raises(TranslateError):
        translate_cues(_cues(111))

    assert tr.so_lan_goi <= 2, (
        f"gọi {tr.so_lan_goi} lượt cho một lỗi vĩnh viễn — chốt dừng sớm không ăn"
    )


def test_loi_khong_co_ma_thi_van_thu_lai(monkeypatch) -> None:
    """Lỗi mạng chập chờn (status 0) phải đi hết đường lui, đừng dừng oan."""
    from src.pipeline.translate import _khong_the_thu_lai

    assert _khong_the_thu_lai(TranslateError("timeout")) is False
    assert _khong_the_thu_lai(TranslateError("x", status=500)) is False
    assert _khong_the_thu_lai(TranslateError("x", status=404)) is True
