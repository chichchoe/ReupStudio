"""Giọng đọc qua OpenRouter (``openai/gpt-audio``).

Khác hai bên kia ở ba chỗ, và cả ba đều dễ làm hỏng nếu chép nguyên cách gọi
của Gemini sang:

1. Đây là ``/chat/completions`` chứ không phải endpoint TTS riêng. Audio xin
   bằng ``modalities: ["text", "audio"]`` kèm ``audio: {voice, format}``.
2. **BẮT BUỘC ``stream: true``** — OpenRouter chỉ trả audio qua SSE. Gửi
   ``stream: false`` thì không có tiếng nào trong phản hồi.
3. Audio về theo NHIỀU mẩu base64 ở ``choices[0].delta.audio.data``. Lấy mẩu
   đầu tiên là ra file cụt vài trăm mili giây, còn nối chuỗi base64 rồi giải mã
   một lần thì ra rác — mỗi mẩu là một khối base64 độc lập, có ``=`` chèn cuối
   chặn ngang khối sau. Phải giải mã TỪNG mẩu rồi nối byte.

Xin ``pcm16`` chứ không xin ``wav``: mỗi mẩu WAV có header riêng, nối lại là
header nằm giữa file. PCM thô nối thẳng được, rồi tự bọc header một lần —
giống hệt cách ``gemini.py`` làm với ``audio/L16``.

Vì là model ngôn ngữ chứ không phải máy đọc, nó có thể "trả lời" thay vì đọc.
Lời nhắc hệ thống ở đây khoá chặt việc đó — xem ``LOI_NHAC_HE_THONG``.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from reup_core.logging import get_logger

from ..errors import ReupError
from .base import GiongDoc

log = get_logger(__name__)

MODEL_MAC_DINH = "openai/gpt-audio"
_URL = "https://openrouter.ai/api/v1/chat/completions"

#: Giọng của gpt-audio. Đều đọc được tiếng Việt (model đa ngữ), giới tính ghi
#: theo cảm nhận nghe — OpenAI không công bố, nên đây là mô tả để chọn cho
#: nhanh chứ không phải thuộc tính chính thức.
GIONG_GPT_AUDIO: tuple[GiongDoc, ...] = (
    GiongDoc(ma="alloy", ten="Alloy — trung tính, đều", gioi_tinh="trung tính"),
    GiongDoc(ma="echo", ten="Echo — trầm, chắc", gioi_tinh="nam"),
    GiongDoc(ma="fable", ten="Fable — kể chuyện", gioi_tinh="trung tính"),
    GiongDoc(ma="onyx", ten="Onyx — trầm, dày", gioi_tinh="nam"),
    GiongDoc(ma="nova", ten="Nova — sáng, nhanh", gioi_tinh="nữ"),
    GiongDoc(ma="shimmer", ten="Shimmer — nhẹ, ấm", gioi_tinh="nữ"),
)
GIONG_MAC_DINH = "nova"

#: Model ngôn ngữ hay "giúp đỡ": thêm lời chào, giải thích, hoặc dịch tiếp.
#: Mỗi câu thừa là một câu lệch khỏi phụ đề đã canh giờ sẵn.
LOI_NHAC_HE_THONG = (
    "Bạn là máy đọc văn bản. Đọc NGUYÊN VĂN đoạn tiếng Việt người dùng đưa, "
    "bằng giọng tự nhiên. Không chào, không bình luận, không thêm hay bớt chữ nào, "
    "không dịch sang tiếng khác."
)

#: PCM 16-bit thô — xem lý do ở đầu file. Ta tự bọc thành WAV sau khi nối.
DINH_DANG = "pcm16"
#: Tần số của ``pcm16`` theo tài liệu OpenAI, cũng đúng bằng ``TAN_SO`` mà
#: ``ffmpeg/dub.py`` đang dùng nên không phải resample lần nào.
TAN_SO = 24000

SO_LAN_THU = 3
CHO_BAN_DAU_GIAY = 2.0
TIMEOUT_GIAY = 120


def _che_khoa(text: str, khoa: str) -> str:
    """Không bao giờ để khoá lọt vào log hay thông báo lỗi (luật số 6)."""
    return text.replace(khoa, "***") if khoa else text


def _gop_audio_tu_sse(luong) -> bytes:
    """Nối các mẩu base64 trong luồng SSE thành một khối audio.

    OpenRouter trả từng dòng ``data: {...}``, kết thúc bằng ``data: [DONE]``.
    Dòng nào không phải JSON hợp lệ thì bỏ qua — luồng có cả dòng trống và
    dòng ``: comment`` giữ kết nối.
    """
    manh: list[str] = []
    for dong_byte in luong:
        dong = dong_byte.decode("utf-8", "replace").strip()
        if not dong.startswith("data:"):
            continue
        than = dong[5:].strip()
        if than == "[DONE]":
            break
        try:
            goi = json.loads(than)
        except json.JSONDecodeError:
            continue

        for lua_chon in goi.get("choices") or []:
            audio = (lua_chon.get("delta") or {}).get("audio") or {}
            if audio.get("data"):
                manh.append(audio["data"])

    if not manh:
        raise ReupError("OpenRouter không trả về mẩu audio nào trong luồng SSE.")

    #: Giải mã TỪNG mẩu rồi nối byte. Nối chuỗi base64 trước rồi giải mã một
    #: lần sẽ ra rác: dấu ``=`` đệm cuối mỗi mẩu chặn ngang mẩu sau.
    try:
        return b"".join(base64.b64decode(m, validate=True) for m in manh)
    except (binascii.Error, ValueError):
        #: Đường lui cho trường hợp nhà cung cấp cắt MỘT khối base64 thành
        #: nhiều mẩu không tròn 4 ký tự — lúc đó phải nối chuỗi rồi mới giải mã.
        gop = "".join(manh)
        return base64.b64decode(gop + "=" * (-len(gop) % 4))


def _ghi_wav(dst: Path, pcm: bytes) -> None:
    """Bọc PCM thô thành WAV — ffmpeg không đoán được định dạng nếu thiếu header."""
    with wave.open(str(dst), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(TAN_SO)
        f.writeframes(pcm)


class OpenRouterTTS:
    ten = "openrouter"

    def __init__(self, api_key: str, model: str = MODEL_MAC_DINH) -> None:
        if not api_key:
            raise ReupError("Chưa dán khoá OpenRouter — không gọi được giọng đọc.")
        self._key = api_key
        self._model = model or MODEL_MAC_DINH

    def cac_giong(self) -> list[GiongDoc]:
        return list(GIONG_GPT_AUDIO)

    def doc(self, text: str, dst: Path, *, giong: str = GIONG_MAC_DINH) -> Path:
        """Đọc một câu ra file WAV 24 kHz.

        Câu rỗng tạo file rỗng thay vì ném lỗi — bước xếp lịch tự bỏ qua file 0
        giây, và một câu rỗng không được làm hỏng cả video.
        """
        dst.parent.mkdir(parents=True, exist_ok=True)
        sach = " ".join(text.split())
        if not sach:
            dst.write_bytes(b"")
            return dst

        _ghi_wav(dst, self._goi_co_thu_lai(sach, giong))
        return dst

    def _goi_co_thu_lai(self, cau: str, giong: str) -> bytes:
        cho = CHO_BAN_DAU_GIAY
        loi_cuoi = ""

        for lan in range(SO_LAN_THU):
            try:
                return self._goi_mot_lan(cau, giong)
            except urllib.error.HTTPError as exc:
                than = exc.read().decode("utf-8", "replace")[:300]
                loi_cuoi = f"HTTP {exc.code}: {_che_khoa(than, self._key)}"
                #: 404 kèm "data policy" KHÔNG phải model không tồn tại mà là
                #: tài khoản đang chặn nhà cung cấp phục vụ model đó. Gặp thật
                #: ngày 16.08.2026: khoá gọi model văn bản thì 200, gọi
                #: gpt-audio thì 404. Nói thẳng chỗ phải sửa, đừng để người dùng
                #: đi tìm trong một chuỗi JSON.
                if exc.code == 404 and "data policy" in than:
                    raise ReupError(
                        "OpenRouter chặn model giọng đọc theo thiết lập quyền riêng tư của "
                        "tài khoản. Mở https://openrouter.ai/settings/privacy và cho phép "
                        "nhà cung cấp phục vụ openai/gpt-audio, rồi thử lại."
                    ) from exc
                #: 429 hết hạn mức, 402 hết tiền — thử lại chỉ tốn thêm lượt.
                #: Báo ngay để chỗ gọi dừng và đổi sang edge-tts.
                if exc.code in (402, 429):
                    raise ReupError(f"OpenRouter TTS không chạy tiếp được: {loi_cuoi}") from exc
            except Exception as exc:  # noqa: BLE001 - mọi kiểu hỏng đều đáng thử lại
                loi_cuoi = _che_khoa(str(exc), self._key)

            if lan < SO_LAN_THU - 1:
                log.info("tts.openrouter.thu_lai", lan=lan + 1, error=loi_cuoi[:100])
                time.sleep(cho)
                cho *= 2

        raise ReupError(f"OpenRouter TTS hỏng sau {SO_LAN_THU} lần: {loi_cuoi}")

    def _goi_mot_lan(self, cau: str, giong: str) -> bytes:
        body = {
            "model": self._model,
            #: BẮT BUỘC — OpenRouter chỉ trả audio qua luồng SSE.
            "stream": True,
            "modalities": ["text", "audio"],
            "audio": {"voice": giong, "format": DINH_DANG},
            "messages": [
                {"role": "system", "content": LOI_NHAC_HE_THONG},
                {"role": "user", "content": cau},
            ],
        }
        req = urllib.request.Request(
            _URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {self._key}",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_GIAY) as r:
            return _gop_audio_tu_sse(r)
