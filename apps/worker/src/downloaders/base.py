"""Interface chung cho mọi downloader.

Thêm nền tảng mới = thêm một file trong thư mục này, không sửa chỗ khác.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reup_core.enums import SourcePlatform


@dataclass
class DownloadResult:
    path: Path
    #: ID thật lấy từ nền tảng (khác ID tạm khi link là dạng rút gọn).
    source_video_id: str
    title: str | None = None
    description: str | None = None
    author: str | None = None
    view_count: int | None = None
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    raw_meta: dict[str, Any] = field(default_factory=dict)


class BaseDownloader(ABC):
    platform: SourcePlatform

    @abstractmethod
    def download(self, url: str, dest_dir: Path, *, progress_cb=None) -> DownloadResult:
        """Tải video về ``dest_dir``.

        ``progress_cb(percent: int)`` được gọi trong lúc tải nếu có.
        """
