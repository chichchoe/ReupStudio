"""Nhận dạng giọng nói tiếng Trung bằng faster-whisper.

Model được nạp một lần và giữ lại trong tiến trình worker GPU (concurrency=1).
"""

from __future__ import annotations

from pathlib import Path

from reup_core.logging import get_logger

from ..config import get_settings
from ..errors import TranscribeError
from ..milestones import milestones
from .cues import Cue

log = get_logger(__name__)

_model = None
_model_key: tuple[str, str, str] | None = None


def _resolve_device(configured: str) -> str:
    if configured != "auto":
        return configured
    try:
        import torch  # noqa: PLC0415

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def get_model():
    """Nạp model một lần rồi tái sử dụng — nạp lại mỗi video sẽ rất chậm."""
    global _model, _model_key
    settings = get_settings()
    device = _resolve_device(settings.whisper_device)
    compute_type = settings.whisper_compute_type if device == "cuda" else "int8"
    key = (settings.whisper_model, device, compute_type)

    if _model is not None and _model_key == key:
        return _model

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover
        raise TranscribeError(
            'Chưa cài faster-whisper. Chạy: pip install -e "apps/worker[ai]"'
        ) from exc

    log.info("whisper.loading", model=settings.whisper_model, device=device)
    _model = WhisperModel(settings.whisper_model, device=device, compute_type=compute_type)
    _model_key = key
    return _model


def transcribe(audio_path: Path, *, language: str = "zh", progress_cb=None) -> list[Cue]:
    """Trả về danh sách cue tiếng Trung có timestamp.

    Dùng VAD để bỏ đoạn im lặng — giảm ảo giác (hallucination) của Whisper trên
    video chỉ có nhạc nền.
    """
    if not audio_path.exists():
        raise TranscribeError(f"Không tìm thấy file audio: {audio_path}")

    model = get_model()
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
        beam_size=5,
        condition_on_previous_text=False,  # tránh lặp câu ở video ngắn
    )

    total = float(getattr(info, "duration", 0.0)) or 1.0
    #: Số segment không biết trước (generator whisper) nên không dùng
    #: milestones(số_segment) như format_cues — thay vào đó dàn mốc theo %
    #: thời lượng (milestones(100)) rồi bắn dần khi vượt ngưỡng. Đảm bảo đủ
    #: ít nhất MIN_MILESTONES mốc kể cả khi audio chỉ có 1-2 segment.
    marks = sorted(milestones(100)) if progress_cb else []
    next_mark = 0
    cues: list[Cue] = []
    for index, seg in enumerate(segments):
        text = (seg.text or "").strip()
        if not text:
            continue
        cues.append(Cue(index, float(seg.start), float(seg.end), text))
        if progress_cb:
            percent = min(99, int(seg.end / total * 100))
            while next_mark < len(marks) and marks[next_mark] <= percent:
                progress_cb(marks[next_mark])
                next_mark += 1

    if progress_cb:
        while next_mark < len(marks):
            progress_cb(marks[next_mark])
            next_mark += 1

    log.info("whisper.done", cues=len(cues), duration=total)
    return cues
