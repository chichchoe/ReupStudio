"""Thư viện giọng: cổng chất lượng đoạn mẫu và hằng số dùng chung.

Vì sao cổng chất lượng quan trọng đến thế: giọng clone chép lại đoạn mẫu —
kể cả nhiễu, tiếng vọng và cái đều đều của giọng máy. Chất lượng bản lồng
tiếng không bao giờ vượt được chất lượng đoạn mẫu, và tham số sinh của Fish
KHÔNG mở ra ngoài API. Nên đoạn mẫu là cần gạt chất lượng DUY NHẤT.

Bốn thứ đo được bằng số thì phải đo trước khi lưu, chứ không để người dùng
phát hiện sau khi đã lồng tiếng cả video.

Hàm THUẦN, nhận số đo chứ không chạm file — test được mà không cần file wav
thật (thứ CLAUDE.md cấm commit vào repo).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Câu đọc thử CỐ ĐỊNH cho mọi giọng. Cố định thì bấm lần lượt mới so được
#: sòng phẳng — mỗi giọng một câu khác thì nghe xong không biết khác nhau do
#: giọng hay do câu. Không xuống dòng: một số nhà cung cấp đọc dấu xuống dòng
#: thành khoảng lặng dài.
CAU_NGHE_THU = (
    "Xin chào, đây là giọng đọc thử của ReupStudio. "
    "Mọi giọng trong thư viện đều đọc đúng câu này, để bạn nghe lần lượt và so cho công bằng."
)

#: Đoạn dựng tạm bằng Edge cho nguồn ``tam_tu_may``. Phải DÀI HƠN câu đọc thử:
#: nó được dùng làm ĐOẠN MẪU, mà mẫu dưới 7 giây thì ăn cảnh báo "ngắn quá"
#: ngay khi vừa tạo.
DOAN_MAU_TAM = (
    "Xin chào, đây là đoạn giọng mẫu tạm do máy dựng. "
    "Bạn có thể dùng tạm để chạy thử, nhưng nên thay bằng một đoạn thu thật khi có điều kiện, "
    "vì chất lượng bản lồng tiếng không bao giờ vượt được chất lượng đoạn mẫu."
)

#: Ngắn hơn thì không đủ đặc trưng giọng để nhân bản.
NGAN_NHAT_GIAY = 7.0
#: Dài hơn chỉ tổ phí ngữ cảnh và làm chậm mỗi câu, không thêm đặc trưng nào.
DAI_NHAT_GIAY = 15.0
#: Đỉnh từ mức này trở lên là đã cắt ngọn sóng — nghe ra tiếng rè.
DINH_VO_TIENG = 0.99
#: RMS dưới mức này thì gần như im lặng.
RMS_QUA_NHO = 0.02
#: Quá nửa chừng này là im lặng thì phần giọng thật còn quá ít.
IM_LANG_TOI_DA = 0.40


@dataclass(frozen=True)
class DoAmThanh:
    """Số đo của một đoạn mẫu, lấy từ ffmpeg."""

    do_dai_giay: float
    #: Biên độ trung bình 0–1. Nhỏ quá nghĩa là thu quá nhỏ tiếng.
    rms: float
    #: Biên độ đỉnh 0–1. Chạm 1,0 nghĩa là vỡ tiếng.
    dinh: float
    #: Tỉ lệ thời gian im lặng 0–1.
    ti_le_im_lang: float


@dataclass(frozen=True)
class CanhBao:
    """Một điều chưa ổn ở đoạn mẫu. ``ma`` để giao diện lọc, ``thong_diep`` cho người đọc."""

    ma: str
    thong_diep: str


def kiem_chat_luong(do: DoAmThanh) -> list[CanhBao]:
    """Soi đoạn mẫu, trả danh sách cảnh báo. Rỗng nghĩa là ổn.

    CẢNH BÁO chứ không CHẶN: người dùng có thể cố tình dùng mẫu lạ (giọng thì
    thầm, giọng trẻ con). Nhưng phải nói ra TRƯỚC khi lưu.

    Liệt kê HẾT trong một lần chứ không dừng ở lỗi đầu: báo một lỗi rồi dừng
    thì người dùng sửa xong lại ăn cảnh báo tiếp — ba vòng thu lại mới xong.

    Mỗi thông điệp phải nói CÁCH SỬA. "Mẫu không đạt" là câu vô dụng.
    """
    ra: list[CanhBao] = []

    if do.do_dai_giay < NGAN_NHAT_GIAY:
        ra.append(
            CanhBao(
                "qua_ngan",
                f"Đoạn mẫu chỉ {do.do_dai_giay:.1f} giây — dưới {NGAN_NHAT_GIAY:.0f} giây thì "
                "không đủ đặc trưng giọng. Thu lại dài hơn, khoảng 3–4 câu liền mạch.",
            )
        )
    elif do.do_dai_giay > DAI_NHAT_GIAY:
        ra.append(
            CanhBao(
                "qua_dai",
                f"Đoạn mẫu {do.do_dai_giay:.1f} giây — dài hơn {DAI_NHAT_GIAY:.0f} giây chỉ tốn "
                "thêm thời gian mỗi câu mà không hay hơn. Cắt bớt còn 10–15 giây.",
            )
        )

    if do.dinh >= DINH_VO_TIENG:
        ra.append(
            CanhBao(
                "vo_tieng",
                "Tiếng bị vỡ do thu quá to (chạm đỉnh). Thu lại nhỏ hơn hoặc để micro xa "
                "miệng thêm một gang tay — tiếng vỡ sẽ bị chép sang mọi câu.",
            )
        )

    if do.rms < RMS_QUA_NHO:
        ra.append(
            CanhBao(
                "qua_nho",
                "Tiếng quá nhỏ, gần như im lặng. Thu lại gần micro hơn, hoặc kiểm tra xem có "
                "chọn nhầm micro không.",
            )
        )

    if do.ti_le_im_lang > IM_LANG_TOI_DA:
        ra.append(
            CanhBao(
                "nhieu_im_lang",
                f"{do.ti_le_im_lang:.0%} đoạn mẫu là im lặng — phần giọng thật còn quá ít. "
                "Cắt bỏ khoảng lặng đầu cuối, hoặc nói liền mạch hơn.",
            )
        )

    return ra


def tham_so_goi(
    *, nha_cung_cap: str, ma_giong: str, model: str, giong_id: str
) -> dict[str, str]:
    """Một dòng ``giong_doc`` -> tham số ghi vào ``video.process_config``.

    Bốn nhà cung cấp, bốn dạng khác nhau:

    - ``edge``: chỉ cần mã giọng, không có model;
    - ``gemini`` / ``openrouter``: mã giọng + model;
    - ``fish_mlx``: KHÔNG có mã giọng và KHÔNG có model — giọng đến từ đoạn mẫu
      (Fish S2-Pro không có trường ``voice``), worker tra đoạn mẫu theo
      ``giong_doc_id``.

    Luôn ghi ``giong_doc_id``: đó là thứ duy nhất trỏ ngược về dòng bảng, nhờ
    nó mà đổi tên giọng hay sửa đoạn mẫu không làm hỏng video đã xếp hàng.

    ``tts_model`` chỉ có mặt khi thật sự có model — để lọt khoá rỗng vào
    ``process_config`` là worker đọc ra chuỗi rỗng rồi gửi nó đi làm tên model.
    """
    ra = {
        "tts_provider": nha_cung_cap,
        "giong_doc": ma_giong or "",
        "giong_doc_id": giong_id,
    }
    if model:
        ra["tts_model"] = model
    return ra
