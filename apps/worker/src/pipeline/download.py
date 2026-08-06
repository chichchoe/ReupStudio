"""Bước tải video. Hàm thuần — không biết gì về Celery."""

from __future__ import annotations

import hashlib
from pathlib import Path

from reup_core.enums import SourcePlatform
from reup_core.logging import get_logger
from reup_core.paths import raw_dir, raw_meta

from ..downloaders import get_downloader
from ..downloaders.base import DownloadResult

log = get_logger(__name__)


def download_video(
    url: str,
    platform: SourcePlatform | str,
    source_video_id: str,
    *,
    progress_cb=None,
) -> DownloadResult:
    dest = raw_dir(str(platform), source_video_id)

    existing = dest / "source.mp4"
    if existing.exists() and existing.stat().st_size > 0:
        log.info("download.skip_existing", path=str(existing))
        return DownloadResult(path=existing, source_video_id=source_video_id)

    downloader = get_downloader(platform)
    result = downloader.download(url, dest, progress_cb=progress_cb)

    import json

    raw_meta(str(platform), source_video_id).write_text(
        json.dumps(result.raw_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("download.done", path=str(result.path), size=result.path.stat().st_size)
    return result


def file_md5(path: Path, chunk_size: int = 1 << 20) -> str:
    """MD5 để chống trùng. Đọc theo khối để không nạp cả file vào RAM."""
    digest = hashlib.md5()
    with path.open("rb") as fh:
        while block := fh.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()
