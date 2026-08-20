from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from reup_core.paths import voice_track
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import NotFound
from ..schemas.common import Page, TaskAccepted
from ..schemas.video import (
    BulkAction,
    BulkResult,
    CreateFromLinks,
    CreateFromLinksResult,
    JobRunOut,
    SuaBanDichIn,
    SubtitleOut,
    TranslateRequest,
    TtsOptionsOut,
    VideoDetail,
    VideoOut,
    VideoUpdate,
)
from ..services import task_bridge, video_service

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("", response_model=Page[VideoOut])
def list_videos(
    status: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    items, total = video_service.list_videos(db, status=status, q=q, page=page, limit=limit)
    return Page(items=items, total=total, page=page, limit=limit)


@router.get("/counts")
def counts(db: Session = Depends(get_db)) -> dict[str, int]:
    return video_service.counts_by_status(db)


@router.post("/from-links", response_model=CreateFromLinksResult, status_code=202)
def create_from_links(body: CreateFromLinks, db: Session = Depends(get_db)):
    result = video_service.create_from_links(db, body.urls, body.process_config)
    db.commit()
    if body.autostart:
        for vid in result["video_ids"]:
            task_bridge.start_processing(vid)
    return result


@router.get("/tts-options", response_model=list[TtsOptionsOut])
def tts_options(db: Session = Depends(get_db)):
    """Các giọng đọc chọn được, kèm ĐÁNH ĐỔI của từng nhà cung cấp.

    Khai TRƯỚC ``/{video_id}``: FastAPI khớp route theo THỨ TỰ đăng ký, nên đặt
    sau thì ``/{video_id}`` nuốt mất và trả về lỗi "tts-options không phải UUID".

    Giấu phần đánh đổi đi thì người dùng chọn Gemini cho video 672 câu rồi hết
    hạn mức giữa chừng — mỗi câu là một lượt gọi.

    OpenRouter chỉ hiện khi đã dán khoá: nó có ``openai/gpt-audio`` đọc được
    tiếng nhưng tính TIỀN theo lượt, không có bậc miễn phí.
    """
    return video_service.cac_giong_doc(db)


@router.get("/{video_id}", response_model=VideoDetail)
def get_video(video_id: uuid.UUID, db: Session = Depends(get_db)):
    return video_service.get_video(db, video_id)


@router.patch("/{video_id}", response_model=VideoDetail)
def update_video(video_id: uuid.UUID, body: VideoUpdate, db: Session = Depends(get_db)):
    video = video_service.get_video(db, video_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(video, field, value)
    return video


@router.delete("/{video_id}", status_code=204)
def delete_video(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video_service.soft_delete(db, video_id)
    return Response(status_code=204)


@router.post("/{video_id}/retry", response_model=TaskAccepted, status_code=202)
def retry(video_id: uuid.UUID, from_step: str | None = None, db: Session = Depends(get_db)):
    video_service.prepare_retry(db, video_id)
    # Commit TRƯỚC khi gửi task — nếu không worker chạy gần như ngay lập tức
    # có thể đọc phải trạng thái cũ (SKIPPED/ERROR) và tự bỏ qua toàn bộ
    # chuỗi (xem worker/tasks/base.py). Bắt chước create_from_links ở trên.
    db.commit()
    task_id = task_bridge.retry_from(video_id, from_step)
    return TaskAccepted(task_id=task_id, message="Đã đưa vào hàng đợi xử lý lại")


@router.post("/{video_id}/translate", response_model=TaskAccepted, status_code=202)
def translate(video_id: uuid.UUID, body: TranslateRequest, db: Session = Depends(get_db)):
    """Chạy nửa sau pipeline với model AI người dùng vừa chọn.

    Pipeline dừng ở trạng thái ``review`` sau bước nhận dạng để người dùng
    chọn model (lúc đó đã biết video có bao nhiêu câu thoại). Endpoint này
    khởi động lại — luật số 1 CLAUDE.md: dịch chạy hàng phút nên luôn qua
    Celery, endpoint trả 202 chứ không chờ.
    """
    video_service.request_translate(db, video_id, body.llm_model)
    video_service.luu_tuy_chon_xu_ly(
        db,
        video_id,
        llm_provider=body.llm_provider,
        xoa_chu_cung=body.xoa_chu_cung,
        tts_provider=body.tts_provider,
        giong_doc=body.giong_doc,
        tts_model=body.tts_model,
    )
    # Commit TRƯỚC khi gửi task — worker chạy gần như tức thì, chậm một nhịp
    # là nó đọc phải process_config chưa có model vừa chọn.
    db.commit()
    task_id = task_bridge.translate_video(video_id)
    return TaskAccepted(task_id=task_id, message="Đã đưa vào hàng đợi dịch")


@router.post("/{video_id}/approve", response_model=VideoDetail)
def approve(video_id: uuid.UUID, db: Session = Depends(get_db)):
    return video_service.approve(db, video_id)


@router.post("/bulk", response_model=BulkResult)
def bulk(body: BulkAction, db: Session = Depends(get_db)):
    return video_service.bulk_action(db, body.ids, body.action, body.payload)


@router.post("/{video_id}/approve-dub", response_model=TaskAccepted, status_code=202)
def approve_dub(video_id: uuid.UUID, db: Session = Depends(get_db)):
    """Duyệt bản dịch và giọng đọc, cho chạy tiếp chặng cuối.

    Chặng cuối là phần nặng nhất (xoá chữ cứng rồi render). Commit TRƯỚC khi
    gửi task — worker chạy gần như tức thì.
    """
    video_service.duyet_ban_dich(db, video_id)
    db.commit()

    task_id = task_bridge.tiep_tuc_sau_duyet(video_id)
    return TaskAccepted(task_id=task_id, message="Đã duyệt, đang xử lý hình ảnh")


@router.get("/{video_id}/voice-track")
def voice_track_file(video_id: uuid.UUID, db: Session = Depends(get_db)):
    """Dải tiếng Việt đã khớp thời gian, để nghe thử TRƯỚC khi ghép vào video."""
    video_service.get_video(db, video_id)
    f = voice_track(str(video_id))
    if not f.exists() or f.stat().st_size == 0:
        raise NotFound("Chưa có dải tiếng — bước lồng tiếng chưa chạy xong.")
    return FileResponse(f, media_type="audio/wav", filename=f"loitieng-{video_id}.wav")


@router.put("/{video_id}/subtitles/vi", response_model=SubtitleOut)
def sua_ban_dich(video_id: uuid.UUID, body: SuaBanDichIn, db: Session = Depends(get_db)):
    """Lưu bản dịch người dùng sửa tay, rồi đọc lại giọng cho câu đã đổi.

    Commit TRƯỚC khi gửi task — worker chạy gần như tức thì, chậm một nhịp là
    nó đọc phải bản dịch cũ.
    """
    row = video_service.sua_ban_dich(db, video_id, [c.model_dump() for c in body.cues])
    db.commit()
    if body.doc_lai:
        task_bridge.doc_lai_sau_khi_sua(video_id)
    return row


@router.get("/{video_id}/subtitles", response_model=list[SubtitleOut])
def subtitles(video_id: uuid.UUID, lang: str | None = None, db: Session = Depends(get_db)):
    video_service.get_video(db, video_id)
    return video_service.get_subtitles(db, video_id, lang)


@router.get("/{video_id}/job-runs", response_model=list[JobRunOut])
def job_runs(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video_service.get_video(db, video_id)
    return video_service.get_job_runs(db, video_id)


@router.get("/{video_id}/preview")
def preview_file(video_id: uuid.UUID, db: Session = Depends(get_db)):
    """Video NGUỒN để xem ở hai chỗ dừng duyệt, trước khi có bản render.

    ``FileResponse`` hỗ trợ range request nên thẻ ``<video>`` tua được mà
    không phải tải hết file.
    """
    f = video_service.duong_dan_xem_truoc(db, video_id)
    return FileResponse(f, media_type="video/mp4", filename=f"preview-{video_id}.mp4")


@router.get("/{video_id}/file")
def download_file(video_id: uuid.UUID, db: Session = Depends(get_db)):
    """Tải bản render cuối cùng."""
    video = video_service.get_video(db, video_id)
    if not video.out_path or not Path(video.out_path).exists():
        raise NotFound("Video chưa render xong hoặc file đã bị xoá")
    return FileResponse(
        video.out_path,
        media_type="video/mp4",
        filename=f"{video.title_vi or video.source_video_id}.mp4",
    )
