"""Lỗi API với format thống nhất: {"error": {"code", "message", "detail"}}."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFound(ApiError):
    status_code = 404
    code = "NOT_FOUND"


class Conflict(ApiError):
    status_code = 409
    code = "CONFLICT"


class InvalidPresetDefault(Conflict):
    """Thao tác sẽ khiến một ``kind`` preset còn 0 mặc định.

    Bất biến của M2-BE-04: mỗi kind LUÔN có đúng một preset ``is_default=True``.
    M3+ đọc preset mặc định để chạy tự động — 0 mặc định là lỗi runtime.
    """

    code = "INVALID_PRESET_DEFAULT"


class UnsupportedSource(ApiError):
    status_code = 422
    code = "UNSUPPORTED_SOURCE"


class LlmUnavailable(ApiError):
    """Không hỏi được nhà cung cấp LLM: mạng hỏng, quá hạn chờ, hoặc họ trả rác.

    502 chứ không phải 400: lỗi nằm ở chặng API -> nhà cung cấp, request của
    frontend không có gì sai và gửi lại y hệt là hợp lý.

    Tồn tại riêng thay vì dùng ``ApiError`` trần vì frontend cần PHÂN BIỆT
    được ca này với "không có model nào" — trả danh sách rỗng kèm 200 sẽ khiến
    người dùng tưởng key của mình không dùng được model nào và đi sửa nhầm chỗ.
    """

    status_code = 502
    code = "LLM_UNAVAILABLE"


class LlmAuthFailed(LlmUnavailable):
    """Khoá LLM chưa cấu hình, sai, hết hạn hoặc bị từ chối (401/403).

    Mã riêng để frontend dẫn thẳng người dùng tới chỗ điền ``LLM_API_KEY``,
    thay vì mời họ "thử lại sau" — thử lại bao nhiêu lần cũng vẫn hỏng.
    """

    code = "LLM_AUTH_FAILED"


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}},
    )
