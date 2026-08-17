"""Giọng đọc qua VoiceStudio chạy tại máy (https://github.com/debpalash/VoiceStudio).

Dễ hơn hẳn ``openrouter.py``: VoiceStudio mở đúng endpoint TTS chuẩn của
OpenAI — ``POST /v1/audio/speech`` nhận JSON, trả THẲNG khối audio. Không SSE,
không mẩu base64, không phải dỗ model đọc thay vì trả lời.

Ba thứ nó cho mà hai bên kia không có:

- Chạy tại máy: không khoá API, không tính tiền, không hạn mức.
- Nhân bản giọng từ một mẩu ghi âm ngắn, nên đọc được bằng giọng đã chọn sẵn.
- Nhiều engine (OmniVoice, CosyVoice, GPT-SoVITS…), đổi bằng ``TTS_MODEL``.

Đổi lại: nó là model chạy trên máy mình, nên tốc độ phụ thuộc phần cứng. Trên
máy không có GPU — nhất là khi image amd64 phải chạy qua giả lập trên Apple
Silicon — có thể chậm hơn nhiều lần so với gọi mạng.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from reup_core.logging import get_logger

from ..errors import ReupError
from .base import GiongDoc

log = get_logger(__name__)

#: Cổng mặc định của VoiceStudio (xem docs/install/docker.md của họ).
BASE_URL_MAC_DINH = "http://localhost:3900/v1"
MODEL_MAC_DINH = "omnivoice"

#: Xin WAV cho đồng bộ với hai provider kia — ``dung_dai_tieng`` giải mã bằng
#: ffmpeg nên định dạng nào cũng được, nhưng WAV khỏi phải đoán.
DINH_DANG = "wav"

#: Giọng mặc định khi máy chủ chưa trả danh sách. VoiceStudio nhận cả tên giọng
#: người dùng tự nhân bản, nên đây chỉ là chỗ bấu víu ban đầu.
GIONG_MAC_DINH = "default"
GIONG_DU_PHONG: tuple[GiongDoc, ...] = (GiongDoc(ma="default", ten="Mặc định", gioi_tinh="—"),)

SO_LAN_THU = 3
CHO_BAN_DAU_GIAY = 2.0
#: Rộng hơn hẳn hai bên gọi mạng: đây là model chạy trên máy, lần đọc đầu còn
#: phải nạp trọng số vào bộ nhớ.
TIMEOUT_GIAY = 600


def _goi(url: str, body: dict | None, timeout: int) -> bytes:
    """Gọi VoiceStudio. ``body`` rỗng nghĩa là GET."""
    du_lieu = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=du_lieu,
        headers={"Content-Type": "application/json", "Accept": "*/*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


#: Tên khoá chứa MÃ giọng, theo thứ tự ưu tiên. VoiceStudio trả ``voice_id``
#: (đo thật ngày 17.08.2026) — lấy nhầm ``name`` là gửi lên "Alloy" thay vì
#: "alloy", và máy chủ không nhận ra giọng nào.
_KHOA_MA = ("voice_id", "id", "name")


def _doc_giong(data: object) -> list[GiongDoc]:
    """Rút danh sách giọng từ phản hồi. Hình dạng lạ thì trả rỗng."""
    muc = data.get("voices") if isinstance(data, dict) else data
    ra: list[GiongDoc] = []
    for v in muc or []:
        if not isinstance(v, dict):
            continue
        ma = next((str(v[k]) for k in _KHOA_MA if v.get(k)), "")
        if not ma:
            continue
        ra.append(
            GiongDoc(
                ma=ma,
                ten=str(v.get("name") or ma),
                #: VoiceStudio không khai giới tính; ``type`` cho biết đây là
                #: giọng có sẵn hay giọng người dùng tự nhân bản, hữu ích hơn.
                gioi_tinh=str(v.get("gender") or v.get("type") or "—"),
            )
        )
    return ra


class VoiceStudioTTS:
    ten = "voicestudio"

    def __init__(self, base_url: str = "", model: str = MODEL_MAC_DINH) -> None:
        self._goc = (base_url or BASE_URL_MAC_DINH).rstrip("/")
        self._model = model or MODEL_MAC_DINH

    def cac_giong(self) -> list[GiongDoc]:
        """Hỏi thẳng máy chủ xem có giọng nào.

        Không gọi được (chưa bật container) thì trả danh sách dự phòng thay vì
        ném lỗi — chỗ gọi chỉ đang liệt kê để hiện lên giao diện, làm sập cả
        trang cấu hình vì một container chưa chạy là quá tay.
        """
        try:
            data = json.loads(_goi(f"{self._goc}/audio/voices", None, 10))
        except Exception as exc:  # noqa: BLE001 - mọi kiểu hỏng đều là "chưa hỏi được"
            log.info("tts.voicestudio.khong_hoi_duoc_giong", error=str(exc)[:120])
            return list(GIONG_DU_PHONG)

        return _doc_giong(data) or list(GIONG_DU_PHONG)

    def doc(self, text: str, dst: Path, *, giong: str = GIONG_MAC_DINH) -> Path:
        """Đọc một câu ra file.

        Câu rỗng tạo file rỗng thay vì ném lỗi — bước xếp lịch tự bỏ qua file 0
        giây, và một câu rỗng không được làm hỏng cả video.
        """
        dst.parent.mkdir(parents=True, exist_ok=True)
        sach = " ".join(text.split())
        if not sach:
            dst.write_bytes(b"")
            return dst

        dst.write_bytes(self._goi_co_thu_lai(sach, giong))
        return dst

    def _goi_co_thu_lai(self, cau: str, giong: str) -> bytes:
        cho = CHO_BAN_DAU_GIAY
        loi_cuoi = ""

        for lan in range(SO_LAN_THU):
            try:
                return self._goi_mot_lan(cau, giong)
            except urllib.error.HTTPError as exc:
                than = exc.read().decode("utf-8", "replace")[:300]
                loi_cuoi = f"HTTP {exc.code}: {than}"
                #: 4xx là sai yêu cầu (giọng không có, model sai tên) — thử lại
                #: y hệt cũng hỏng y hệt.
                if 400 <= exc.code < 500:
                    raise ReupError(f"VoiceStudio từ chối: {loi_cuoi}") from exc
            except urllib.error.URLError as exc:
                loi_cuoi = str(exc.reason)
                raise ReupError(
                    f"Không kết nối được VoiceStudio tại {self._goc} ({loi_cuoi}). "
                    "Bật container: docker compose --profile voicestudio up -d"
                ) from exc
            except Exception as exc:  # noqa: BLE001 - lỗi tạm thì thử lại
                loi_cuoi = str(exc)[:200]

            if lan < SO_LAN_THU - 1:
                log.info("tts.voicestudio.thu_lai", lan=lan + 1, error=loi_cuoi[:100])
                time.sleep(cho)
                cho *= 2

        raise ReupError(f"VoiceStudio hỏng sau {SO_LAN_THU} lần: {loi_cuoi}")

    def _goi_mot_lan(self, cau: str, giong: str) -> bytes:
        am = _goi(
            f"{self._goc}/audio/speech",
            {
                "model": self._model,
                "input": cau,
                "voice": giong or GIONG_MAC_DINH,
                "response_format": DINH_DANG,
            },
            TIMEOUT_GIAY,
        )
        #: Máy chủ trả 200 kèm thân rỗng vẫn là hỏng — chỉ là hỏng lặng lẽ hơn.
        #: Ghi ra file 0 byte thì bước sau âm thầm bỏ qua câu này.
        if not am:
            raise ReupError("VoiceStudio trả về audio rỗng.")
        return am
