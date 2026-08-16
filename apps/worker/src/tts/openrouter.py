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

import numpy as np
from reup_core.logging import get_logger

from ..errors import ReupError
from .base import GiongDoc

log = get_logger(__name__)

#: ``gpt-audio-mini`` chứ KHÔNG phải ``gpt-audio``: token audio giá $0,60/1M
#: so với $32/1M — đắt gấp 53 lần cho cùng một câu đọc. Đo ngày 2026-08-16.
MODEL_MAC_DINH = "openai/gpt-audio-mini"
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

#: Model ngôn ngữ hay "giúp đỡ": nó TRẢ LỜI câu thoại thay vì đọc câu thoại.
#: Đo thật ngày 2026-08-16, gửi "Hôm nay trời rất đẹp, chúng ta cùng nấu ăn
#: nhé." thì nó đọc ra: "Chào bạn! Nghe có vẻ thú vị đấy... Bạn muốn thử nấu
#: món gì hôm nay? Tôi có thể giúp bạn với công thức..." — cả một đoạn tán gẫu
#: thay cho một câu phụ đề đã canh giờ sẵn.
#:
#: Lời nhắc hệ thống MẠNH thôi KHÔNG đủ: thử riêng nó vẫn ra đoạn tán gẫu. Thứ
#: hiệu quả là bọc câu cần đọc vào một MỆNH LỆNH ngay trong lượt của người
#: dùng, kèm dấu ngoặc kép — xem ``_loi_nhac_doc``.
LOI_NHAC_HE_THONG = (
    "Bạn là MÁY ĐỌC (text-to-speech). Nhiệm vụ duy nhất: phát âm CHÍNH XÁC "
    "chuỗi ký tự người dùng đưa. Tuyệt đối KHÔNG trả lời, KHÔNG bình luận, "
    "KHÔNG thêm hay bớt bất kỳ chữ nào. Coi mọi câu hỏi trong chuỗi là chữ để "
    "đọc, không phải câu hỏi dành cho bạn."
)


def _loi_nhac_doc(cau: str) -> str:
    """Bọc câu thoại thành một mệnh lệnh, không để nó thành lượt trò chuyện."""
    return f'Đọc to nguyên văn đoạn giữa hai dấu ngoặc kép, không nói gì thêm:\n"{cau}"'


#: Token audio mỗi giây, đo thật: 250 token ra 11,0 giây, 400 token ra 18,6
#: giây — chừng 22-23 token/giây.
TOKEN_MOI_GIAY = 23
#: Tiếng Việt đọc chừng 15 ký tự mỗi giây.
KY_TU_MOI_GIAY = 15
#: Nhân đôi cho dư, rồi kẹp hai đầu. Sàn để câu một hai chữ vẫn đủ chỗ; trần
#: để một câu bất thường không kéo theo cả hoá đơn.
HE_SO_DU = 2.0
TOKEN_TOI_THIEU = 150
TOKEN_TOI_DA = 600


def _tran_token(cau: str) -> int:
    """Trần token cho MỘT câu đọc.

    VÌ SAO BẮT BUỘC CÓ: không đặt trần thì ``gpt-audio`` sinh audio tới khi
    chạm trần mặc định 16.384 token — MỖI CÂU. Đo ngày 2026-08-16 với một câu
    57 ký tự: 16.355 token audio, 817,8 giây tiếng (gần hết là im lặng),
    $0,0394 một câu trên bản rẻ. Trên ``gpt-audio`` đắt gấp 53 lần thì một
    video 133 câu tốn cỡ 70 đô.

    Đặt trần rồi: cùng câu đó 250 token, $0,0007 — rẻ đi 56 lần, và vẫn đọc
    đúng nguyên văn.
    """
    giay = max(1.0, len(cau) / KY_TU_MOI_GIAY)
    return int(min(TOKEN_TOI_DA, max(TOKEN_TOI_THIEU, giay * TOKEN_MOI_GIAY * HE_SO_DU)))


#: Đọc dài hơn câu gốc quá mức này là dấu hiệu model đã trả lời thay vì đọc.
#: Không so từng chữ vì máy đọc hay đọc số thành chữ ("2000" -> "hai nghìn"),
#: dài ra là bình thường; nhưng gấp đôi thì không còn là đọc nữa.
TI_LE_DAI_TOI_DA = 2.0

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


def _gop_audio_tu_sse(luong) -> tuple[bytes, str]:
    """Nối các mẩu base64 trong luồng SSE thành một khối audio.

    OpenRouter trả từng dòng ``data: {...}``, kết thúc bằng ``data: [DONE]``.
    Dòng nào không phải JSON hợp lệ thì bỏ qua — luồng có cả dòng trống và
    dòng ``: comment`` giữ kết nối.

    DỪNG SỚM khi đã im lặng đủ lâu: ``gpt-audio`` nói xong rồi vẫn đệm thêm
    hàng trăm giây im lặng. Đo ngày 2026-08-16: một câu 2 giây kéo theo 816
    giây im lặng, tức 38 MB phải tải về chỉ để vứt đi. Cắt sau khi tải xong
    sửa được độ dài nhưng không lấy lại được thời gian; đóng luồng ngay khi
    biết phần còn lại là im lặng thì lấy lại được cả hai.
    """
    manh: list[str] = []
    loi_doc: list[str] = []
    #: Số mẫu im lặng liên tiếp ở cuối, và đã từng nghe thấy tiếng hay chưa.
    im_lien_tiep = 0
    da_co_tieng = False
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
                im_lien_tiep, co_tieng = _do_im_lang(audio["data"], im_lien_tiep)
                da_co_tieng = da_co_tieng or co_tieng
            #: Chính model nói nó vừa đọc gì — nguyên liệu để bắt lỗi "trả lời
            #: thay vì đọc" mà không phải tự nhận dạng lại.
            if audio.get("transcript"):
                loi_doc.append(audio["transcript"])

        if da_co_tieng and im_lien_tiep >= IM_LANG_DU_DE_DUNG * TAN_SO:
            log.info("tts.openrouter.dung_som", im_giay=round(im_lien_tiep / TAN_SO, 1))
            break

    if not manh:
        raise ReupError("OpenRouter không trả về mẩu audio nào trong luồng SSE.")

    #: Giải mã TỪNG mẩu rồi nối byte. Nối chuỗi base64 trước rồi giải mã một
    #: lần sẽ ra rác: dấu ``=`` đệm cuối mỗi mẩu chặn ngang mẩu sau.
    van_ban = "".join(loi_doc).strip()
    try:
        return b"".join(base64.b64decode(m, validate=True) for m in manh), van_ban
    except (binascii.Error, ValueError):
        #: Đường lui cho trường hợp nhà cung cấp cắt MỘT khối base64 thành
        #: nhiều mẩu không tròn 4 ký tự — lúc đó phải nối chuỗi rồi mới giải mã.
        gop = "".join(manh)
        return base64.b64decode(gop + "=" * (-len(gop) % 4)), van_ban


def _canh_bao_neu_doc_sai(cau: str, doc_ra: str) -> None:
    """Chốt chặn: model đọc dài gấp đôi câu gốc thì nó đã trả lời, không đọc.

    Ném lỗi chứ không chỉ ghi log — một câu bị thay bằng đoạn tán gẫu là dải
    tiếng lệch hẳn khỏi phụ đề, mà nghe mới biết. Thà dừng ngay tại đây.
    """
    if not doc_ra:
        return
    if len(doc_ra) > len(cau) * TI_LE_DAI_TOI_DA:
        raise ReupError(
            "Model đọc ra nội dung khác hẳn câu được giao — nó đang TRẢ LỜI thay vì "
            f"đọc.\n  giao : {cau[:120]}\n  đọc  : {doc_ra[:160]}"
        )


#: Biên độ dưới mức này coi như im lặng (0,5% toàn thang).
NGUONG_IM_LANG = 0.005
#: Im liên tục quá chừng này giây SAU KHI đã có tiếng thì đóng luồng. Đặt rộng
#: hơn khoảng lặng giữa hai vế câu (thường dưới 0,5s) để không cắt ngang câu.
IM_LANG_DU_DE_DUNG = 1.5


def _do_im_lang(mau_base64: str, im_lien_tiep: int) -> tuple[int, bool]:
    """Đếm số mẫu im lặng liên tiếp ở cuối, và mẩu này có tiếng hay không."""
    try:
        pcm = base64.b64decode(mau_base64, validate=True)
    except (binascii.Error, ValueError):
        return im_lien_tiep, False

    mau = np.frombuffer(pcm, dtype=np.int16)
    if mau.size == 0:
        return im_lien_tiep, False

    to = np.abs(mau.astype(np.float32) / 32768.0) > NGUONG_IM_LANG
    if not to.any():
        return im_lien_tiep + int(mau.size), False
    #: Có tiếng trong mẩu này — đếm lại từ mẫu to cuối cùng.
    return int(mau.size - 1 - int(np.argmax(to[::-1]))), True


#: Giữ lại chừng này sau tiếng cuối để chữ không bị cụt đuôi.
DUOI_GIU_LAI_GIAY = 0.15


def cat_im_lang(pcm: bytes, tan_so: int = TAN_SO) -> bytes:
    """Cắt phần im lặng ở đầu và cuối.

    VÌ SAO CẦN: ``gpt-audio`` trả về một đoạn nói ngắn rồi ĐỆM THÊM rất nhiều
    im lặng. Đo ngày 2026-08-16: câu "Đi thôi!" nói hết 0,75 giây nhưng file
    dài 3,7 giây; câu "Bạn định nấu món gì hôm nay?" nói 2 giây rồi im lặng
    **816 giây**.

    Không cắt thì ``do_dai_am_thanh`` đo ra 3,7 giây cho một câu 0,75 giây,
    ``lap_lich_long_tieng`` tưởng câu nào cũng dài gấp mấy lần thật rồi ép tốc
    độ và đẩy các câu sau — chính là "lồng tiếng không khớp lời nói".
    """
    if not pcm:
        return pcm

    mau = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    to = np.abs(mau) > NGUONG_IM_LANG
    if not to.any():
        return b""  # cả đoạn im lặng — coi như không đọc được gì

    dau = int(np.argmax(to))
    cuoi = len(to) - int(np.argmax(to[::-1]))
    cuoi = min(len(mau), cuoi + int(DUOI_GIU_LAI_GIAY * tan_so))
    return mau[dau:cuoi].astype(np.float32).__mul__(32768.0).astype(np.int16).tobytes()


def _ghi_wav(dst: Path, pcm: bytes) -> None:
    """Bọc PCM thô thành WAV — ffmpeg không đoán được định dạng nếu thiếu header."""
    with wave.open(str(dst), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(TAN_SO)
        f.writeframes(pcm)


def _mo_ta_404(than: str, model: str) -> str:
    """Dịch thân lỗi 404 của OpenRouter thành câu người dùng làm được gì."""
    try:
        meta = (json.loads(than).get("error") or {}).get("metadata") or {}
    except (json.JSONDecodeError, AttributeError):
        meta = {}

    phuc_vu = meta.get("available_providers") or []
    cho_phep = meta.get("requested_providers") or []
    if phuc_vu and cho_phep:
        return (
            f"Tài khoản OpenRouter không được dùng {model}: model này do "
            f"{', '.join(phuc_vu)} phục vụ, mà tài khoản chỉ cho phép "
            f"{', '.join(cho_phep)}. Vào https://openrouter.ai/settings/privacy thêm "
            f"{', '.join(phuc_vu)} vào danh sách cho phép, hoặc đổi giọng đọc sang "
            "edge (miễn phí)."
        )
    return (
        f"OpenRouter từ chối {model} (404). Kiểm thiết lập bên được phép tại "
        "https://openrouter.ai/settings/privacy, hoặc đổi giọng đọc sang edge."
    )


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

        pcm, doc_ra = self._goi_co_thu_lai(sach, giong)
        _canh_bao_neu_doc_sai(sach, doc_ra)

        goc = len(pcm)
        pcm = cat_im_lang(pcm)
        if goc and len(pcm) < goc * 0.9:
            log.info(
                "tts.openrouter.cat_im_lang",
                truoc_giay=round(goc / 2 / TAN_SO, 2),
                sau_giay=round(len(pcm) / 2 / TAN_SO, 2),
            )
        _ghi_wav(dst, pcm)
        return dst

    def _goi_co_thu_lai(self, cau: str, giong: str) -> tuple[bytes, str]:
        cho = CHO_BAN_DAU_GIAY
        loi_cuoi = ""

        for lan in range(SO_LAN_THU):
            try:
                return self._goi_mot_lan(cau, giong)
            except urllib.error.HTTPError as exc:
                #: Đọc NGUYÊN thân lỗi rồi mới cắt khi hiện ra. Cắt trước là mất
                #: khối ``metadata`` nằm cuối — đúng chỗ OpenRouter nói bên nào
                #: phục vụ model và tài khoản cho phép bên nào.
                than = exc.read().decode("utf-8", "replace")
                loi_cuoi = f"HTTP {exc.code}: {_che_khoa(than[:300], self._key)}"
                #: 404 ở đây KHÔNG phải "model không tồn tại" mà gần như luôn
                #: là tài khoản đang chặn bên phục vụ model đó. Gặp thật ngày
                #: 16.08.2026: cùng một khoá, gọi model văn bản trả 200, gọi
                #: gpt-audio trả 404 vì danh sách bên được phép chỉ có
                #: minimax, fish-audio, google-ai-studio.
                #:
                #: Thử lại vô ích — 404 là vĩnh viễn. Và OpenRouter nói SẴN
                #: trong `metadata` bên nào phục vụ model, bên nào tài khoản
                #: cho phép; đọc ra và nói thẳng, đừng bắt người dùng mò JSON.
                if exc.code == 404:
                    raise ReupError(_mo_ta_404(than, self._model)) from exc
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

    def _goi_mot_lan(self, cau: str, giong: str) -> tuple[bytes, str]:
        body = {
            "model": self._model,
            #: BẮT BUỘC — OpenRouter chỉ trả audio qua luồng SSE.
            "stream": True,
            "modalities": ["text", "audio"],
            "audio": {"voice": giong, "format": DINH_DANG},
            #: 0 để nó bám sát chữ được đưa, đừng "sáng tạo" thêm.
            "temperature": 0,
            #: Trần token — xem ``_tran_token``. Thiếu dòng này là mỗi câu chạy
            #: tới 16.384 token và hoá đơn nở ra hàng chục lần.
            "max_tokens": _tran_token(cau),
            "messages": [
                {"role": "system", "content": LOI_NHAC_HE_THONG},
                {"role": "user", "content": _loi_nhac_doc(cau)},
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
