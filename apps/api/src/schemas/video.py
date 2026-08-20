from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from reup_core.enums import M1_STEPS, PipelineStep, VideoStatus

#: Giá trị ``job_runs.status`` mà worker ghi ra (``tasks/base.py``). Khai bằng
#: ``Literal`` chứ không phải ``str`` để OpenAPI mang được tập giá trị sang
#: frontend — ``lib/types.ts`` sinh từ đó (luật số 7 CLAUDE.md).
JobRunStatus = Literal["running", "success", "failed"]


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_platform: str
    source_video_id: str
    source_url: str
    source_author: str | None = None
    title_original: str | None = None
    title_vi: str | None = None
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    #: Khai bằng enum, KHÔNG phải ``str``: OpenAPI khi đó mang được tập giá trị
    #: sang frontend, nên ``lib/types.ts`` sinh ra union thay vì ``string``.
    #: Trước đây frontend gõ tay lại hai union này — đúng thứ luật số 7
    #: CLAUDE.md cấm, và không có gì bảo đảm chúng còn khớp backend.
    status: VideoStatus
    current_step: PipelineStep | None = None
    error_message: str | None = None
    flags: dict[str, Any] = Field(default_factory=dict)
    #: Đưa lên cả DANH SÁCH chứ không riêng chi tiết: tab Chờ duyệt cần hiện
    #: model đã dịch và giọng đã đọc ngay trên dòng. Không có nó thì mỗi dòng
    #: phải gọi thêm một lượt /videos/{id}, mà danh sách có bao nhiêu dòng là
    #: bấy nhiêu lượt. Ở đây không có bí mật — chỉ tên model, mã giọng, văn
    #: phong; khoá API nằm trong bảng ``ai_providers`` và không bao giờ ra API.
    process_config: dict[str, Any] = Field(default_factory=dict)
    out_path: str | None = None
    created_at: datetime
    updated_at: datetime

    @property
    def step_index(self) -> int:
        if not self.current_step:
            return 0
        try:
            return [s.value for s in M1_STEPS].index(self.current_step)
        except ValueError:
            return 0


class VideoDetail(VideoOut):
    desc_original: str | None = None
    desc_vi: str | None = None
    hashtags_vi: list[str] | None = None
    fps: float | None = None
    has_audio: bool | None = None
    raw_path: str | None = None


class CreateFromLinks(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=200)
    process_config: dict[str, Any] = Field(default_factory=dict)
    autostart: bool = True


class CreateFromLinksResult(BaseModel):
    created: int
    skipped_duplicate: int
    invalid: list[str] = Field(default_factory=list)
    video_ids: list[uuid.UUID] = Field(default_factory=list)
    #: Link đã có sẵn trong thư viện → id của bản ghi cũ, để FE mở thẳng video đó.
    duplicate_ids: list[uuid.UUID] = Field(default_factory=list)


class VideoUpdate(BaseModel):
    title_vi: str | None = None
    desc_vi: str | None = None
    hashtags_vi: list[str] | None = None


#: MỘT nguồn sự thật cho danh sách bên đọc. Dùng cả ở chỗ nhận yêu cầu
#: (``TranslateRequest``) lẫn chỗ liệt kê cho giao diện
#: (``video_service.cac_giong_doc``).
BEN_DOC_HOP_LE = ("edge", "gemini", "openrouter")
BenDoc = Literal["edge", "gemini", "openrouter"]


class TranslateRequest(BaseModel):
    """Body của ``POST /videos/{id}/translate``.

    ``llm_model`` bỏ trống là hợp lệ — khi đó worker dùng ``LLM_MODEL`` mặc
    định trong cấu hình. Không kiểm model hợp lệ ở đây mà ở tầng service:
    việc phân loại model là logic nghiệp vụ, không phải validate cú pháp.
    """

    llm_model: str | None = None
    #: Nhà cung cấp AI dùng để dịch video này. Bỏ trống thì worker dùng bên nào
    #: đang bật trong bảng ``ai_providers``.
    llm_provider: str | None = None

    #: Bật/tắt xoá chữ cứng và watermark cho RIÊNG video này. Bước này nặng
    #: nhất pipeline (video một tiếng mất hàng tiếng) và không phải video nào
    #: cũng cần, nên phải chọn được từng cái.
    xoa_chu_cung: bool = True

    #: Bên đọc. Danh sách lấy từ ``BEN_DOC`` để KHÔNG lệch với danh sách mà
    #: ``GET /videos/tts-options`` mời người dùng chọn — thêm bên mới mà quên
    #: sửa chỗ này thì giao diện gửi lên bị 422, và màn hình chỉ hiện "lỗi" chứ
    #: không nói tên trường nào sai. Xảy ra thật ngày 2026-08-16 với
    #: ``openrouter``: mọi lượt bấm Dịch đều 422.
    tts_provider: BenDoc = "edge"
    #: Mã giọng của nhà cung cấp đã chọn. Bỏ trống thì worker dùng giọng mặc
    #: định của nhà cung cấp đó.
    giong_doc: str | None = None
    #: Chỉ dùng với ``gemini`` và ``openrouter`` — model TTS cụ thể.
    tts_model: str | None = None


class CauSuaIn(BaseModel):
    """Một câu người dùng vừa sửa. CHỈ chữ — mốc thời gian không cho đổi."""

    i: int
    text: str = Field(min_length=1)


class SuaBanDichIn(BaseModel):
    cues: list[CauSuaIn] = Field(min_length=1)
    #: Đọc lại giọng ngay sau khi lưu. Tắt khi còn muốn sửa tiếp vài câu nữa —
    #: mỗi lần đọc lại là một lượt gọi nhà cung cấp cho từng câu đã đổi.
    doc_lai: bool = True


class GiongDocOut(BaseModel):
    """Một giọng đọc chọn được trên giao diện."""

    ma: str
    ten: str
    gioi_tinh: str


class TtsOptionsOut(BaseModel):
    """Các lựa chọn giọng đọc, nhóm theo nhà cung cấp.

    ``ghi_chu`` nói rõ đánh đổi để người dùng chọn đúng — giấu nó đi thì họ
    chọn Gemini cho video 672 câu rồi hết hạn mức giữa chừng.
    """

    provider: str
    ghi_chu: str
    models: list[str] = Field(default_factory=list)
    giong: list[GiongDocOut] = Field(default_factory=list)
    #: Bên được chọn sẵn, theo ``TTS_PROVIDER`` trong Cấu hình.
    mac_dinh: bool = False
    #: Giọng chọn sẵn — CHỈ điền cho bên mặc định.
    giong_mac_dinh: str = ""


class BulkAction(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    action: Literal["approve", "delete", "retry", "apply_preset", "assign_channels", "mark_posted"]
    payload: dict[str, Any] = Field(default_factory=dict)


class BulkSkip(BaseModel):
    id: str
    reason: str


class BulkResult(BaseModel):
    """Kết quả ``POST /videos/bulk``.

    Trước đây endpoint trả ``dict`` trần nên OpenAPI chỉ mô tả được "một object
    bất kỳ", và frontend phải gõ tay lại interface.

    ``skipped`` LUÔN kèm lý do và giao diện phải hiển thị — video bị bỏ qua âm
    thầm là cách nhanh nhất để người dùng tưởng đã duyệt xong cả lô.
    """

    affected: int
    action: str
    skipped: list[BulkSkip]


class SubtitleCue(BaseModel):
    i: int
    start: float
    end: float
    text: str


class SubtitleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lang: str
    source: str
    edited_by_user: bool
    cues: list[SubtitleCue]


class JobRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: PipelineStep
    status: JobRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    duration_sec: float | None = None
    log: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class CapDoiChieuOut(BaseModel):
    """Một dòng bảng đối chiếu ở màn duyệt bản dịch."""

    i: int
    start: float
    end: float
    dich: str
    #: Câu gốc chồng thời gian, nối bằng " / ". Rỗng khi không có câu nào.
    goc: str
    sua_tay: bool = False
    #: Độ dài THẬT của giọng đã đọc cho câu này, giây. ``None`` khi chưa lồng
    #: tiếng hoặc câu đó thiếu giọng. Dài hơn ``end - start`` nghĩa là TRÀN
    #: sang câu sau — chỗ dòng thời gian phải bôi đỏ.
    giong_giay: float | None = None
    #: Chỗ trống thật sự dùng được — tới lúc câu SAU bắt đầu, không phải tới
    #: lúc câu này kết thúc (bước xếp lịch mượn được khoảng lặng phía sau).
    cho_trong_giay: float = 0.0
    #: Phải đọc nhanh gấp bao nhiêu mới vừa. Chạm 1,5 là đã hết cỡ.
    he_so_toc_do: float = 1.0
    #: Còn tràn bao nhiêu giây sang câu sau sau khi đã ép nhanh hết cỡ.
    tran_giay: float = 0.0


class DichLaiIn(BaseModel):
    """Yêu cầu dịch lại. ``chi_so`` rỗng/không có = dịch lại toàn bộ."""

    chi_so: list[int] | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
