"""Dò vùng chữ cứng trên khung hình bằng RapidOCR (M3).

Đo trên Mac mini M4 Pro: **0,11 giây mỗi khung**, chạy ONNX qua CoreML.

Lấy mẫu 2 khung/giây chứ không mọi khung: phụ đề tồn tại vài giây nên lấy mẫu
dày hơn chỉ tốn thời gian mà không thêm thông tin. Bước VÁ thì ngược lại, phải
chạy mọi khung, vì nền dưới mask đổi liên tục.

Module này CÓ nạp model, nên ``loc.py`` (hàm thuần, nơi đặt phần lớn test) cố ý
không import gì từ đây — kiểu dữ liệu chung nằm ở ``kieu.py``.

LƯU Ý về luật "không gọi model AI trong tiến trình worker chính": module này
nạp model ngay trong tiến trình, giống hệt ``transcribe.py`` đang làm với
faster-whisper. RapidOCR chạy ONNX, nhẹ (~15 MB) và không đụng CUDA nên rủi ro
thấp. Chỗ thật sự cần tách tiến trình là LaMa ở ``vaa.py`` — model torch nặng,
sập hoặc hết bộ nhớ ở đó sẽ kéo cả worker xuống.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from reup_core.logging import get_logger

from ...errors import InvalidFrameSizeError
from .kieu import TextBox

log = get_logger(__name__)

#: Số khung lấy mẫu mỗi giây khi dò. Xem lý do ở docstring module.
KHUNG_MOI_GIAY = 2.0

_engine: Any = None


def doi_sang_phan_tram(
    diem: list[list[float]] | Any, rong: int, cao: int
) -> tuple[float, float, float, float]:
    """Đổi bốn đỉnh pixel của RapidOCR thành ``(x, y, w, h)`` phần trăm 0–1.

    Lấy khung BAO TRỌN bốn đỉnh: OCR trả về tứ giác chứ không phải hình chữ
    nhật khi chữ hơi nghiêng, lấy hai đỉnh đối diện thì góc chữ thò ra ngoài
    mask.

    Toạ độ bị kẹp về ``[0, 1]`` — OCR đôi khi trả đỉnh lố ra ngoài mép khung,
    và toạ độ âm làm hỏng mọi phép tính phía sau mà không báo lỗi.
    """
    if rong <= 0 or cao <= 0:
        raise InvalidFrameSizeError(
            f"Kích thước khung không hợp lệ ({rong}×{cao}) — không quy đổi được toạ độ OCR."
        )

    dinh = [(float(p[0]), float(p[1])) for p in diem]
    if len(dinh) < 4:
        raise InvalidFrameSizeError(
            f"RapidOCR phải trả về 4 đỉnh, nhận được {len(dinh)} — không dựng được khung bao."
        )

    def kep(gia_tri: float) -> float:
        return max(0.0, min(1.0, gia_tri))

    trai = kep(min(p[0] for p in dinh) / rong)
    phai = kep(max(p[0] for p in dinh) / rong)
    tren = kep(min(p[1] for p in dinh) / cao)
    duoi = kep(max(p[1] for p in dinh) / cao)

    return (trai, tren, phai - trai, duoi - tren)


def _lay_engine() -> Any:
    """Nạp RapidOCR MỘT lần rồi dùng lại. Nạp lại mỗi khung thì 0,11 giây/khung
    thành vài giây/khung."""
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:  # pragma: no cover — phụ thuộc vào máy cài gì
            raise ImportError(
                'Chưa cài rapidocr-onnxruntime. Chạy: pip install -e "apps/worker[ai]"'
            ) from exc
        log.info("ocr.loading")
        _engine = RapidOCR()
    return _engine


def lay_mau_khung(video: Path, *, moi_giay: float = KHUNG_MOI_GIAY) -> Iterator[tuple[float, Any]]:
    """Sinh ra ``(giây, ảnh)`` theo nhịp lấy mẫu, không nạp cả video vào RAM."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise InvalidFrameSizeError(f"Không mở được video để lấy mẫu khung: {video}")

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        if fps <= 0:
            raise InvalidFrameSizeError(
                f"Không đọc được fps của {video} — không tính được nhịp lấy mẫu."
            )

        buoc = max(1, round(fps / moi_giay))
        chi_so = 0
        while True:
            doc_duoc, anh = cap.read()
            if not doc_duoc:
                break
            if chi_so % buoc == 0:
                yield (chi_so / fps, anh)
            chi_so += 1
    finally:
        cap.release()


def doc_khung(anh: Any, thoi_diem: float) -> list[TextBox]:
    """Dò chữ trên MỘT khung hình, trả về box theo phần trăm 0–1."""
    cao, rong = anh.shape[:2]
    ket_qua, _ = _lay_engine()(anh)
    if not ket_qua:
        return []

    ra: list[TextBox] = []
    for diem, text, tin_cay in ket_qua:
        x, y, w, h = doi_sang_phan_tram(diem, rong, cao)
        if w <= 0 or h <= 0:
            continue
        ra.append(
            TextBox(
                time=thoi_diem,
                x=x,
                y=y,
                w=w,
                h=h,
                text=str(text),
                confidence=float(tin_cay),
            )
        )
    return ra


def doc_video(video: Path, *, moi_giay: float = KHUNG_MOI_GIAY) -> list[TextBox]:
    """Dò chữ trên cả video theo nhịp lấy mẫu. Trả về mọi box đọc được.

    KHÔNG lọc gì ở đây — lọc là việc của ``loc.py``, và giữ hai việc tách rời
    cho phép chỉnh ngưỡng lọc mà không phải dò lại từ đầu (dò tốn 0,11 giây mỗi
    khung, lọc thì tức thì).
    """
    ra: list[TextBox] = []
    so_khung = 0
    for thoi_diem, anh in lay_mau_khung(video, moi_giay=moi_giay):
        ra.extend(doc_khung(anh, thoi_diem))
        so_khung += 1

    log.info("ocr.done", video=str(video), khung=so_khung, box=len(ra))
    return ra
