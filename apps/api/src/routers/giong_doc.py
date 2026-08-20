"""Thư viện giọng — chỗ duy nhất quản mọi giọng đọc.

Router chỉ validate rồi gọi service (luật ba lớp CLAUDE.md).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from reup_core.paths import giong_nghe_thu
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import NotFound
from ..schemas.common import TaskAccepted
from ..schemas.giong_doc import GiongDocOut, SuaGiongIn
from ..services import giong_doc_service, task_bridge

router = APIRouter(prefix="/giong-doc", tags=["giong-doc"])


@router.get("", response_model=list[GiongDocOut])
def danh_sach(db: Session = Depends(get_db)):
    """Mọi giọng: dựng sẵn của Edge/Gemini/OpenRouter LẪN giọng đã clone."""
    ra = []
    for g in giong_doc_service.danh_sach(db):
        #: Kiểm FILE chứ không chỉ đọc trạng thái dòng — xem docstring
        #: ``giong_doc_service.co_nghe_thu``.
        muc = GiongDocOut.model_validate(g)
        ra.append(muc.model_copy(update={"co_nghe_thu": giong_doc_service.co_nghe_thu(g.id)}))
    return ra


@router.post("", response_model=TaskAccepted, status_code=202)
async def tao(
    ten: str = Form(...),
    nguon: str = Form(...),
    nha_cung_cap: str = Form("fish_mlx"),
    ghi_chu: str = Form(""),
    cat_tu_giay: float | None = Form(None),
    cat_den_giay: float | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """Thêm giọng mới. Trả 202 — dựng giọng mất vài chục giây, chạy nền.

    Commit TRƯỚC khi gửi task: worker chạy gần như tức thì, chậm một nhịp là
    nó đọc phải dòng chưa có.
    """
    giong = giong_doc_service.tao(
        db,
        ten=ten,
        nguon=nguon,
        nha_cung_cap=nha_cung_cap,
        ghi_chu=ghi_chu,
        cat_tu_giay=cat_tu_giay,
        cat_den_giay=cat_den_giay,
        co_file=file is not None,
    )
    if file is not None:
        giong_doc_service.luu_file_tai_len(giong.id, file.filename or "tai-len", await file.read())
    db.commit()

    task_id = task_bridge.chuan_bi_giong(giong.id)
    return TaskAccepted(task_id=task_id, message=f"Đang dựng giọng “{ten}”")


@router.get("/{giong_id}/nghe-thu")
def nghe_thu(giong_id: uuid.UUID, db: Session = Depends(get_db)):
    """Câu đọc thử CỐ ĐỊNH — mọi giọng đọc cùng câu để so cho sòng phẳng."""
    giong_doc_service.lay(db, giong_id)
    f = giong_nghe_thu(str(giong_id))
    if not f.exists() or f.stat().st_size == 0:
        raise NotFound("Giọng này chưa dựng xong hoặc dựng hỏng — chưa có gì để nghe.")
    return FileResponse(f, media_type="audio/wav", filename=f"nghe-thu-{giong_id}.wav")


@router.patch("/{giong_id}", response_model=GiongDocOut)
def sua(giong_id: uuid.UUID, body: SuaGiongIn, db: Session = Depends(get_db)):
    """Đổi tên, ghi chú, đặt mặc định, hoặc chữa lại phần chữ của đoạn mẫu."""
    giong, doc_lai = giong_doc_service.sua(
        db,
        giong_id,
        ten=body.ten,
        ghi_chu=body.ghi_chu,
        mac_dinh=body.mac_dinh,
        mau_text=body.mau_text,
    )
    db.commit()
    #: Sửa phần chữ là đổi đoạn mẫu -> phải mã hoá lại và đọc thử lại, nếu
    #: không thì giọng vẫn theo bản chữ cũ mà giao diện hiện chữ mới.
    if doc_lai:
        task_bridge.chuan_bi_giong(giong_id)
    return giong


@router.delete("/{giong_id}", status_code=204)
def xoa(giong_id: uuid.UUID, db: Session = Depends(get_db)):
    giong_doc_service.xoa(db, giong_id)
    db.commit()


@router.post("/{giong_id}/doc-lai", response_model=TaskAccepted, status_code=202)
def doc_lai(giong_id: uuid.UUID, db: Session = Depends(get_db)):
    """Dựng lại câu đọc thử — dùng khi đổi nhà cung cấp hoặc lần trước hỏng."""
    giong_doc_service.lay(db, giong_id)
    task_id = task_bridge.chuan_bi_giong(giong_id)
    return TaskAccepted(task_id=task_id, message="Đang dựng lại câu đọc thử")
