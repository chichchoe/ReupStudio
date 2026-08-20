"""Dịch lại bản dịch đã có — cả video hoặc chỉ mấy câu người dùng tích.

Vì sao tách khỏi ``tasks/video.py``: file đó đã hơn 1100 dòng và mang cả chuỗi
pipeline chính. Dịch lại là nhánh riêng, chạy trên video ĐÃ dừng ở chỗ duyệt,
không đi qua chuỗi nào.
"""

from __future__ import annotations

from reup_core.db import session_scope
from reup_core.doi_chieu import ghep_theo_thoi_gian, tu_dicts
from reup_core.enums import PipelineStep
from reup_core.logging import get_logger
from reup_core.models import Subtitle, Video
from sqlalchemy import select

from .. import progress as prog
from ..celery_app import app
from ..errors import ReupError
from ..pipeline.cues import cues_from_dicts, cues_to_dicts
from ..pipeline.translate import translate_cues

log = get_logger(__name__)


def gop_giu_cau_sua_tay(cu: list[dict], moi: list[dict]) -> list[dict]:
    """Trộn bản dịch mới vào bản cũ, GIỮ NGUYÊN câu người dùng đã chữa tay.

    Hàm THUẦN, không chạm DB — test được thẳng.

    Ba luật:
    - câu có ``sua_tay`` -> giữ nguyên bản cũ, không đụng tới;
    - câu bản mới có -> lấy chữ mới, GIỮ MỐC THỜI GIAN CŨ (mốc giờ do bước
      nhận dạng và chuẩn hoá tính ra; lấy theo bản dịch mới là mở đường cho
      phụ đề chồng lên nhau);
    - câu bản mới THIẾU -> giữ bản cũ. Model trả thiếu câu là chuyện có thật,
      bỏ luôn thì phụ đề hụt một đoạn mà video vẫn "xong".
    """
    moi_theo_i = {int(c["i"]): c for c in moi}
    ra: list[dict] = []

    for cau in cu:
        i = int(cau["i"])
        if cau.get("sua_tay"):
            ra.append(cau)
            continue
        thay = moi_theo_i.get(i)
        ra.append({**cau, "text": str(thay["text"])} if thay else cau)

    return ra


def _khoa_llm(video) -> dict[str, str]:
    """Khoá/địa chỉ/nhà cung cấp cho ``translate_cues``, đọc từ ``ai_providers``."""
    from .video import _khoa_llm_cho_translate

    return _khoa_llm_cho_translate(video)


@app.task(name="reup.dich_lai")
def dich_lai_task(video_id: str) -> dict:
    """Dịch lại rồi ghi đè bản dịch, trừ câu người dùng đã chữa.

    ``chi_so`` đọc từ ``process_config["dich_lai_chi_so"]`` — API đặt vào đó
    trước khi gửi task, giống cách ``llm_model`` đang đi. Rỗng/không có nghĩa
    là dịch lại TOÀN BỘ.
    """
    with session_scope() as db:
        video = db.get(Video, video_id)
        if video is None:
            raise ReupError(f"Không có video {video_id}")

        config = video.process_config or {}
        chi_so = set(config.get("dich_lai_chi_so") or [])

        vi_row = db.scalar(
            select(Subtitle).where(Subtitle.video_id == video.id, Subtitle.lang == "vi")
        )
        zh_row = db.scalar(
            select(Subtitle).where(Subtitle.video_id == video.id, Subtitle.lang == "zh")
        )
        if vi_row is None or zh_row is None:
            raise ReupError(f"Video {video_id} thiếu phụ đề để dịch lại")

        cu = list(vi_row.cues)
        can_dich = [c for c in cu if not chi_so or int(c["i"]) in chi_so]

        log.info("dich_lai.bat_dau", video_id=video_id, tong=len(cu), can_dich=len(can_dich))
        prog.progress(video_id, PipelineStep.TRANSLATE.value, 5)

        #: Dịch lại từ chữ TIẾNG VIỆT hiện có sang tiếng Việt tốt hơn là vô
        #: nghĩa — phải quay về câu gốc. Ghép lại nguồn theo thời gian vì sau
        #: bước chuẩn hoá, chỉ số hai bên không còn khớp nhau.
        cap = {c.i: c.goc for c in ghep_theo_thoi_gian(tu_dicts(cu), tu_dicts(list(zh_row.cues)))}
        nguon = [
            {
                "i": int(c["i"]),
                "start": float(c["start"]),
                "end": float(c["end"]),
                "text": cap.get(int(c["i"]), ""),
            }
            for c in can_dich
            if cap.get(int(c["i"]))
        ]
        if not nguon:
            raise ReupError("Không tìm được câu gốc tương ứng để dịch lại")

        moi = cues_to_dicts(
            translate_cues(
                cues_from_dicts(nguon),
                model=config.get("llm_model") or None,
                **_khoa_llm(video),
            )
        )

        vi_row.cues = gop_giu_cau_sua_tay(cu, moi)
        vi_row.source = "llm"
        prog.progress(video_id, PipelineStep.TRANSLATE.value, 100)
        log.info("dich_lai.xong", video_id=video_id, doi=len(moi), tong=len(cu))
        ket_qua = {"doi": len(moi), "tong": len(cu)}

    #: Đọc lại giọng cho câu vừa đổi chữ — cơ chế vân tay tự bỏ qua câu không
    #: đổi, nên gọi thẳng chuỗi đọc lại là đủ.
    app.send_task("reup.doc_lai_sau_khi_sua", args=[video_id], queue="download")
    return ket_qua
