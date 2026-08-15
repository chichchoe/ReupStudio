"""Chèn dòng chữ hook vào 3 giây đầu video + tính khoảng cắt nếu mở đầu ì ạch
(M4-WK-03).

Hàm THUẦN: không đụng DB, không đụng ffmpeg thật (chỉ DỰNG chuỗi filter dạng
string), không import celery.

Vì sao module này tồn tại — CLAUDE.md ghi thẳng: "Hook 3 giây đầu quyết định
retention. Đừng coi nhẹ bước này." Người xem quyết định lướt tiếp hay ở lại
trong 3 giây đầu; dòng chữ hook đập vào mắt ngay từ khung hình đầu tiên, và
việc cắt bỏ đoạn mở đầu im lặng/lê thê trước khi nội dung thật bắt đầu, là hai
đòn bẩy trực tiếp nhất cho retention mà module này cung cấp.

``hook_box`` dùng lại ``SafeArea`` của Task 2 (``safe_area.py``) để đặt hook ở
dải TRÊN của vùng an toàn nền tảng — KHÔNG BAO GIỜ đè lên phụ đề, vốn nằm sát
ĐÁY vùng an toàn (xem ``ffmpeg/burn.py::build_force_style`` dùng
``margin_v_pixels`` của cùng module ``safe_area.py``).
"""

from __future__ import annotations

from reup_core.logging import get_logger

from ..cues import Cue
from .safe_area import SafeArea

log = get_logger(__name__)

#: Hook chỉ hiện trong 3 giây đầu video.
HOOK_DURATION_SEC = 3.0

#: Chiều cao khối hook, phần trăm chiều cao khung hình. Neo vào mép TRÊN của
#: vùng an toàn (``safe.top`` — dưới thanh trạng thái/nút back của app nền
#: tảng), tách biệt hẳn khỏi phụ đề vốn nằm sát mép DƯỚI vùng an toàn. Không
#: hardcode theo pixel (luật số 5 CLAUDE.md) — luôn là phần trăm.
HOOK_BOX_HEIGHT_FRAC = 0.14

#: Cỡ chữ hook = chiều cao khối hook (pixel) nhân tỉ lệ này. 0.6 để chữ chiếm
#: phần lớn khối nhưng còn đệm xung quanh, không sát mép hộp nền.
_HOOK_FONT_SIZE_RATIO = 0.6
#: Sàn cỡ chữ, phòng khi video quá thấp (hiếm, nhưng tránh chữ nhỏ tới mức
#: không đọc được).
_HOOK_MIN_FONT_SIZE_PX = 24

#: Số dòng tối đa của hook. Hơn 2 dòng thì không còn là "hook" mà là một đoạn
#: văn — người xem lướt qua trước khi đọc hết.
HOOK_MAX_LINES = 2

#: Bề rộng từng ký tự theo tỉ lệ cỡ chữ, gom thành nhóm bội số 0,05.
#:
#: ``drawtext`` không cho hỏi bề rộng chữ trước khi render (``text_w`` chỉ tồn
#: tại lúc ffmpeg chạy), nên phải ước lượng ở tầng Python. Bản trước dùng MỘT
#: con số phẳng 0,5 cho mọi ký tự — coi "W" bằng "i" trong khi chúng chênh nhau
#: hơn ba lần.
#:
#: Bảng này ĐO thật (2026-08-15) trên Verdana / Arial / Arial Bold / Helvetica —
#: bốn font sans mà fontconfig hay trả về cho ``Sans``, lấy giá trị LỚN NHẤT của
#: mỗi ký tự rồi làm tròn LÊN: ước dư thì chữ hơi nhỏ, ước thiếu thì hook bị cắt
#: cụt hai đầu.
#:
#: Vì sao đáng làm: câu mẫu 47 ký tự rộng 24,6 lần cỡ chữ khi viết thường nhưng
#: 29,2 lần khi viết HOA. Ước phẳng cho ra 23,5 — thiếu 5% với chữ thường, thiếu
#: 24% với chữ HOA. Hook ngắn thì hay viết HOA.
_NHOM_BE_RONG: dict[float, str] = {
    0.30: "'ilìíỉị",
    0.35: " fj",
    0.40: "!,.t",
    0.45: "()-/:;I[\\]r|ÌÍĨĩỈỊ",
    0.50: '"',
    0.55: "z",
    0.60: "Jaceksvxyàáâãèéêýăạảấầẩẫậắằẳẵặẹẻẽếềểễệỳỵỷỹ",
    0.65: "$*0123456789?FLT_`bdghnopqu{}òóôõùúđũọỏốồổỗộụủ",
    0.70: "EPSVXYZÈÉÊÝẸẺẼẾỀỂỄỆỲỴỶỸ",
    0.75: "&ABCHKNRUÀÁÂÃÙÚĂŨơưẠẢẤẦẨẪẬẮẰẲẴẶớờởỡợỤỦứừửữự",
    0.80: "DGOQÒÓÔÕĐỌỎỐỒỔỖỘ",
    0.85: "#+<=>M^w~",
    0.90: "ƠƯỚỜỞỠỢỨỪỬỮỰ",
    1.00: "Wm",
    1.05: "@",
    1.10: "%",
}

#: Ký tự không có trong bảng tính là ô ĐẦY. Nguồn của dự án là video Trung
#: Quốc: bản dịch sót vài ký tự Hán là chuyện có thật, mà chữ Hán đúng là rộng
#: bằng một ô đầy. Đoán hẹp cho ký tự lạ là đoán về phía tràn khung.
_BE_RONG_MAC_DINH = 1.0

_BE_RONG_KY_TU: dict[str, float] = {
    ky_tu: ti_le for ti_le, day in _NHOM_BE_RONG.items() for ky_tu in day
}

#: Mỗi lần thu nhỏ giảm 8% cỡ chữ. Nhỏ hơn thì lặp quá nhiều vòng, lớn hơn thì
#: nhảy cóc qua cỡ vừa đẹp.
_FONT_SHRINK_STEP = 0.92

#: Chấp nhận chữ nhỏ hơn tới 10% để hook gọn vào ÍT DÒNG hơn. Một dòng đọc
#: nhanh hơn hai dòng, mà chênh lệch cỡ chữ ở mức này mắt gần như không thấy —
#: "Xem hết nhé" vừa một dòng ở cỡ 115 thì đừng bẻ làm hai dòng chỉ để được
#: cỡ 125.
_UU_TIEN_IT_DONG = 0.9

#: Trắng trên nền đen mờ — tương phản cao, KHÁC màu phụ đề (phụ đề vàng, xem
#: ``build_force_style``) để hai lớp chữ không lẫn vào nhau khi ở gần nhau.
_HOOK_FONT_COLOR = "white"
_HOOK_BOX_COLOR = "black@0.55"
_HOOK_BOX_BORDER_PX = 12

#: Cắt bớt đầu video nếu cue phụ đề đầu tiên xuất hiện QUÁ TRỄ (mở đầu im lặng
#: quá lâu). Trùng giá trị mặc định tham số ``max_silent_head_sec`` bên dưới,
#: đặt tên hằng số riêng để chỗ gọi khác (Task 6) tham chiếu được nếu cần.
DEFAULT_MAX_SILENT_HEAD_SEC = 2.0


def hook_box(safe: SafeArea) -> tuple[float, float, float, float]:
    """Vị trí hook theo phần trăm ``(x, y, w, h)`` — nằm PHÍA TRÊN vùng phụ đề.

    Neo vào mép trên của vùng an toàn (``safe.top``), rộng hết bề ngang vùng an
    toàn (trừ lề trái/phải ``safe.left``/``safe.right``). Chiều cao lấy
    ``HOOK_BOX_HEIGHT_FRAC``, nhưng KẸP lại theo phần diện tích dọc còn trống
    của vùng an toàn (``1 - safe.top - safe.bottom``) — nền tảng nào có lề
    trên/dưới đặc biệt lớn thì hộp hook tự thu nhỏ, không bao giờ tràn xuống
    đè lên phụ đề nằm sát đáy vùng an toàn (kiểm bằng ``fits_in_safe_area`` của
    Task 2 trong test, không viết lại phép kiểm ở đây).
    """
    x = safe.left
    y = safe.top
    w = max(0.0, 1 - safe.left - safe.right)
    available_h = max(0.0, 1 - safe.top - safe.bottom)
    h = min(HOOK_BOX_HEIGHT_FRAC, available_h)
    return (x, y, w, h)


def be_rong_chu(text: str, font_size: int) -> float:
    """Bề rộng ước lượng của một dòng chữ, tính bằng pixel.

    Cộng bề rộng từng ký tự theo ``_BE_RONG_KY_TU``. Đây là ƯỚC LƯỢNG, không
    phải số đo từ chính font mà ffmpeg sẽ dùng — font đó do fontconfig chọn lúc
    render nên khác nhau giữa máy dev và Docker. Bảng lấy giá trị lớn nhất của
    bốn font sans phổ biến nên sai số nghiêng về phía an toàn.
    """
    return sum(_BE_RONG_KY_TU.get(ky_tu, _BE_RONG_MAC_DINH) for ky_tu in text) * font_size


def _ngat_dong(text: str, max_width_px: float, font_size: int) -> list[str]:
    """Chia câu thành các dòng không rộng quá ``max_width_px``, không cắt giữa từ.

    Từ dài hơn cả dòng vẫn được giữ nguyên trên một dòng riêng — thà một dòng
    hơi tràn còn hơn mất chữ.
    """
    lines: list[str] = []
    hien_tai = ""
    for tu in text.split():
        thu = f"{hien_tai} {tu}".strip()
        if hien_tai and be_rong_chu(thu, font_size) > max_width_px:
            lines.append(hien_tai)
            hien_tai = tu
        else:
            hien_tai = thu
    if hien_tai:
        lines.append(hien_tai)
    return lines


def fit_hook_text(
    text: str,
    *,
    box_w_px: int,
    box_h_px: int,
    max_lines: int = HOOK_MAX_LINES,
    min_font_size: int = _HOOK_MIN_FONT_SIZE_PX,
) -> tuple[str, int]:
    """Trả về ``(text đã xuống dòng, cỡ chữ vừa khối hook)``.

    ``drawtext`` không tự xuống dòng và không cho hỏi kích thước chữ trước khi
    render (``text_w``/``text_h`` chỉ tồn tại lúc ffmpeg chạy), nên phải ước
    lượng ở đây — xem ``be_rong_chu``. Không có bước này, câu hook dài hơn khối
    bị cắt cụt cả hai đầu, đúng lỗi quan sát được trên khung hình render thật
    ngày 2026-08-14.

    Ép theo CẢ HAI chiều:

    - ngang: bề rộng ĐO THEO TỪNG KÝ TỰ của mỗi dòng không vượt ``box_w_px``;
    - dọc: ``số dòng × cỡ chữ`` không vượt ``box_h_px`` — cỡ chữ mặc định
      (``box_h × 0,6``) là cỡ dành cho MỘT dòng, để nguyên mà xuống hai dòng
      thì chữ tràn xuống dưới khối và đè vào video.

    Thu nhỏ dần tới khi vừa, nhưng KHÔNG xuống dưới ``min_font_size``: chữ nhỏ
    tới mức không đọc được cũng vô dụng như chữ bị cắt, mà lại khó phát hiện
    hơn.
    """
    co_dau = max(min_font_size, round(box_h_px * _HOOK_FONT_SIZE_RATIO))
    cleaned = " ".join(text.split())
    if not cleaned:
        return "", co_dau

    #: Thử lần lượt 1 dòng, 2 dòng… và với mỗi số dòng tìm cỡ chữ LỚN NHẤT còn
    #: vừa khối. Vòng thu nhỏ đơn thuần dừng ngay lúc "vừa" nên hay chốt ở hai
    #: dòng dù câu hoàn toàn vừa một dòng chỉ nhỏ hơn vài pixel.
    phuong_an: list[tuple[int, list[str]]] = []
    for so_dong in range(1, max_lines + 1):
        co = co_dau
        while True:
            dong = _ngat_dong(cleaned, box_w_px, co)
            #: Không chỉ đếm dòng: một TỪ dài hơn cả dòng không ngắt được, nên
            #: vẫn phải kiểm bề rộng thật của từng dòng.
            vua = (
                len(dong) <= so_dong
                and all(be_rong_chu(d, co) <= box_w_px for d in dong)
                and len(dong) * co <= box_h_px
            )
            if vua:
                phuong_an.append((co, dong))
                break
            if co <= min_font_size:
                break
            co = max(min_font_size, int(co * _FONT_SHRINK_STEP))

    if not phuong_an:
        #: Không cách nào vừa — thà chữ hơi tràn ở cỡ sàn còn hơn mất chữ.
        return "\n".join(_ngat_dong(cleaned, box_w_px, min_font_size)), min_font_size

    to_nhat = max(co for co, _ in phuong_an)
    for co, dong in phuong_an:  # đã theo thứ tự số dòng tăng dần
        if co >= to_nhat * _UU_TIEN_IT_DONG:
            return "\n".join(dong), co
    raise AssertionError("không thể tới đây: phương án cỡ lớn nhất luôn thoả điều kiện")


def _escape_drawtext_text(text: str) -> str:
    """Escape text cho tham số ``text=`` của filter ``drawtext``.

    Escape 2 TẦNG theo đúng cú pháp filtergraph ffmpeg nói chung (không riêng
    drawtext) — xem ``man ffmpeg-filters``, mục "Notes on filtergraph
    escaping":

    - Tầng 1 (escape riêng giá trị option): ``\\`` và ``:`` và ``'`` là ký tự
      đặc biệt, escape bằng cách thêm ``\\`` phía trước.
    - Tầng 2 (escape khi nhúng vào toàn bộ mô tả filtergraph): ``\\`` và ``'``
      lại đặc biệt LẦN NỮA (escape thêm một lớp), và các ký tự cấu trúc
      filtergraph — dấu phẩy ``,`` (phân tách filter trong cùng một chain),
      dấu chấm phẩy ``;`` (phân tách các chain), ``[`` ``]`` (bọc tên nhãn
      pad) — cũng phải escape ở tầng này (xem ``man ffmpeg-filters``, mục
      "Filtering introduction": "Filters in the same linear chain are
      separated by commas, and distinct linear chains of filters are
      separated by semicolons... labelled by names enclosed in square
      brackets").

    Gộp 2 tầng, hiệu ứng RÒNG trên từng ký tự gốc:
    ``\\`` -> 4 dấu ``\\``,  ``:`` -> 2 dấu ``\\`` + ``:``,
    ``'`` -> 3 dấu ``\\`` + ``'``,
    ``,`` / ``;`` / ``[`` / ``]`` -> 1 dấu ``\\`` + chính ký tự đó.

    Đã đối chiếu khớp TỪNG KÝ TỰ với ví dụ chính thức trong tài liệu ffmpeg
    (chuỗi ``this is a 'string': may contain one, or more, special
    characters`` -> ``this is a \\\\\\'string\\\\\\'\\\\: may contain
    one\\, or more\\, special characters`` khi nhúng vào
    ``drawtext=text=...``) — xem ``tests/test_hook.py``. ``;``/``[``/``]``
    dùng đúng công thức escape 1 lớp như ``,`` (cùng là ký tự cấu trúc tầng 2,
    không đặc biệt ở tầng 1) — đã xác nhận lại bằng ffmpeg thật, không chỉ suy
    diễn từ công thức của ``,`` (xem báo cáo Task 5, phần "Sửa nối tiếp").

    Thứ tự escape BẮT BUỘC: ``\\`` trước tiên. Escape ``\\`` sau cùng sẽ nhân
    đôi luôn cả những dấu ``\\`` do các bước escape ``:``/``'``/``,``/``;``/
    ``[``/``]`` phía sau vừa sinh ra — sai hoàn toàn. Vì mỗi bước sau chỉ thay
    ký tự GỐC, không đụng tới ``\\`` đã escape ở bước trước, thứ tự escape
    các ký tự còn lại với nhau không quan trọng.

    ``\n`` (xuống dòng) KHÔNG phải ký tự đặc biệt của filtergraph — không
    escape (đã kiểm bằng ffmpeg thật: không gây lỗi cú pháp).

    KHÔNG escape ``%``: ``build_hook_filter`` đặt ``expansion=none`` cho
    drawtext — tắt hẳn cơ chế nội suy ``%{...}`` mặc định của drawtext, nên
    ``%`` trở thành ký tự thường, in verbatim, không cần (và không được) thêm
    ``\\`` phía trước — xem lý do đầy đủ trong docstring của
    ``build_hook_filter``.
    """
    escaped = text
    escaped = escaped.replace("\\", "\\" * 4)
    escaped = escaped.replace(":", "\\" * 2 + ":")
    escaped = escaped.replace("'", "\\" * 3 + "'")
    for special in (",", ";", "[", "]"):
        escaped = escaped.replace(special, "\\" + special)
    return escaped


def build_hook_filter(
    text: str,
    box: tuple[float, float, float, float],
    video_width: int,
    video_height: int,
) -> str:
    """Chuỗi filter ``drawtext`` của ffmpeg, chỉ hiện trong 0–``HOOK_DURATION_SEC``.

    ``box`` là ``(x, y, w, h)`` theo PHẦN TRĂM 0–1 (thường lấy từ
    ``hook_box``). Đổi sang pixel CHỈ Ở ĐÂY, sát chỗ dựng filter — không có
    toạ độ pixel nào lọt ra khỏi hàm này (luật số 5 CLAUDE.md).

    ``expansion=none``: TẮT HẲN cơ chế "text expansion" mặc định
    (``expansion=normal``) của drawtext — cơ chế đó hiểu ``%{...}`` là lệnh
    nội suy (VD ``%{metadata:...}``, ``%{eif:...}`` — xem ``man
    ffmpeg-filters``, mục "Text expansion") và hiểu ``\\X`` (backslash + bất
    kỳ ký tự nào) luôn nội suy thành ``X``. Hook text đến từ bản dịch tiếng
    Việt (LLM hoặc người dùng nhập) — nội dung không kiểm soát được. Nếu giữ
    ``expansion=normal`` và bản dịch chẳng may sinh ra chuỗi trông giống
    ``%{...}``, drawtext sẽ CỐ NỘI SUY nó thay vì in ra chữ y nguyên — đúng
    kiểu "chèn nội dung ngoài ý muốn" mà task này cảnh báo, và escape ``%``
    thủ công cho đúng dưới ``expansion=normal`` còn phải tính cả tương tác
    với escape ``\\`` ở tầng filtergraph ngoài (dễ sai hơn hẳn). Tắt hẳn
    expansion là lựa chọn AN TOÀN HƠN escape thủ công: ``%`` trở thành ký tự
    thường, in verbatim, không cần escape gì thêm (xem
    ``_escape_drawtext_text``).

    Giá trị ``text=`` KHÔNG bọc thêm cặp nháy đơn ``'...'`` — đúng dạng ví dụ
    chính thức của ``man ffmpeg-filters`` (``drawtext=text=this is a
    \\\'string\\\'\\: ...``, không có nháy đơn bao ngoài). Đã thử bọc thêm
    nháy đơn lúc phát triển: ffmpeg báo lỗi cú pháp thật (``No option name
    near ...``) vì khi đó chồng thêm một tầng escape thứ ba (tầng "nội dung
    trong cặp nháy") lên trên 2 tầng đã tính sẵn trong ``_escape_drawtext_text``
    — sai. Đã xác nhận bằng ffmpeg thật (xem ``scripts/try_hook.py``): bỏ cặp
    nháy ngoài, chuỗi 2 tầng escape parse sạch, dừng đúng ở bước "không tìm
    thấy filter drawtext" (bản ffmpeg máy dev không build kèm libfreetype) chứ
    không phải lỗi cú pháp.
    """
    x, y, w, h = box
    box_x_px = round(x * video_width)
    box_y_px = round(y * video_height)
    box_w_px = round(w * video_width)
    box_h_px = round(h * video_height)

    #: Đo và ép chữ vừa khối hook TRƯỚC khi escape — escape sinh thêm dấu
    #: ``\`` vào chuỗi, đếm ký tự sau đó là đếm nhầm.
    text, font_size = fit_hook_text(text, box_w_px=box_w_px, box_h_px=box_h_px)
    escaped_text = _escape_drawtext_text(text)

    # text_w/text_h là biến ffmpeg tính lúc render (kích thước chữ thật theo
    # font/nội dung) — không tính trước được ở tầng Python, nên căn giữa chữ
    # trong khối hook bằng biểu thức, không bằng số cứng.
    x_expr = f"{box_x_px}+({box_w_px}-text_w)/2"
    y_expr = f"{box_y_px}+({box_h_px}-text_h)/2"

    log.debug(
        "hook.build_filter",
        box_px=(box_x_px, box_y_px, box_w_px, box_h_px),
        font_size=font_size,
    )

    return (
        "drawtext="
        f"text={escaped_text}:"
        "expansion=none:"
        f"fontsize={font_size}:"
        f"fontcolor={_HOOK_FONT_COLOR}:"
        "box=1:"
        f"boxcolor={_HOOK_BOX_COLOR}:"
        f"boxborderw={_HOOK_BOX_BORDER_PX}:"
        f"x={x_expr}:"
        f"y={y_expr}:"
        f"enable='between(t,0,{HOOK_DURATION_SEC})'"
    )


def trim_slow_intro(
    cues: list[Cue], *, max_silent_head_sec: float = DEFAULT_MAX_SILENT_HEAD_SEC
) -> float:
    """Số giây nên cắt bỏ ở đầu nếu mở đầu im lặng quá lâu. ``0`` nếu không cần.

    Cue phụ đề đầu tiên bắt đầu càng trễ nghĩa là càng nhiều giây đầu video
    không có lời nói (thường là logo intro, cảnh dạo đầu của kênh nguồn) —
    đúng loại "mở đầu lê thê" giết retention mà CLAUDE.md cảnh báo. Không có
    cue nào, hoặc cue đầu tiên bắt đầu trong ngưỡng ``max_silent_head_sec``,
    trả về ``0`` (không cắt gì) — hàm này KHÔNG tự chạy ffmpeg, chỉ tính số
    giây cần cắt, chỗ gọi (Task 6) mới thật sự cắt.
    """
    if not cues:
        return 0.0
    first_start = min(cue.start for cue in cues)
    if first_start <= max_silent_head_sec:
        return 0.0
    return first_start
