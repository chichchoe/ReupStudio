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


class UnsupportedSource(ApiError):
    status_code = 422
    code = "UNSUPPORTED_SOURCE"


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": exc.code, "message": exc.message, "detail": exc.detail}
        },
    )
