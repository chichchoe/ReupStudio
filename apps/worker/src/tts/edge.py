"""Giọng đọc tiếng Việt qua edge-tts (M8).

Vì sao chọn edge-tts: **không cần khoá API và không tính phí** — nó dùng đúng
dịch vụ đọc của trình duyệt Microsoft Edge. Hạn mức Gemini của dự án đã chật
cho riêng việc dịch (đo được: một video 34 phút tiêu 31 lượt gọi), nên đẩy
thêm phần lồng tiếng sang đó là tự bóp cổ mình.

Đánh đổi phải biết trước: đây là dịch vụ không có hợp đồng, Microsoft có thể
đổi hoặc chặn bất cứ lúc nào. Vì vậy nó nằm sau ``tts/base.py`` — đổi sang nhà
cung cấp khác chỉ phải viết một file mới trong thư mục này.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from reup_core.logging import get_logger

from ..errors import ReupError
from .base import GiongDoc

log = get_logger(__name__)

#: Hai giọng tiếng Việt edge-tts có. Kiểm ngày 2026-08-15.
GIONG_VIET = [
    GiongDoc(ma="vi-VN-HoaiMyNeural", ten="Hoài My", gioi_tinh="nữ"),
    GiongDoc(ma="vi-VN-NamMinhNeural", ten="Nam Minh", gioi_tinh="nam"),
]

GIONG_MAC_DINH = "vi-VN-HoaiMyNeural"


class EdgeTTS:
    ten = "edge"

    def cac_giong(self) -> list[GiongDoc]:
        return list(GIONG_VIET)

    def doc(self, text: str, dst: Path, *, giong: str = GIONG_MAC_DINH) -> Path:
        """Đọc một câu ra file mp3.

        Câu rỗng vẫn tạo file rỗng thay vì ném lỗi: bản dịch đôi khi cho ra câu
        chỉ có dấu câu, và một câu như vậy không được làm hỏng cả video. Bước
        xếp lịch (``pipeline/dubbing.py``) tự bỏ qua file 0 giây.
        """
        import edge_tts

        dst.parent.mkdir(parents=True, exist_ok=True)
        sach = " ".join(text.split())
        if not sach:
            dst.write_bytes(b"")
            return dst

        async def _chay() -> None:
            com = edge_tts.Communicate(sach, giong)
            await com.save(str(dst))

        try:
            asyncio.run(_chay())
        except Exception as exc:
            raise ReupError(f"edge-tts đọc hỏng câu {sach[:40]!r}: {exc}") from exc

        return dst

    def doc_nhieu(
        self,
        cac_cau: list[str],
        thu_muc: Path,
        *,
        giong: str = GIONG_MAC_DINH,
        song_song: int = 8,
        progress_cb: Any = None,
    ) -> dict[int, Path]:
        """Đọc nhiều câu SONG SONG, trả về ``{chỉ số câu: file}``.

        Đây là lời gọi mạng, không phải tính toán, nên chạy tuần tự là phí:
        đo được 4,5 giây cho MỘT câu, tức 672 câu của video 34 phút mất 50
        phút. Chạy 8 luồng đưa con số đó về khoảng 6 phút.

        Không đẩy cao hơn 8: đây là dịch vụ miễn phí không có hợp đồng, dội
        quá nhiều yêu cầu một lúc là cách nhanh nhất để bị chặn.

        Câu nào hỏng thì BỎ QUA câu đó chứ không làm hỏng cả video — thiếu một
        câu lồng tiếng còn hơn mất cả bản dựng. Mọi câu hỏng đều ghi log.
        """
        import asyncio

        import edge_tts

        thu_muc.mkdir(parents=True, exist_ok=True)
        ket_qua: dict[int, Path] = {}
        xong = 0

        async def _mot(chi_so: int, text: str, khoa: Any) -> None:
            nonlocal xong
            sach = " ".join(text.split())
            dst = thu_muc / f"cau_{chi_so:05d}.mp3"
            async with khoa:
                try:
                    if sach:
                        await edge_tts.Communicate(sach, giong).save(str(dst))
                        ket_qua[chi_so] = dst
                except Exception as exc:
                    log.warning("tts.cau_hong", chi_so=chi_so, error=str(exc))
                finally:
                    xong += 1
                    if progress_cb and cac_cau:
                        progress_cb(int(xong * 100 / len(cac_cau)))

        async def _chay() -> None:
            khoa = asyncio.Semaphore(song_song)
            await asyncio.gather(*[_mot(i, t, khoa) for i, t in enumerate(cac_cau)])

        asyncio.run(_chay())
        log.info("tts.xong", tong=len(cac_cau), thanh_cong=len(ket_qua))
        return ket_qua
