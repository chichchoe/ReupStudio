"""Vá vùng đã bị xoá: LaMa là chính, ``cv2.inpaint`` là phương án dự phòng (M3).

Số đo trên Mac mini M4 Pro (2026-08-15), khung 720×1280:

    LaMa cả khung        4,700 s/khung   không dùng được
    LaMa chỉ vùng cắt    0,173 s/khung   ảnh sạch
    cv2.inpaint          0,008 s/khung   nhoè rõ trên nền có cấu trúc

Cắt vùng nhỏ quanh chữ rồi mới đưa vào model là phép tối ưu quyết định — nhanh
gấp 27 lần vá cả khung, và chính nó biến M3 từ "không khả thi trên máy này"
thành "khả thi".

Vùng cắt phải RỘNG HƠN mask: LaMa cần nhìn thấy nền xung quanh chỗ thủng mới
dựng lại được. Cắt sát mask thì model chỉ nhìn thấy chữ và vá ra một mảng bệt.

LƯU Ý về luật "không gọi model AI trong tiến trình worker chính": module này
nạp LaMa ngay trong tiến trình, giống ``transcribe.py`` và ``ocr.py``. Đây là
chỗ rủi ro nhất trong ba chỗ — model torch nặng, hết bộ nhớ giữa chừng sẽ kéo
cả worker xuống. Chưa tách tiến trình vì tách đúng cách cần một tiến trình con
sống dai nhận khung qua ống dẫn (nạp lại model mỗi khung thì 0,173 giây thành
vài giây), và việc đó chỉ đáng làm sau khi đo xong bộ nhớ thật.
"""

from __future__ import annotations

from typing import Any

from reup_core.logging import get_logger

from ...errors import InvalidFrameSizeError
from .timeline import MaskRegion

log = get_logger(__name__)

#: Số pixel nới thêm mỗi phía khi cắt vùng đưa vào LaMa — phần nền để model
#: nhìn mà dựng lại. Đo trên mask 629×97 thật (2026-08-15):
#:
#:     48px   720×192   0,246 s
#:     32px   694×160   0,135 s
#:     20px   670×136   0,124 s
#:     12px   654×120   0,116 s
#:
#: Bốn mức cho ảnh nhìn giống hệt nhau, nhưng 48px CHẬM GẤP ĐÔI 20px: vùng chữ
#: là dải mỏng nằm ngang, cộng biên vào chiều cao 97px thì 48px mỗi phía làm
#: phình diện tích gấp đôi. Chọn 24px — vẫn ở vùng rẻ, còn dư biên so với mức
#: 12px đã đo là đủ, phòng khi nền phức tạp hơn cái áo trắng đã thử.
BIEN_CAT_PX = 24

#: Thu nhỏ vùng cắt trước khi vá rồi phóng lại. Đo trên vùng 720×192 thật
#: (2026-08-15):
#:
#:     1,00   0,384 s   nét gốc
#:     0,75   0,157 s   nhanh gấp 2,4 lần, mắt không phân biệt được
#:     0,50   0,083 s   nhanh gấp 4,6 lần, đã thấy mềm
#:     0,35   0,058 s   nhanh gấp 6,6 lần, nhoè hẳn
#:
#: Chọn 0,75: đây là mức cuối cùng còn giữ nguyên nét khi so ảnh cạnh nhau.
TI_LE_VA = 0.75

#: Vùng nhỏ hơn ngần này pixel thì không thu nhỏ nữa — model không còn gì để
#: đọc, mà chỗ tiết kiệm được chỉ vài mili giây.
CANH_TOI_THIEU_DE_THU_NHO = 96

#: Hai vùng cắt coi là "không đổi" khi chênh lệch trung bình dưới ngần này mức
#: xám (0–255). Đặt chặt: dùng lại miếng vá cũ khi nền ĐÃ đổi sẽ để lại một
#: mảng hình của quá khứ đứng im giữa cảnh đang chạy — hỏng nặng hơn không xoá.
NGUONG_KHONG_DOI = 1.5

_lama: Any = None


class BoNhoVa:
    """Nhớ miếng vá gần nhất của TỪNG mask để khỏi gọi model lại khi nền đứng yên.

    Vì sao đáng làm — đo trên hai video thật (2026-08-15), đếm số lượt vá có
    vùng cắt gần như y hệt khung trước:

        video Douyin, phim vẽ      144/149   97%
        video rednote, quay tay     12/401    3%

    Nội dung phim vẽ đứng yên gần như suốt, và đó đúng là loại video dài nhất
    của dự án. Không có bộ nhớ này thì video một tiếng phải gọi model khoảng
    90.000 lần cho những khung y hệt nhau.

    Mỗi mask một ô nhớ riêng: dùng chung thì miếng vá của mask này đắp sang chỗ
    của mask kia.
    """

    def __init__(self, nguong: float = NGUONG_KHONG_DOI) -> None:
        self._nguong = nguong
        self._o: dict[int, tuple[Any, Any]] = {}
        self.so_lan_dung_lai = 0
        self.so_lan_va = 0

    def lay(self, khoa: int, cat: Any) -> Any | None:
        """Miếng vá cũ nếu vùng cắt gần như không đổi, ngược lại ``None``."""
        import numpy as np

        da_co = self._o.get(khoa)
        if da_co is None:
            return None

        cat_cu, ket_qua = da_co
        if cat_cu.shape != cat.shape:
            return None

        lech = np.abs(cat.astype(np.int16) - cat_cu.astype(np.int16)).mean()
        if lech >= self._nguong:
            return None

        self.so_lan_dung_lai += 1
        return ket_qua

    def luu(self, khoa: int, cat: Any, ket_qua: Any) -> None:
        self._o[khoa] = (cat.copy(), ket_qua.copy())
        self.so_lan_va += 1


def mask_dang_hien(masks: list[MaskRegion], thoi_diem: float) -> list[MaskRegion]:
    """Các mask đang phải áp tại thời điểm ``thoi_diem`` (giây).

    Lấy cả hai đầu khoảng: biên đã được nới ở ``timeline.py`` theo nhịp lấy
    mẫu, cắt thêm ở đây thì khung đầu và khung cuối của mỗi câu lại còn nguyên
    chữ.
    """
    return [m for m in masks if m.bat_dau <= thoi_diem <= m.ket_thuc]


def hop_pixel(
    mask: MaskRegion, rong: int, cao: int, *, bien: int = BIEN_CAT_PX
) -> tuple[int, int, int, int]:
    """Đổi mask phần trăm thành hộp pixel ``(x1, y1, x2, y2)`` đã nới biên.

    Đây là ranh giới CUỐI CÙNG giữa hệ toạ độ phần trăm của cả chặng M3 và
    pixel thật của ảnh (luật số 2 CLAUDE.md) — không có chỗ nào khác quy đổi.

    Hộp luôn có diện tích dương: mask mỏng tới mức quy đổi ra 0 pixel sẽ cho
    mảng rỗng và LaMa ném lỗi khó hiểu ở tận đáy.
    """
    if rong <= 0 or cao <= 0:
        raise InvalidFrameSizeError(
            f"Kích thước khung không hợp lệ ({rong}×{cao}) — không quy đổi được mask."
        )

    x1 = max(0, int(mask.x * rong) - bien)
    y1 = max(0, int(mask.y * cao) - bien)
    x2 = min(rong, int((mask.x + mask.w) * rong) + bien)
    y2 = min(cao, int((mask.y + mask.h) * cao) + bien)

    if x2 <= x1:
        x2 = min(rong, x1 + 1)
        x1 = max(0, x2 - 1)
    if y2 <= y1:
        y2 = min(cao, y1 + 1)
        y1 = max(0, y2 - 1)

    return (x1, y1, x2, y2)


def _lay_lama() -> Any:
    """Nạp LaMa MỘT lần rồi dùng lại — nạp lại mỗi khung thì không dùng được."""
    global _lama
    if _lama is None:
        try:
            from simple_lama_inpainting import SimpleLama
        except ImportError as exc:  # pragma: no cover — phụ thuộc vào máy cài gì
            raise ImportError(
                'Chưa cài simple-lama-inpainting. Chạy: pip install -e "apps/worker[ai]"'
            ) from exc
        log.info("lama.loading")
        _lama = SimpleLama()
    return _lama


def _va_bang_lama(cat: Any, mat_na: Any) -> Any:
    from PIL import Image

    ket_qua = _lay_lama()(
        Image.fromarray(cat[:, :, ::-1]),  # OpenCV dùng BGR, PIL dùng RGB
        Image.fromarray(mat_na),
    )
    import numpy as np

    return np.array(ket_qua)[:, :, ::-1]


def _va_bang_cv2(cat: Any, mat_na: Any) -> Any:
    import cv2

    return cv2.inpaint(cat, mat_na, 3, cv2.INPAINT_TELEA)


def thu_nho_va_phong_lai(cat: Any, mat_na: Any, ti_le: float, va: Any) -> Any:
    """Thu nhỏ vùng cắt, gọi ``va``, rồi phóng kết quả về đúng kích thước cũ.

    Chi phí của LaMa tỉ lệ với số pixel, nên đây là chỗ mua được nhiều tốc độ
    nhất mà không đổi kiến trúc gì — xem số đo ở ``TI_LE_VA``.

    Trả về ảnh ĐÚNG kích thước vào: lệch một pixel là có đường nối thấy rõ
    quanh chỗ vừa vá.

    Mặt nạ phóng to bằng nội suy LÁNG GIỀNG GẦN NHẤT, không phải nội suy tuyến
    tính: mặt nạ chỉ có hai giá trị 0 và 255, nội suy mượt sẽ đẻ ra viền xám mà
    model đọc thành "hơi thủng", vá ra một vành mờ quanh mép.
    """
    import cv2

    cao, rong = cat.shape[:2]
    qua_nho = min(cao, rong) < CANH_TOI_THIEU_DE_THU_NHO
    if ti_le >= 1.0 or qua_nho:
        return va(cat, mat_na)

    nho = cv2.resize(cat, None, fx=ti_le, fy=ti_le, interpolation=cv2.INTER_AREA)
    mat_na_nho = cv2.resize(mat_na, (nho.shape[1], nho.shape[0]), interpolation=cv2.INTER_NEAREST)

    ket_qua = va(nho, mat_na_nho)
    return cv2.resize(ket_qua, (rong, cao), interpolation=cv2.INTER_LANCZOS4)


def va_khung(
    anh: Any,
    masks: list[MaskRegion],
    thoi_diem: float,
    *,
    dung_lama: bool = True,
    bien: int = BIEN_CAT_PX,
    ti_le: float = TI_LE_VA,
    bo_nho: BoNhoVa | None = None,
) -> Any:
    """Vá mọi mask đang hiện trên MỘT khung hình, trả về ảnh đã vá.

    Không có mask nào đang hiện thì trả về đúng ảnh vào — không sao chép, không
    chạm model. Phần lớn khung của một video rơi vào nhánh này.

    Truyền ``bo_nho`` (giữ nguyên một đối tượng qua cả video) để bỏ qua những
    khung có nền không đổi — xem ``BoNhoVa``, đo được 97% trên phim vẽ.
    """
    dang_hien = mask_dang_hien(masks, thoi_diem)
    if not dang_hien:
        return anh

    import numpy as np

    cao, rong = anh.shape[:2]
    ra = anh.copy()

    for mask in dang_hien:
        #: Khoá theo vị trí trong danh sách GỐC, không theo thứ tự trong
        #: ``dang_hien``: số mask đang hiện đổi theo từng khung, đánh số lại mỗi
        #: khung sẽ khiến ô nhớ của mask này gán nhầm cho mask khác.
        khoa = masks.index(mask)
        x1, y1, x2, y2 = hop_pixel(mask, rong, cao, bien=bien)
        cat = ra[y1:y2, x1:x2]

        #: Mặt nạ chỉ tô phần MASK, không tô phần biên vừa nới — biên là ngữ
        #: cảnh để model nhìn, tô luôn vào thì lại xoá mất chính ngữ cảnh đó.
        mat_na = np.zeros(cat.shape[:2], dtype=np.uint8)
        mx1 = max(0, int(mask.x * rong) - x1)
        my1 = max(0, int(mask.y * cao) - y1)
        mx2 = min(cat.shape[1], int((mask.x + mask.w) * rong) - x1)
        my2 = min(cat.shape[0], int((mask.y + mask.h) * cao) - y1)
        mat_na[my1:my2, mx1:mx2] = 255

        if not mat_na.any():
            continue

        va = bo_nho.lay(khoa, cat) if bo_nho is not None else None
        if va is None:
            cach_va = _va_bang_lama if dung_lama else _va_bang_cv2
            try:
                va = thu_nho_va_phong_lai(cat, mat_na, ti_le, cach_va)
            except Exception as exc:
                #: Rơi về cv2 thay vì làm hỏng cả job. Nhoè còn hơn để nguyên
                #: chữ Trung, nhưng PHẢI ghi log — im lặng thì không ai biết
                #: chất lượng đã tụt.
                log.warning("lama.that_bai_dung_cv2", error=str(exc), thoi_diem=thoi_diem)
                va = thu_nho_va_phong_lai(cat, mat_na, ti_le, _va_bang_cv2)
            if bo_nho is not None:
                bo_nho.luu(khoa, cat, va)

        ra[y1:y2, x1:x2] = va[: y2 - y1, : x2 - x1]

    return ra
