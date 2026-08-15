"""Interface chung cho mọi nhà cung cấp giọng đọc (M8).

Theo đúng luật CLAUDE.md: "Bọc trong lớp có interface chung (translator/base.py,
tts/base.py, publishers/base.py)". Đổi nhà cung cấp chỉ được đụng vào thư mục
này, không đụng vào pipeline hay task.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class GiongDoc:
    """Một giọng đọc có thể chọn trên giao diện."""

    ma: str
    ten: str
    gioi_tinh: str
    ngon_ngu: str = "vi"


class TTSProvider(Protocol):
    """Hợp đồng tối thiểu của một nhà cung cấp giọng đọc."""

    ten: str

    def cac_giong(self) -> list[GiongDoc]:
        """Danh sách giọng dùng được."""
        ...

    def doc(self, text: str, dst: Path, *, giong: str) -> Path:
        """Đọc ``text`` thành file âm thanh tại ``dst``, trả về đường dẫn."""
        ...


def lay_provider(ten: str = "edge") -> TTSProvider:
    """Chọn nhà cung cấp theo tên. Import muộn để không kéo phụ thuộc khi không dùng."""
    if ten == "edge":
        from .edge import EdgeTTS

        return EdgeTTS()
    raise ValueError(f"Không có nhà cung cấp giọng đọc tên '{ten}'")
