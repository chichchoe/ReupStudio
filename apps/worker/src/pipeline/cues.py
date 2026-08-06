"""Kiểu dữ liệu phụ đề và xuất file SRT.

Hàm thuần — không chạm DB, không import Celery. Test được bằng cách gọi trực tiếp.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Cue:
    i: int
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def with_text(self, text: str) -> Cue:
        return replace(self, text=text)

    def to_dict(self) -> dict[str, Any]:
        return {"i": self.i, "start": self.start, "end": self.end, "text": self.text}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Cue:
        return Cue(int(d["i"]), float(d["start"]), float(d["end"]), str(d["text"]))


def cues_to_dicts(cues: list[Cue]) -> list[dict[str, Any]]:
    return [c.to_dict() for c in cues]


def cues_from_dicts(items: list[dict[str, Any]]) -> list[Cue]:
    return [Cue.from_dict(d) for d in items]


def _srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(cues: list[Cue], path: Path) -> Path:
    """Ghi file SRT (UTF-8, không BOM)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(
            f"{index}\n{_srt_timestamp(cue.start)} --> {_srt_timestamp(cue.end)}\n{cue.text}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path
