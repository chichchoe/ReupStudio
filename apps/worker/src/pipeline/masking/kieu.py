"""Kiểu dữ liệu dùng chung của bước dò/xoá watermark và phụ đề cứng (M3).

Tách riêng khỏi ``ocr.py`` vì ``ocr.py`` nạp model RapidOCR ngay khi import;
``loc.py`` là hàm THUẦN và phải chạy được trong test mà không cần model nào.
Đặt kiểu ở đây để hai bên dùng chung mà không bên nào phải import bên kia.

**Toạ độ luôn là phần trăm 0–1, không bao giờ là pixel** (luật số 2 CLAUDE.md).
Quy đổi sang pixel chỉ xảy ra sát chỗ gọi ffmpeg/model.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextBox:
    """Một vùng chữ OCR đọc được trên MỘT khung hình.

    ``x``/``y`` là góc trên bên trái, ``w``/``h`` là bề rộng và chiều cao —
    tất cả theo phần trăm chiều rộng/chiều cao khung.
    """

    #: Giây tính từ đầu video của khung hình chứa vùng chữ này.
    time: float
    x: float
    y: float
    w: float
    h: float
    text: str
    #: Độ tin cậy OCR, 0–1.
    confidence: float

    @property
    def tam(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    def giao_nhau(self, khac: TextBox) -> float:
        """Tỉ lệ IoU với một box khác — dùng để biết hai box có cùng chỗ không."""
        trai = max(self.x, khac.x)
        tren = max(self.y, khac.y)
        phai = min(self.x + self.w, khac.x + khac.w)
        duoi = min(self.y + self.h, khac.y + khac.h)

        if phai <= trai or duoi <= tren:
            return 0.0

        chung = (phai - trai) * (duoi - tren)
        tong = self.w * self.h + khac.w * khac.h - chung
        return chung / tong if tong > 0 else 0.0


@dataclass(frozen=True)
class VungCanXoa:
    """Một vùng đã được lọc là đáng xoá, kèm khoảng thời gian nó tồn tại.

    ``ly_do`` giữ lại các tín hiệu đã cộng điểm, để giao diện giải thích được
    vì sao máy định xoá vùng này — không giải thích được thì người dùng không
    duyệt được.
    """

    x: float
    y: float
    w: float
    h: float
    bat_dau: float
    ket_thuc: float
    diem: float
    ly_do: tuple[str, ...]
