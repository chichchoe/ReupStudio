"""Giọng đọc bằng Gemini TTS (M8).

Vì sao thêm bên cạnh edge-tts: chủ dự án nghe thử và thấy giọng edge-tts chưa
đạt. Gemini TTS có 30 giọng dựng sẵn và nhận cả chỉ dẫn ngữ điệu bằng lời
("đọc chậm rãi, giọng kể chuyện"), nên chất giọng tự nhiên hơn hẳn.

ĐÁNH ĐỔI PHẢI BIẾT TRƯỚC — hạn mức. edge-tts không tính lượt; Gemini TTS tính
đúng như mọi lời gọi Gemini khác và bậc miễn phí của dự án chỉ có 500 lượt mỗi
ngày. Một video 34 phút có 672 câu, tức MỘT video đã vượt hạn mức ngày. Vì vậy:

    video ngắn, cần giọng đẹp     -> Gemini TTS
    video dài                     -> edge-tts

Mỗi câu là một lượt gọi và được ghi vào ``cost_logs`` như mọi lời gọi ngoài
khác, nên tab hạn mức phản ánh đúng.

Trả về PCM L16 24 kHz một kênh — đúng tần số edge-tts trả về, nên phần dựng dải
tiếng phía sau không phải đổi gì. Ở đây bọc thành WAV để mọi bước sau đọc được
bằng ffmpeg như file thường.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any

from reup_core.logging import get_logger

from ..errors import ReupError
from .base import GiongDoc

log = get_logger(__name__)

_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

#: Tần số Gemini TTS trả về. Trùng edge-tts nên không phải resample.
TAN_SO = 24000

MODEL_MAC_DINH = "gemini-2.5-flash-preview-tts"
GIONG_MAC_DINH = "Kore"

#: 30 giọng dựng sẵn. Mô tả lấy theo tính chất giọng để người dùng chọn được mà
#: không phải nghe thử cả 30.
GIONG_GEMINI = [
    GiongDoc(ma="Kore", ten="Kore — chắc chắn", gioi_tinh="nữ"),
    GiongDoc(ma="Aoede", ten="Aoede — nhẹ nhàng", gioi_tinh="nữ"),
    GiongDoc(ma="Leda", ten="Leda — trẻ trung", gioi_tinh="nữ"),
    GiongDoc(ma="Callirrhoe", ten="Callirrhoe — thong thả", gioi_tinh="nữ"),
    GiongDoc(ma="Autonoe", ten="Autonoe — tươi sáng", gioi_tinh="nữ"),
    GiongDoc(ma="Despina", ten="Despina — mượt", gioi_tinh="nữ"),
    GiongDoc(ma="Erinome", ten="Erinome — rõ ràng", gioi_tinh="nữ"),
    GiongDoc(ma="Laomedeia", ten="Laomedeia — sôi nổi", gioi_tinh="nữ"),
    GiongDoc(ma="Achernar", ten="Achernar — êm", gioi_tinh="nữ"),
    GiongDoc(ma="Gacrux", ten="Gacrux — chững chạc", gioi_tinh="nữ"),
    GiongDoc(ma="Pulcherrima", ten="Pulcherrima — dẫn chuyện", gioi_tinh="nữ"),
    GiongDoc(ma="Vindemiatrix", ten="Vindemiatrix — dịu", gioi_tinh="nữ"),
    GiongDoc(ma="Sulafat", ten="Sulafat — ấm", gioi_tinh="nữ"),
    GiongDoc(ma="Zephyr", ten="Zephyr — sáng", gioi_tinh="nữ"),
    GiongDoc(ma="Puck", ten="Puck — hoạt bát", gioi_tinh="nam"),
    GiongDoc(ma="Charon", ten="Charon — trầm, kể chuyện", gioi_tinh="nam"),
    GiongDoc(ma="Fenrir", ten="Fenrir — mạnh", gioi_tinh="nam"),
    GiongDoc(ma="Orus", ten="Orus — chắc", gioi_tinh="nam"),
    GiongDoc(ma="Enceladus", ten="Enceladus — thì thầm", gioi_tinh="nam"),
    GiongDoc(ma="Iapetus", ten="Iapetus — rõ", gioi_tinh="nam"),
    GiongDoc(ma="Umbriel", ten="Umbriel — thư thái", gioi_tinh="nam"),
    GiongDoc(ma="Algieba", ten="Algieba — mượt", gioi_tinh="nam"),
    GiongDoc(ma="Algenib", ten="Algenib — khàn", gioi_tinh="nam"),
    GiongDoc(ma="Rasalgethi", ten="Rasalgethi — giàu thông tin", gioi_tinh="nam"),
    GiongDoc(ma="Alnilam", ten="Alnilam — dứt khoát", gioi_tinh="nam"),
    GiongDoc(ma="Schedar", ten="Schedar — điềm đạm", gioi_tinh="nam"),
    GiongDoc(ma="Achird", ten="Achird — thân thiện", gioi_tinh="nam"),
    GiongDoc(ma="Zubenelgenubi", ten="Zubenelgenubi — đời thường", gioi_tinh="nam"),
    GiongDoc(ma="Sadachbia", ten="Sadachbia — sống động", gioi_tinh="nam"),
    GiongDoc(ma="Sadaltager", ten="Sadaltager — hiểu biết", gioi_tinh="nam"),
]

#: Chỉ dẫn ngữ điệu ghép trước câu cần đọc. Đây là thứ edge-tts không làm được,
#: và là lý do chính để chịu hạn mức của Gemini.
NGU_DIEU_MAC_DINH = "Đọc câu sau bằng giọng kể chuyện tự nhiên, rõ ràng, không quá nhanh:"

SO_LAN_THU = 3
CHO_BAN_DAU_GIAY = 2.0


class GeminiTTS:
    ten = "gemini"

    def __init__(self, api_key: str, model: str = MODEL_MAC_DINH) -> None:
        if not api_key:
            raise ReupError("Chưa có LLM_API_KEY — không gọi được Gemini TTS.")
        self._key = api_key
        self._model = model

    def cac_giong(self) -> list[GiongDoc]:
        return list(GIONG_GEMINI)

    def doc(
        self,
        text: str,
        dst: Path,
        *,
        giong: str = GIONG_MAC_DINH,
        ngu_dieu: str = NGU_DIEU_MAC_DINH,
    ) -> Path:
        """Đọc một câu ra file WAV 24 kHz.

        Câu rỗng tạo file rỗng thay vì ném lỗi — bước xếp lịch tự bỏ qua file 0
        giây, và một câu rỗng không được làm hỏng cả video.
        """
        dst.parent.mkdir(parents=True, exist_ok=True)
        sach = " ".join(text.split())
        if not sach:
            dst.write_bytes(b"")
            return dst

        pcm = self._goi_co_thu_lai(f"{ngu_dieu} {sach}", giong)
        _ghi_wav(dst, pcm)
        return dst

    def _goi_co_thu_lai(self, loi_nhac: str, giong: str) -> bytes:
        """Gọi API, thử lại có giãn nhịp. Che khoá trong mọi thông báo lỗi."""
        cho = CHO_BAN_DAU_GIAY
        loi_cuoi = ""

        for lan in range(SO_LAN_THU):
            try:
                return self._goi_mot_lan(loi_nhac, giong)
            except urllib.error.HTTPError as exc:
                than = exc.read().decode("utf-8", "replace")[:300]
                loi_cuoi = f"HTTP {exc.code}: {_che_khoa(than, self._key)}"
                #: 429 là hết hạn mức, không phải lỗi tạm — thử lại chỉ tốn thêm
                #: lượt. Báo ra ngay để chỗ gọi đổi sang edge-tts.
                if exc.code == 429:
                    raise ReupError(f"Gemini TTS hết hạn mức: {loi_cuoi}") from exc
            except Exception as exc:
                loi_cuoi = _che_khoa(str(exc), self._key)

            if lan < SO_LAN_THU - 1:
                log.info("tts.gemini.thu_lai", lan=lan + 1, error=loi_cuoi[:100])
                time.sleep(cho)
                cho *= 2

        raise ReupError(f"Gemini TTS hỏng sau {SO_LAN_THU} lần: {loi_cuoi}")

    def _goi_mot_lan(self, loi_nhac: str, giong: str) -> bytes:
        body = {
            "contents": [{"parts": [{"text": loi_nhac}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": giong}}},
            },
        }
        req = urllib.request.Request(
            _URL.format(model=self._model),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self._key},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data: Any = json.load(r)

        try:
            phan = data["candidates"][0]["content"]["parts"][0]["inlineData"]
        except (KeyError, IndexError) as exc:
            raise ReupError(f"Gemini TTS trả về không có audio: {str(data)[:200]}") from exc

        return base64.b64decode(phan["data"])


def _ghi_wav(dst: Path, pcm: bytes) -> None:
    """Bọc PCM thô thành WAV.

    Gemini trả về ``audio/L16`` không có header. Ghi thẳng ra đĩa thì ffmpeg
    không đoán được định dạng và mọi bước sau hỏng với lỗi khó hiểu.
    """
    with wave.open(str(dst), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(TAN_SO)
        f.writeframes(pcm)


def _che_khoa(text: str, key: str) -> str:
    """Không bao giờ để khoá API lọt vào log hay thông báo lỗi."""
    return text.replace(key, "***") if key else text
