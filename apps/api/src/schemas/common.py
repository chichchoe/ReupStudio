from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int


class TaskAccepted(BaseModel):
    task_id: str | None = None
    message: str = "Đã đưa vào hàng đợi"
