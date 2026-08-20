"""Cổng chất lượng đoạn mẫu — mẫu tồi thì MỌI video về sau đều tồi.

Đoạn mẫu là cần gạt chất lượng DUY NHẤT của giọng clone (spec B3: tham số sinh
của Fish không mở ra ngoài API). Vì vậy bốn thứ đo được bằng số thì phải đo
trước khi lưu, chứ không để người dùng phát hiện sau khi đã lồng tiếng cả video.

CẢNH BÁO chứ không CHẶN: người dùng có thể cố tình dùng mẫu lạ (giọng thì thầm,
giọng trẻ con). Nhưng phải nói ra trước khi lưu.

Hàm THUẦN nhận số đo, không chạm file: nhờ vậy test không cần một file wav thật
— thứ mà CLAUDE.md cấm commit vào repo.
"""

from __future__ import annotations

from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.giong import (
    CAU_NGHE_THU,
    DOAN_MAU_TAM,
    CanhBao,
    DoAmThanh,
    kiem_chat_luong,
    tham_so_goi,
)


def _do(
    *,
    do_dai_giay: float = 10.0,
    rms: float = 0.12,
    dinh: float = 0.80,
    ti_le_im_lang: float = 0.15,
) -> DoAmThanh:
    """Số đo của một mẫu TỐT; mỗi test chỉ đổi đúng một chỉ số."""
    return DoAmThanh(do_dai_giay=do_dai_giay, rms=rms, dinh=dinh, ti_le_im_lang=ti_le_im_lang)


def _ma(canh_bao: list[CanhBao]) -> list[str]:
    return [c.ma for c in canh_bao]


class TestKiemChatLuong:
    def test_mau_tot_khong_canh_bao_gi(self) -> None:
        assert kiem_chat_luong(_do()) == []

    def test_ngan_qua(self) -> None:
        assert _ma(kiem_chat_luong(_do(do_dai_giay=6.9))) == ["qua_ngan"]

    def test_dai_qua(self) -> None:
        assert _ma(kiem_chat_luong(_do(do_dai_giay=15.1))) == ["qua_dai"]

    def test_dung_bien_7_va_15_giay_thi_khong_canh_bao(self) -> None:
        #: Ngưỡng là "< 7" và "> 15", đúng biên KHÔNG cảnh báo — nếu không thì
        #: mẫu 15,0 giây do chính ta cắt ra lại bị chính ta chê.
        assert kiem_chat_luong(_do(do_dai_giay=7.0)) == []
        assert kiem_chat_luong(_do(do_dai_giay=15.0)) == []

    def test_dinh_bang_0_99_la_vo_tieng(self) -> None:
        #: Ngưỡng "≥ 0,99" — đúng 0,99 đã là cắt đỉnh.
        assert _ma(kiem_chat_luong(_do(dinh=0.99))) == ["vo_tieng"]
        assert kiem_chat_luong(_do(dinh=0.98)) == []

    def test_rms_qua_nho(self) -> None:
        assert _ma(kiem_chat_luong(_do(rms=0.019))) == ["qua_nho"]
        assert kiem_chat_luong(_do(rms=0.02)) == []

    def test_im_lang_qua_nhieu(self) -> None:
        assert _ma(kiem_chat_luong(_do(ti_le_im_lang=0.41))) == ["nhieu_im_lang"]
        assert kiem_chat_luong(_do(ti_le_im_lang=0.40)) == []

    def test_mau_te_toan_tap_bao_DU_moi_loi(self) -> None:
        #: Báo một lỗi rồi dừng thì người dùng sửa xong lại ăn cảnh báo tiếp —
        #: ba vòng thu lại mới xong. Phải liệt kê hết trong một lần.
        ra = kiem_chat_luong(DoAmThanh(do_dai_giay=3.0, rms=0.005, dinh=1.0, ti_le_im_lang=0.8))
        assert _ma(ra) == ["qua_ngan", "vo_tieng", "qua_nho", "nhieu_im_lang"]

    def test_moi_canh_bao_deu_noi_CACH_SUA(self) -> None:
        #: "Mẫu không đạt" là câu vô dụng. Người dùng phải biết làm gì tiếp.
        ra = kiem_chat_luong(DoAmThanh(do_dai_giay=3.0, rms=0.005, dinh=1.0, ti_le_im_lang=0.8))
        for c in ra:
            assert len(c.thong_diep) >= 20

    def test_mau_rong_hoan_toan(self) -> None:
        #: File 0 byte đo ra toàn số 0. Không được ném lỗi, chỉ cảnh báo.
        ra = kiem_chat_luong(DoAmThanh(do_dai_giay=0.0, rms=0.0, dinh=0.0, ti_le_im_lang=1.0))
        assert "qua_ngan" in _ma(ra) and "qua_nho" in _ma(ra)


class TestCauNgheThu:
    def test_la_MOT_cau_co_dinh_du_dai(self) -> None:
        #: Mọi giọng đọc CÙNG một câu thì bấm lần lượt mới so được. Câu phải đủ
        #: dài để nghe ra ngữ điệu, và không xuống dòng (một số nhà cung cấp
        #: đọc dấu xuống dòng thành khoảng lặng dài).
        assert len(CAU_NGHE_THU) >= 40
        assert "\n" not in CAU_NGHE_THU

    def test_doan_mau_tam_dai_hon_cau_nghe_thu(self) -> None:
        #: `tam_tu_may` dùng đoạn này làm MẪU, mà mẫu dưới 7 giây thì ăn cảnh
        #: báo "ngắn quá" ngay khi vừa tạo.
        assert len(DOAN_MAU_TAM) > len(CAU_NGHE_THU)


class TestThamSoGoi:
    """Một dòng `giong_doc` -> đúng tham số gọi của nhà cung cấp tương ứng."""

    def test_edge_khong_co_model(self) -> None:
        ra = tham_so_goi(
            nha_cung_cap="edge", ma_giong="vi-VN-HoaiMyNeural", model="", giong_id="g1"
        )
        assert ra == {
            "tts_provider": "edge",
            "giong_doc": "vi-VN-HoaiMyNeural",
            "giong_doc_id": "g1",
        }

    def test_gemini_co_model(self) -> None:
        ra = tham_so_goi(
            nha_cung_cap="gemini",
            ma_giong="Kore",
            model="gemini-2.5-flash-preview-tts",
            giong_id="g2",
        )
        assert ra["tts_provider"] == "gemini"
        assert ra["giong_doc"] == "Kore"
        assert ra["tts_model"] == "gemini-2.5-flash-preview-tts"

    def test_openrouter_co_model(self) -> None:
        ra = tham_so_goi(
            nha_cung_cap="openrouter",
            ma_giong="nova",
            model="openai/gpt-audio-mini",
            giong_id="g3",
        )
        assert ra["tts_provider"] == "openrouter"
        assert ra["tts_model"] == "openai/gpt-audio-mini"

    def test_fish_mlx_khong_co_ma_giong_va_khong_co_model(self) -> None:
        #: Fish KHÔNG có trường `voice` (spec B3) — giọng đến từ đoạn mẫu, tra
        #: theo `giong_doc_id`. Để lọt `tts_model` vào đây là gửi tên model của
        #: bên khác sang subprocess MLX.
        ra = tham_so_goi(nha_cung_cap="fish_mlx", ma_giong="", model="", giong_id="g4")
        assert ra == {"tts_provider": "fish_mlx", "giong_doc": "", "giong_doc_id": "g4"}
        assert "tts_model" not in ra


class TestEnum:
    def test_du_bon_nguon_nguoi_dung_da_chot(self) -> None:
        assert {n.value for n in NguonGiong} == {
            "dung_san",
            "tu_thu",
            "cat_tu_file",
            "thue_doc",
            "tam_tu_may",
        }

    def test_ba_trang_thai(self) -> None:
        assert {t.value for t in TrangThaiGiong} == {"dang_xu_ly", "san_sang", "hong"}
