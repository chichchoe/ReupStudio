"""Danh sách bên đọc ở hai chỗ KHÔNG được lệch nhau.

Quan sát ngày 2026-08-16: thêm `openrouter` vào danh sách giọng mà quên sửa
`TranslateRequest.tts_provider` (vẫn `Literal["edge","gemini"]`). Giao diện mời
chọn openrouter, người dùng chọn, bấm Dịch — FastAPI trả 422 cho TOÀN BỘ body.

Loại hỏng này đặc biệt khó lần: màn hình chỉ hiện "lỗi", không nói trường nào
sai; và nó chỉ xảy ra sau khi đổi mặc định nên trông như "tự dưng hỏng".
"""

from __future__ import annotations

import pytest

from src.schemas.video import BEN_DOC_HOP_LE, TranslateRequest
from src.services import video_service


@pytest.mark.parametrize("ben", BEN_DOC_HOP_LE)
def test_moi_ben_doc_hop_le_deu_gui_len_duoc(ben: str) -> None:
    assert TranslateRequest(tts_provider=ben).tts_provider == ben


def test_ben_la_thi_bi_tu_choi() -> None:
    """Vẫn phải chặn tên gõ sai — đó là lý do dùng Literal ngay từ đầu."""
    with pytest.raises(ValueError):
        TranslateRequest(tts_provider="ben-khong-co-that")


def test_moi_ben_hien_tren_giao_dien_deu_gui_len_duoc() -> None:
    """Chốt chặn thật: mời chọn cái gì thì phải nhận được cái đó.

    Gọi KHÔNG kèm session nên chỉ liệt kê edge và gemini — nhánh openrouter cần
    tra khoá trong DB. Vẫn đủ để bắt lệch ở hai bên còn lại, và
    `BEN_DOC_HOP_LE` phía trên khoá nốt phần còn lại.
    """
    for nhom in video_service.cac_giong_doc():
        assert nhom["provider"] in BEN_DOC_HOP_LE, (
            f"giao diện mời chọn '{nhom['provider']}' nhưng TranslateRequest từ chối"
        )
