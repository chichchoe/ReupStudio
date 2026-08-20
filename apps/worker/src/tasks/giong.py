"""Dựng một giọng cho thư viện: chuẩn hoá -> gõ chữ -> cổng chất lượng -> đọc thử.

Tách ``dung_giong`` (nhận sẵn session) khỏi task Celery để test được phần điều
phối mà không cần Redis.
"""

from __future__ import annotations

from pathlib import Path

from reup_core.db import session_scope
from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.giong import CAU_NGHE_THU, DOAN_MAU_TAM, kiem_chat_luong
from reup_core.logging import get_logger
from reup_core.models import GiongDoc
from reup_core.paths import giong_mau_txt, giong_mau_wav, giong_nghe_thu, giong_tai_len

from ..celery_app import app
from ..errors import ReupError
from ..pipeline.giong_mau import chuan_hoa
from ..pipeline.transcribe import transcribe
from ..tts import lay_provider

log = get_logger(__name__)


def chon_duong_mau(nguon: str) -> str:
    """Lấy đoạn mẫu từ đâu: dựng bằng máy, hay dùng file người dùng tải lên."""
    return "edge" if nguon == NguonGiong.TAM_TU_MAY.value else "tai_len"


def doc_thu(giong: GiongDoc) -> None:
    """Đọc CÂU CỐ ĐỊNH bằng chính giọng này, để nghe so với các giọng khác.

    Cố định câu cho mọi giọng mới so được sòng phẳng — mỗi giọng một câu khác
    thì nghe xong không biết khác nhau do giọng hay do câu.
    """
    dst = giong_nghe_thu(str(giong.id))
    provider = lay_provider(giong.nha_cung_cap, model=giong.model or "")
    provider.doc(CAU_NGHE_THU, dst, giong=giong.ma_giong or str(giong.id))


def _nguon_am_thanh(giong: GiongDoc) -> Path:
    """File âm thanh đầu vào — tải lên sẵn, hoặc dựng tạm bằng Edge."""
    if chon_duong_mau(giong.nguon) != "edge":
        #: Tìm theo ĐÚNG tiền tố ``giong_tai_len`` đặt ra ("goc.<đuôi>"), không
        #: đoán tên khác: lệch một chữ là không bao giờ tìm thấy file, và giọng
        #: nào thêm vào cũng hỏng với lý do "chưa tải file lên".
        thu_muc = giong_tai_len(str(giong.id), "").parent
        tim = sorted(p for p in thu_muc.glob("goc*") if p.is_file())
        if not tim:
            raise ReupError("Chưa có file âm thanh nào được tải lên cho giọng này.")
        return tim[0]

    #: Giọng tạm: dựng bằng Edge ngay tại chỗ để cắm điện là chạy được, nhưng
    #: bảng đánh dấu rõ ``TAM_TU_MAY`` và giao diện ghi "giọng tạm".
    tam = giong_tai_len(str(giong.id), "mp3")
    lay_provider("edge").doc(DOAN_MAU_TAM, tam, giong="vi-VN-HoaiMyNeural")
    return tam


def dung_giong(db, giong_id) -> None:
    """Bốn bước dựng một giọng. Hỏng thì đánh dấu HONG rồi ném lại.

    Không đánh dấu thì giọng treo ở ``DANG_XU_LY`` mãi mãi và người dùng ngồi
    chờ một việc đã chết.
    """
    giong = db.get(GiongDoc, giong_id)
    if giong is None:
        raise ReupError(f"Không có giọng {giong_id}")

    try:
        mau = giong_mau_wav(str(giong.id))
        do = chuan_hoa(
            _nguon_am_thanh(giong),
            mau,
            tu_giay=giong.cat_tu_giay,
            den_giay=giong.cat_den_giay,
        )

        cues = transcribe(mau, language="vi")
        chu = " ".join(c.text.strip() for c in cues).strip()
        if not chu:
            raise ReupError(
                "Whisper không nghe ra chữ nào trong đoạn mẫu — "
                "nhân bản giọng cần cả âm thanh lẫn phần chữ khớp từng chữ."
            )
        #: Lưu số đo, không chỉ dùng rồi vứt: thẻ giọng trên giao diện hiện
        #: độ dài để so nhanh giữa các giọng, và không có nó thì mọi thẻ đều
        #: trống một ô mà không ai biết vì sao.
        giong.do_dai_giay = round(do.do_dai_giay, 2)
        giong.mau_text = chu
        giong_mau_txt(str(giong.id)).write_text(chu, encoding="utf-8")

        #: CẢNH BÁO chứ không chặn (spec C4). Lưu vào DB để giao diện hiện
        #: được ngay trên thẻ giọng.
        giong.canh_bao = [{"ma": c.ma, "thong_diep": c.thong_diep} for c in kiem_chat_luong(do)]

        doc_thu(giong)
        #: Ghi nhà cung cấp THẬT SỰ đã dựng file nghe thử. Đổi nhà cung cấp
        #: giữa chừng mà không ghi thì không ai biết file nghe-thu.wav đang là
        #: của bên nào.
        giong.nghe_thu_bang = giong.nha_cung_cap

        giong.trang_thai = TrangThaiGiong.SAN_SANG.value
        giong.loi = None
        log.info(
            "giong.dung_xong", giong_id=str(giong.id), canh_bao=len(giong.canh_bao), chu=chu[:60]
        )
    except Exception as exc:
        giong.trang_thai = TrangThaiGiong.HONG.value
        giong.loi = str(exc)[:500]
        log.error("giong.dung_hong", giong_id=str(giong_id), error=str(exc)[:200])
        raise


@app.task(name="reup.chuan_bi_giong")
def chuan_bi_giong_task(giong_id: str) -> dict:
    with session_scope() as db:
        dung_giong(db, giong_id)
    return {"giong_id": giong_id}
