"""Phân loại model LLM theo mục đích dùng trong dự án.

Hàm THUẦN — không gọi mạng, không chạm DB. Dùng chung giữa API (đổ danh sách
vào ô chọn) và worker (kiểm model được chọn có hợp lệ không).

Vì sao cần: key Gemini của dự án trả về hơn 50 model, gồm cả sinh ảnh, sinh
video, nhúng vector, điều khiển máy tính. Đổ hết vào ô "chọn AI dịch" thì người
dùng chọn nhầm ``veo-3.1-generate`` rồi ngồi đoán vì sao hỏng.

Hạn mức thật của dự án (aistudio.google.com/rate-limit, đọc ngày 2026-08-14)
cho thấy chọn nhầm tốn kém thế nào:

===========================  ===========  ============
model                        lượt/phút    lượt/ngày
===========================  ===========  ============
gemini-3.5-flash-lite            15           500
gemini-3.6-flash                  5            20
gemini-2.5-flash-tts              3            10
===========================  ===========  ============

Dịch một video 34 phút cần 7 lượt (lô 100 câu). Chọn bản ``flash`` thay vì
``flash-lite`` là mất 25 lần hạn mức ngày.

Phân loại theo MẪU TÊN chứ không theo danh sách cứng: nhà cung cấp ra model mới
liên tục (danh sách đã đổi hai lần trong một tháng), danh sách cứng sẽ lạc hậu
ngay và chặn mất model mới. Tên hoàn toàn lạ thì xếp vào ``OTHER`` — không đoán
bừa, thà không mời người dùng chọn còn hơn mời nhầm.
"""

from __future__ import annotations

import re
from enum import Enum


class ModelPurpose(str, Enum):
    """Mục đích dùng được trong dự án này, không phải mọi khả năng của model."""

    #: Dịch phụ đề, sinh tiêu đề/mô tả — nhận và trả VĂN BẢN theo lô.
    TRANSLATE = "translate"
    #: Đọc thành giọng nói (lồng tiếng, chặng M8).
    TTS = "tts"
    #: Ảnh, video, nhúng vector, điều khiển máy tính, Live API... — dự án chưa dùng.
    OTHER = "other"


#: Thứ tự kiểm QUAN TRỌNG. ``gemini-2.5-flash-tts`` chứa cả chữ "flash"; kiểm
#: TTS sau thì nó lọt vào nhóm dịch, và người dùng chọn phải model chỉ có 10
#: lượt/ngày.
_TTS = re.compile(r"-tts\b|-tts-|tts$")

#: Không dùng để dịch theo lô, dù tên nghe có vẻ liên quan:
#: - ``live``/``native-audio``: Live API, dịch thời gian thực theo luồng —
#:   khác hẳn cách ta gửi cả lô văn bản.
#: - ``image``/``imagen``/``banana``: sinh ảnh.
#: - ``veo``/``lyria``: sinh video và nhạc.
#: - ``video``: model HIỂU video (nhận video làm đầu vào), không dịch văn bản.
#: - ``embedding``: nhúng vector.
#: - ``computer-use``/``robotics``/``deep-research``/``antigravity``/``aqa``:
#:   tác tử chuyên biệt, không phải mô hình dịch văn bản.
_KHONG_DUNG = re.compile(
    r"image|imagen|banana|veo|video|lyria|embedding|computer-use|robotics"
    r"|deep-research|antigravity|\baqa\b|live|native-audio"
)

#: Họ model có khả năng nhận và trả văn bản theo lô.
#:
#: Danh sách này CHỈ mở rộng khi có bằng chứng: mỗi tên ở đây đều có mặt thật
#: trong danh mục OpenRouter (đếm ngày 16.08.2026). Không thêm theo cảm tính —
#: tên lạ vẫn xếp vào "khác", vì mời người dùng chọn một model không dịch được
#: chỉ để họ mất một lượt gọi rồi đọc thông báo lỗi khó hiểu.
_VAN_BAN = re.compile(
    r"^(gemini|gemma|gpt|o[34]\b|claude|llama|qwen|mistral|ministral|magistral"
    r"|deepseek|grok|nemotron|glm|kimi|minimax|command|sonar|hermes|phi|yi"
    r"|solar|seed|nova|ling|olmo|granite|jamba|exaone|ernie|reka|arcee|apriel)"
)


def _chuan_hoa(model_id: str) -> str:
    """Bỏ những phần KHÔNG phải tên model ra khỏi mã.

    Hai kiểu tiền tố phải bỏ:

    - ``models/gemini-...`` — API Gemini trả kèm.
    - ``google/gemini-...`` — OpenRouter đặt tên theo ``hãng/model``. Không bỏ
      thì ``_VAN_BAN`` neo ``^`` không bao giờ khớp, và 319 trên 413 model của
      OpenRouter bị giấu đi (đếm ngày 16.08.2026) — kể cả ``google/gemini``,
      ``x-ai/grok`` và toàn bộ model miễn phí.
    """
    ten = model_id.strip().removeprefix("models/").lower()
    return ten.split("/", 1)[1] if "/" in ten else ten


def phan_loai(model_id: str) -> ModelPurpose:
    """Model này dùng được vào việc gì trong dự án."""
    ten = _chuan_hoa(model_id)
    if _TTS.search(ten):
        return ModelPurpose.TTS
    if _KHONG_DUNG.search(ten):
        return ModelPurpose.OTHER
    if _VAN_BAN.match(ten):
        return ModelPurpose.TRANSLATE
    return ModelPurpose.OTHER


def loc_theo_muc_dich(model_ids: list[str], muc_dich: ModelPurpose) -> list[str]:
    """Lọc danh sách model, GIỮ NGUYÊN thứ tự đầu vào.

    Giữ thứ tự để nhà cung cấp tự quyết model nào đáng hiện trước — họ thường
    trả theo thứ tự có ý nghĩa, sắp lại theo bảng chữ cái sẽ đẩy bản cũ lên đầu.
    """
    return [m for m in model_ids if phan_loai(m) is muc_dich]
