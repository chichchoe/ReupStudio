"""Prompt dịch thuật. Tách riêng để chỉnh mà không đụng code."""

from __future__ import annotations

import json

TONE_HINTS = {
    "doi_thuong": "tự nhiên, đời thường, như người Việt nói chuyện hằng ngày",
    "ngon_tinh": "kiểu phim ngôn tình: tình cảm, có chút kịch tính, xưng hô anh/em, tôi/anh",
    "hai_huoc": "hài hước, dí dỏm, dùng từ trẻ trung",
    "trang_trong": "trang trọng, lịch sự",
}

SYSTEM_PROMPT = """Bạn là dịch giả phụ đề Trung → Việt chuyên về phim ngắn và video mạng xã hội.

Nguyên tắc:
- Dịch theo NGỮ CẢNH cả đoạn, không dịch máy móc từng câu rời rạc.
- Giữ đúng số lượng câu. Mỗi câu vào phải có đúng một câu ra.
- Câu ngắn gọn, dễ đọc trên màn hình điện thoại. Ưu tiên dưới 40 ký tự.
- Giữ nguyên số, đơn vị, tên thương hiệu.
- Không thêm giải thích, không thêm ghi chú, không dịch nghĩa đen thành ngữ.
- Nếu câu gốc là tiếng lóng, dùng tiếng lóng Việt tương đương.

Trả về DUY NHẤT một mảng JSON các chuỗi, không kèm markdown, không kèm lời dẫn."""


def build_user_prompt(texts: list[str], tone: str, glossary: dict[str, str]) -> str:
    parts = [f"Văn phong yêu cầu: {TONE_HINTS.get(tone, TONE_HINTS['doi_thuong'])}."]

    if glossary:
        pairs = "\n".join(f"- {k} → {v}" for k, v in glossary.items())
        parts.append(f"Từ điển bắt buộc tuân theo:\n{pairs}")

    numbered = json.dumps(texts, ensure_ascii=False, indent=1)
    parts.append(
        f"Dịch {len(texts)} câu sau sang tiếng Việt. "
        f"Trả về mảng JSON đúng {len(texts)} phần tử, cùng thứ tự:\n{numbered}"
    )
    return "\n\n".join(parts)


TITLE_PROMPT = """Dựa vào nội dung phụ đề tiếng Việt dưới đây, viết {count} tiêu đề cho video ngắn đăng lên TikTok / YouTube Shorts tại Việt Nam.

Yêu cầu:
- Dưới 90 ký tự
- Gợi tò mò nhưng không giật tít sai sự thật
- Tự nhiên như người Việt viết, không dịch từ tiếng Trung
- Có thể dùng tối đa 1 emoji

Trả về DUY NHẤT mảng JSON gồm {count} chuỗi.

Nội dung:
{transcript}"""
