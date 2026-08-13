"""Schema cho render nhiều nền tảng cùng lúc (M4-BE-02)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from reup_core.enums import Platform


class RenderRequest(BaseModel):
    """Body của ``POST /videos/{id}/render``.

    ``target_platforms`` bắt buộc có ít nhất một phần tử (danh sách rỗng ->
    422 tự động nhờ ``min_length``) và mỗi phần tử phải nằm trong enum
    ``Platform`` (nền tảng lạ -> 422 tự động nhờ kiểu ``list[Platform]``).
    Việc kiểm thêm mỗi nền tảng có dòng ``platform_limits`` tương ứng hay
    không nằm ở tầng service, vì đó là logic nghiệp vụ cần đọc DB.
    """

    target_platforms: list[Platform] = Field(min_length=1)
    preset_overrides: dict[str, Any] = Field(default_factory=dict)


class RenderVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    video_id: uuid.UUID
    target_platform: str
    part_index: int
    part_total: int
    out_path: str | None = None
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    file_size: int | None = None
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    qc_passed: bool | None = None
    qc_report: dict[str, Any] | None = None
