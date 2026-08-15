"""Nơi DUY NHẤT được phép ghép đường dẫn file.

Không viết ``os.path.join`` hay f-string ghép path ở bất kỳ chỗ nào khác — khi
đổi cấu trúc lưu trữ chỉ cần sửa file này.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_KEY = "MEDIA_ROOT"


def _goc_repo() -> Path:
    """Thư mục gốc repo, tìm bằng dấu mốc chứ không bằng số cấp thư mục.

    Đếm cấp (``parents[4]``) sẽ sai ngay khi gói được cài vào site-packages.
    """
    here = Path(__file__).resolve()
    for cha in here.parents:
        if (cha / "CLAUDE.md").exists() or (cha / ".git").exists():
            return cha
    #: Không tìm thấy mốc (gói đã cài rời khỏi repo) — rơi về thư mục hiện tại,
    #: đúng như hành vi cũ.
    return Path.cwd()


def media_root() -> Path:
    """Thư mục gốc chứa file media.

    Đường dẫn TƯƠNG ĐỐI được tính từ GỐC REPO, không phải từ thư mục đang đứng.

    Vì sao — quan sát ngày 2026-08-16: ``.env`` đặt ``MEDIA_ROOT=./media``, mà
    API chạy từ ``apps/api`` còn worker chạy từ ``apps/worker``. Hai tiến trình
    nhìn vào hai thư mục khác nhau: worker ghi file giọng thành công, API tìm
    không thấy và trả 404, không bên nào báo gì sai.

    Lỗi này nằm im từ đầu dự án và chỉ lộ ra khi có endpoint đầu tiên bên API tự
    dựng đường dẫn media — trước đó mọi endpoint đều đọc đường dẫn TUYỆT ĐỐI đã
    lưu sẵn trong DB.
    """
    khai_bao = Path(os.getenv(_ENV_KEY, "./media"))
    if khai_bao.is_absolute():
        return khai_bao.resolve()
    return (_goc_repo() / khai_bao).resolve()


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def raw_dir(platform: str, source_video_id: str) -> Path:
    """Thư mục chứa file gốc tải về."""
    return _ensure(media_root() / "raw" / platform / source_video_id)


def raw_video(platform: str, source_video_id: str) -> Path:
    return raw_dir(platform, source_video_id) / "source.mp4"


def raw_meta(platform: str, source_video_id: str) -> Path:
    return raw_dir(platform, source_video_id) / "meta.json"


def work_dir(video_id: str) -> Path:
    """Thư mục chứa file trung gian: audio, phụ đề, mask, proxy."""
    return _ensure(media_root() / "work" / str(video_id))


def audio_path(video_id: str) -> Path:
    return work_dir(video_id) / "audio.wav"


def subtitle_path(video_id: str, lang: str) -> Path:
    return work_dir(video_id) / f"sub.{lang}.srt"


def subtitle_ass_path(video_id: str, lang: str) -> Path:
    """File ASS dùng để BURN vào khung hình.

    Khác ``subtitle_path`` (SRT — định dạng trao đổi, để sửa tay và tải về):
    file ASS mang sẵn ``PlayRes`` bằng khung đích cùng toàn bộ kiểu chữ tính
    theo pixel của khung đó. Xem ``pipeline/subtitle_ass.py``.
    """
    return work_dir(video_id) / f"sub.{lang}.ass"


def proxy_path(video_id: str) -> Path:
    """Bản 540p dùng cho preview trên web — tua nhanh hơn bản gốc."""
    return work_dir(video_id) / "proxy.mp4"


def out_dir(video_id: str) -> Path:
    return _ensure(media_root() / "out" / str(video_id))


def out_video(video_id: str, target: str = "master") -> Path:
    """File render cuối. ``target`` là tên nền tảng đích (M4 trở đi)."""
    return out_dir(video_id) / f"{target}.mp4"


def reframed_video(video_id: str, mode: str) -> Path:
    """File trung gian sau khi đổi khung ngang->dọc (``reframe_blur``/``reframe_crop``).

    DÙNG CHUNG cho MỌI ``render_variants`` của một video (không phụ thuộc nền
    tảng đích hay tập) — đổi khung không phụ thuộc platform/part, chỉ chạy MỘT
    LẦN cho cả video rồi mọi tập/nền tảng burn hook + phụ đề TRÊN CÙNG file
    này (xem ``pipeline/render.py::render_variant``, M4-WK-05b). Tên file gồm
    ``mode`` (``blur``/``crop``) để đổi ``reframe_mode`` giữa hai lần chạy tự
    tạo file mới, không lỡ dùng nhầm bản cũ theo mode khác.
    """
    return work_dir(video_id) / f"reframe.{mode}.mp4"


def voice_track(video_id: str) -> Path:
    """Dải tiếng Việt đã khớp thời gian, trước khi trộn vào video (M8)."""
    return work_dir(video_id) / "loitieng.wav"


def voice_parts_dir(video_id: str) -> Path:
    """Thư mục chứa từng mẩu giọng của từng câu."""
    return _ensure(work_dir(video_id) / "giong")


def cleaned_video(video_id: str) -> Path:
    """Bản đã xoá chữ cứng và watermark (M3), trước khi burn phụ đề tiếng Việt.

    File trung gian dùng chung cho mọi bước render phía sau, giống
    ``reframed_video``: xoá chữ tốn hàng chục phút nên chỉ chạy MỘT LẦN cho cả
    video, các bước sau đọc lại file này.
    """
    return work_dir(video_id) / "cleaned.mp4"


def variant_video(video_id: str, target: str, part_index: int = 1) -> Path:
    """File render của một ``render_variants`` — một bản mỗi nền tảng đích.

    Một video sinh nhiều bản (luật số 8 CLAUDE.md), mỗi bản ứng với một dòng
    ``render_variants``: ``media/out/<video_id>/<target>.p<part_index>.mp4``.
    Khác ``out_video()`` (giữ nguyên cho pipeline M1 chưa tách theo nền tảng)
    ở chỗ luôn có ``part_index`` trong tên file, kể cả khi không chia tập
    (``part_index=1``) — nhờ vậy tên file không bao giờ đụng ``out_video()``.
    """
    return out_dir(video_id) / f"{target}.p{part_index}.mp4"


def tmp_sibling(path: Path) -> Path:
    """Đường dẫn tạm cạnh file đích.

    Luôn ghi ra file tạm rồi ``rename`` sang tên chính thức, để một file dở dang
    (do crash giữa chừng) không bị bước sau coi là hợp lệ.

    Phần mở rộng được GIỮ NGUYÊN ở cuối tên (``.a.tmp.wav`` chứ không phải
    ``.a.wav.tmp``) vì FFmpeg đoán định dạng đầu ra từ phần mở rộng.
    """
    return path.with_name(f".{path.stem}.tmp{path.suffix}")
