# Kế hoạch C — Thư viện giọng (Cấu hình → Giọng đọc)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một chỗ duy nhất quản mọi giọng — giọng dựng sẵn của Edge/Gemini/OpenRouter LẪN giọng clone tự thu. Người dùng thêm giọng từ bốn nguồn, nghe thử cùng một câu để so sánh sòng phẳng, rồi chọn giọng ở tab Chờ dịch bằng **một ô** thay vì ba.

**Architecture:** Bảng `giong_doc` là nguồn sự thật duy nhất (seed từ danh sách đang hardcode trong `video_service`). Bốn nguồn giọng đổ về MỘT luồng worker: chuẩn hoá ffmpeg → Whisper gõ chữ → người dùng sửa → cổng chất lượng → mã hoá mẫu (điểm nối Kế hoạch B) → đọc thử. Cổng chất lượng là hàm THUẦN nhận số đo, đặt ở `reup_core` để cả API lẫn worker dùng chung. Giao diện thêm một mục vào trang Cấu hình, đúng khuôn mục "Nhà cung cấp AI" đã có.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Celery, FFmpeg, faster-whisper (ĐÃ cài), Next.js App Router, TanStack Query, Tailwind, vitest.

**Spec:** `docs/superpowers/specs/2026-08-20-duyet-ban-dich-va-long-tieng-design.md` (Phần C, mục C1→C7)

## Kế hoạch này chạy ĐỘC LẬP với Kế hoạch B

Bước `encode_reference()` ở C3 chỉ áp dụng cho nhà cung cấp `fish_mlx`, mà `fish_mlx` là Kế hoạch B — **chưa làm**. Kế hoạch C tuyệt đối không được chờ B. Ba chỗ nối, và cả ba đều có đường lui chạy được ngay hôm nay:

| Điểm nối | Khi CHƯA có B (hôm nay) | Khi có B (Kế hoạch B cắm vào) |
|---|---|---|
| `worker/src/tts/reference.py::ma_hoa_mau()` | `co_fish_tai_may()` trả `False` → trả `False`, KHÔNG ném lỗi, `giong_doc.co_ma_hoa = false`, ghi log `giong.chua_co_fish` | B tạo `worker/src/tts/fish_mlx.py` có `encode_reference()`; hàm này tự thấy và ghi `codes.npz` |
| `worker/src/tts/reference.py::chon_nha_doc_thu()` | Giọng `fish_mlx` đọc thử bằng **Edge**, và GHI LẠI vào cột `nghe_thu_bang` để giao diện nói ra | Trả thẳng `fish_mlx`, không rơi về Edge nữa |
| `worker/src/tts/base.py::lay_provider("fish_mlx")` | Không có module `fish_mlx` → trả `EdgeTTS()` kèm log cảnh báo | B thay nhánh này bằng `from .fish_mlx import FishMlxTTS` |

Nhờ ba chỗ đó, **giọng clone vẫn thêm được, lưu được, nghe thử được** trước khi B tồn tại. Kế hoạch B sau này chỉ phải sửa đúng ba hàm trên, không phải sửa bảng, API hay giao diện.

## Global Constraints

- Python 3.12, type hint bắt buộc cho mọi hàm public. `pathlib.Path`, không dùng chuỗi đường dẫn.
- **Mọi đường dẫn file đi qua `packages/reup_core/src/reup_core/paths.py`.** Không `os.path.join`, không f-string ghép path ở chỗ khác.
- `routers/` chỉ validate input và gọi service. `services/` chứa logic nghiệp vụ, KHÔNG biết gì về HTTP/FastAPI. `models/` chỉ định nghĩa bảng, không có method nghiệp vụ.
- `pipeline/` là hàm THUẦN: KHÔNG import celery, KHÔNG chạm DB. `tasks/` chỉ điều phối 10–30 dòng.
- Việc chạm mạng hoặc chạy >2 giây phải qua Celery; endpoint trả `202 {task_id}`, không bao giờ chờ.
- `task_bridge` gửi task theo TÊN và **bắt buộc truyền `queue=`** — app Celery của API không mang `task_routes` của worker; thiếu nó task rơi vào hàng không ai nghe, API vẫn trả 202 và không có gì xảy ra.
- **Module task mới phải thêm dòng import tay trong `worker/src/celery_app.py`.** `autodiscover_tasks` KHÔNG bắt được nó (`src/tasks/__init__.py` đang rỗng).
- Đổi schema DB thì phải có migration Alembic. Không hardcode giới hạn nền tảng, đường dẫn, API key.
- FFmpeg: **không `shell=True`**, luôn có `timeout`, giữ 2000 ký tự cuối stderr khi lỗi, ghi file tạm rồi `rename` sang tên chính thức.
- Mỗi bước pipeline **idempotent**: chạy lại lần 2 cho cùng kết quả; file output đã tồn tại và hợp lệ thì bỏ qua.
- Không `print` trong code chạy thật; dùng `structlog` qua `reup_core.logging.get_logger`. Không `except: pass`. Exception có nghĩa, kế thừa `ReupError`/`ApiError`.
- Type frontend **sinh từ OpenAPI** (`npx openapi-typescript`), không gõ tay interface trùng backend.
- Web: server component mặc định, `'use client'` chỉ khi cần state/event. Fetch qua `lib/api.ts`. **Không polling** để lấy tiến trình — đã có WebSocket.
- Tailwind dùng biến đã định nghĩa (`bg-panel`, `bg-panel2`, `text-muted`, `border-border`, `text-accent`, `text-err`, `text-ok`, `text-warn`), không viết mã màu thô.
- Đặt tên: bảng số nhiều snake_case; endpoint kebab-case; task Celery `động_từ_danh_từ`; component React PascalCase; hook `use` + PascalCase; hằng số magic number phải đặt tên.
- Format trước khi commit: `ruff format . && ruff check --fix .` (Python), `pnpm lint --fix` (web).
- **Một task = một commit.**

## Lệnh test

```bash
cd apps/api && pytest
cd apps/worker && pytest
cd apps/web && pnpm test
```

---

### Task 1: Cổng chất lượng và hằng số dùng chung

Cổng chất lượng là hàm THUẦN nhận SỐ ĐO, tách hẳn khỏi ffmpeg: đo bằng file thật thì test phải kèm file wav, mà file wav trong repo là thứ CLAUDE.md cấm commit. Đặt ở `reup_core` vì cả API (trả cảnh báo ra giao diện) lẫn worker (tính cảnh báo) cùng cần, mà **API không được import code worker**.

**Files:**
- Create: `packages/reup_core/src/reup_core/giong.py`
- Modify: `packages/reup_core/src/reup_core/enums.py`
- Test: `apps/worker/tests/test_cong_chat_luong_giong.py`

`reup_core` chưa có thư mục test riêng; test cho nó nằm ở `apps/worker/tests/` như `test_paths.py` đã làm.

**Interfaces:**
- Produces:
  - `enums.NguonGiong` — `DUNG_SAN`/`TU_THU`/`CAT_TU_FILE`/`THUE_DOC`/`TAM_TU_MAY`
  - `enums.TrangThaiGiong` — `DANG_XU_LY`/`SAN_SANG`/`HONG`
  - `giong.CAU_NGHE_THU: str`, `giong.DOAN_MAU_TAM: str`
  - `giong.DoAmThanh(do_dai_giay: float, rms: float, dinh: float, ti_le_im_lang: float)` — frozen dataclass
  - `giong.CanhBao(ma: str, thong_diep: str)` — frozen dataclass
  - `giong.kiem_chat_luong(do: DoAmThanh) -> list[CanhBao]`
  - `giong.tham_so_goi(*, nha_cung_cap: str, ma_giong: str, model: str, giong_id: str) -> dict[str, str]`

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/worker/tests/test_cong_chat_luong_giong.py`:

```python
"""Cổng chất lượng đoạn mẫu — mẫu tồi thì MỌI video về sau đều tồi.

Đoạn mẫu là cần gạt chất lượng DUY NHẤT của giọng clone (spec B3: tham số sinh
của Fish không mở ra ngoài API). Vì vậy bốn thứ đo được bằng số thì phải đo
trước khi lưu, chứ không để người dùng phát hiện sau khi đã lồng tiếng cả video.

CẢNH BÁO chứ không CHẶN: người dùng có thể cố tình dùng mẫu lạ (giọng thì thầm,
giọng trẻ con). Nhưng phải nói ra trước khi lưu.

Hàm THUẦN nhận số đo, không chạm file: nhờ vậy test không cần một file wav thật
— thứ mà CLAUDE.md cấm commit vào repo.
"""

from __future__ import annotations

from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.giong import (
    CAU_NGHE_THU,
    DOAN_MAU_TAM,
    CanhBao,
    DoAmThanh,
    kiem_chat_luong,
    tham_so_goi,
)


def _do(
    *,
    do_dai_giay: float = 10.0,
    rms: float = 0.12,
    dinh: float = 0.80,
    ti_le_im_lang: float = 0.15,
) -> DoAmThanh:
    """Số đo của một mẫu TỐT; mỗi test chỉ đổi đúng một chỉ số."""
    return DoAmThanh(do_dai_giay=do_dai_giay, rms=rms, dinh=dinh, ti_le_im_lang=ti_le_im_lang)


def _ma(canh_bao: list[CanhBao]) -> list[str]:
    return [c.ma for c in canh_bao]


class TestKiemChatLuong:
    def test_mau_tot_khong_canh_bao_gi(self) -> None:
        assert kiem_chat_luong(_do()) == []

    def test_ngan_qua(self) -> None:
        assert _ma(kiem_chat_luong(_do(do_dai_giay=6.9))) == ["qua_ngan"]

    def test_dai_qua(self) -> None:
        assert _ma(kiem_chat_luong(_do(do_dai_giay=15.1))) == ["qua_dai"]

    def test_dung_bien_7_va_15_giay_thi_khong_canh_bao(self) -> None:
        #: Ngưỡng là "< 7" và "> 15", đúng biên KHÔNG cảnh báo — nếu không thì
        #: mẫu 15,0 giây do chính ta cắt ra lại bị chính ta chê.
        assert kiem_chat_luong(_do(do_dai_giay=7.0)) == []
        assert kiem_chat_luong(_do(do_dai_giay=15.0)) == []

    def test_dinh_bang_0_99_la_vo_tieng(self) -> None:
        #: Ngưỡng "≥ 0,99" — đúng 0,99 đã là cắt đỉnh.
        assert _ma(kiem_chat_luong(_do(dinh=0.99))) == ["vo_tieng"]
        assert kiem_chat_luong(_do(dinh=0.98)) == []

    def test_rms_qua_nho(self) -> None:
        assert _ma(kiem_chat_luong(_do(rms=0.019))) == ["qua_nho"]
        assert kiem_chat_luong(_do(rms=0.02)) == []

    def test_im_lang_qua_nhieu(self) -> None:
        assert _ma(kiem_chat_luong(_do(ti_le_im_lang=0.41))) == ["nhieu_im_lang"]
        assert kiem_chat_luong(_do(ti_le_im_lang=0.40)) == []

    def test_mau_te_toan_tap_bao_DU_moi_loi(self) -> None:
        #: Báo một lỗi rồi dừng thì người dùng sửa xong lại ăn cảnh báo tiếp —
        #: ba vòng thu lại mới xong. Phải liệt kê hết trong một lần.
        ra = kiem_chat_luong(
            DoAmThanh(do_dai_giay=3.0, rms=0.005, dinh=1.0, ti_le_im_lang=0.8)
        )
        assert _ma(ra) == ["qua_ngan", "vo_tieng", "qua_nho", "nhieu_im_lang"]

    def test_moi_canh_bao_deu_noi_CACH_SUA(self) -> None:
        #: "Mẫu không đạt" là câu vô dụng. Người dùng phải biết làm gì tiếp.
        ra = kiem_chat_luong(DoAmThanh(do_dai_giay=3.0, rms=0.005, dinh=1.0, ti_le_im_lang=0.8))
        for c in ra:
            assert len(c.thong_diep) >= 20

    def test_mau_rong_hoan_toan(self) -> None:
        #: File 0 byte đo ra toàn số 0. Không được ném lỗi, chỉ cảnh báo.
        ra = kiem_chat_luong(DoAmThanh(do_dai_giay=0.0, rms=0.0, dinh=0.0, ti_le_im_lang=1.0))
        assert "qua_ngan" in _ma(ra) and "qua_nho" in _ma(ra)


class TestCauNgheThu:
    def test_la_MOT_cau_co_dinh_du_dai(self) -> None:
        #: Mọi giọng đọc CÙNG một câu thì bấm lần lượt mới so được. Câu phải đủ
        #: dài để nghe ra ngữ điệu, và không xuống dòng (một số nhà cung cấp
        #: đọc dấu xuống dòng thành khoảng lặng dài).
        assert len(CAU_NGHE_THU) >= 40
        assert "\n" not in CAU_NGHE_THU

    def test_doan_mau_tam_dai_hon_cau_nghe_thu(self) -> None:
        #: `tam_tu_may` dùng đoạn này làm MẪU, mà mẫu dưới 7 giây thì ăn cảnh
        #: báo "ngắn quá" ngay khi vừa tạo.
        assert len(DOAN_MAU_TAM) > len(CAU_NGHE_THU)


class TestThamSoGoi:
    """Một dòng `giong_doc` -> đúng tham số gọi của nhà cung cấp tương ứng."""

    def test_edge_khong_co_model(self) -> None:
        ra = tham_so_goi(
            nha_cung_cap="edge", ma_giong="vi-VN-HoaiMyNeural", model="", giong_id="g1"
        )
        assert ra == {
            "tts_provider": "edge",
            "giong_doc": "vi-VN-HoaiMyNeural",
            "giong_doc_id": "g1",
        }

    def test_gemini_co_model(self) -> None:
        ra = tham_so_goi(
            nha_cung_cap="gemini",
            ma_giong="Kore",
            model="gemini-2.5-flash-preview-tts",
            giong_id="g2",
        )
        assert ra["tts_provider"] == "gemini"
        assert ra["giong_doc"] == "Kore"
        assert ra["tts_model"] == "gemini-2.5-flash-preview-tts"

    def test_openrouter_co_model(self) -> None:
        ra = tham_so_goi(
            nha_cung_cap="openrouter",
            ma_giong="nova",
            model="openai/gpt-audio-mini",
            giong_id="g3",
        )
        assert ra["tts_provider"] == "openrouter"
        assert ra["tts_model"] == "openai/gpt-audio-mini"

    def test_fish_mlx_khong_co_ma_giong_va_khong_co_model(self) -> None:
        #: Fish KHÔNG có trường `voice` (spec B3) — giọng đến từ đoạn mẫu, tra
        #: theo `giong_doc_id`. Để lọt `tts_model` vào đây là gửi tên model của
        #: bên khác sang subprocess MLX.
        ra = tham_so_goi(nha_cung_cap="fish_mlx", ma_giong="", model="", giong_id="g4")
        assert ra == {"tts_provider": "fish_mlx", "giong_doc": "", "giong_doc_id": "g4"}
        assert "tts_model" not in ra


class TestEnum:
    def test_du_bon_nguon_nguoi_dung_da_chot(self) -> None:
        assert {n.value for n in NguonGiong} == {
            "dung_san",
            "tu_thu",
            "cat_tu_file",
            "thue_doc",
            "tam_tu_may",
        }

    def test_ba_trang_thai(self) -> None:
        assert {t.value for t in TrangThaiGiong} == {"dang_xu_ly", "san_sang", "hong"}
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/worker && pytest tests/test_cong_chat_luong_giong.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reup_core.giong'`

- [ ] **Step 3: Thêm hai enum**

Thêm vào CUỐI `packages/reup_core/src/reup_core/enums.py`:

```python
class NguonGiong(StrEnum):
    """Đoạn mẫu của một giọng lấy từ đâu.

    Bốn nguồn người dùng chốt đều đổ về CÙNG một luồng xử lý — chỉ khác chỗ
    lấy file vào (spec C3). Ghi lại nguồn để giao diện nói rõ đây là giọng
    thật hay giọng máy: ``tam_tu_may`` là giọng máy chép lại giọng máy, chất
    lượng không thể bằng người thu thật, và người dùng phải biết điều đó.
    """

    DUNG_SAN = "dung_san"  # giọng dựng sẵn của nhà cung cấp, seed từ migration
    TU_THU = "tu_thu"  # người dùng tự thu bằng điện thoại/micro
    CAT_TU_FILE = "cat_tu_file"  # cắt một đoạn từ audio/video có sẵn
    THUE_DOC = "thue_doc"  # file do người đọc thuê gửi về
    TAM_TU_MAY = "tam_tu_may"  # dựng tạm bằng Edge ngay tại chỗ


class TrangThaiGiong(StrEnum):
    """Trạng thái xử lý của một dòng ``giong_doc``.

    Cần trạng thái riêng chứ không suy ra từ ``co_ma_hoa``: giọng dựng sẵn
    (Edge/Gemini) KHÔNG BAO GIỜ mã hoá mẫu nhưng vẫn dùng được ngay, còn giọng
    clone thì có quãng vài chục giây đang chuẩn hoá và gõ chữ — quãng đó giao
    diện phải hiện "đang xử lý…" chứ không hiện giọng như đã sẵn sàng.
    """

    DANG_XU_LY = "dang_xu_ly"
    SAN_SANG = "san_sang"
    HONG = "hong"
```

- [ ] **Step 4: Viết `reup_core/giong.py`**

Tạo `packages/reup_core/src/reup_core/giong.py`:

```python
"""Thư viện giọng — hằng số và luật dùng chung cho API lẫn worker.

Nằm ở ``reup_core`` chứ không ở ``apps/worker``: API cần cổng chất lượng để
trả cảnh báo ra giao diện, mà API KHÔNG được import code worker (xem docstring
``api/src/services/task_bridge.py`` — worker mang theo whisper, torch và những
thứ nặng API không cài).

Mọi hàm ở đây THUẦN: không chạm file, không chạm DB, không import celery.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Câu đọc thử CỐ ĐỊNH cho mọi giọng. Có thế mới so được các giọng với nhau
#: sòng phẳng — mỗi giọng một câu khác nhau thì cái nghe hay hơn có thể chỉ vì
#: câu của nó dễ đọc hơn. Đặt MỘT chỗ, không rải rác (spec C3).
CAU_NGHE_THU = (
    "Xin chào, đây là giọng đọc thử của ReupStudio. "
    "Mọi giọng trong thư viện đều đọc đúng câu này, để bạn nghe lần lượt và so cho công bằng."
)

#: Đoạn dựng mẫu cho nguồn ``tam_tu_may``. Dài hơn ``CAU_NGHE_THU`` vì nó là
#: ĐOẠN MẪU chứ không phải câu nghe thử: mẫu dưới 7 giây sẽ ăn cảnh báo
#: "ngắn quá không đủ đặc trưng" ngay lúc vừa tạo.
DOAN_MAU_TAM = (
    "Xin chào, đây là đoạn giọng mẫu tạm do máy dựng. "
    "Bạn có thể dùng tạm để chạy thử, nhưng nên thay bằng một đoạn thu thật khi có điều kiện, "
    "vì chất lượng bản lồng tiếng không bao giờ vượt được chất lượng đoạn mẫu."
)

#: Tần số lấy mẫu của đoạn mẫu sau khi chuẩn hoá. 44,1 kHz theo spec C3.
TAN_SO_MAU = 44100

#: Ngưỡng cổng chất lượng (spec C4). Đặt tên chứ không rải số trong code.
DO_DAI_TOI_THIEU_GIAY = 7.0
DO_DAI_TOI_DA_GIAY = 15.0
DINH_VO_TIENG = 0.99
RMS_TOI_THIEU = 0.02
TI_LE_IM_LANG_TOI_DA = 0.40

#: Biên độ RMS của một khung 20ms dưới mức này thì coi khung đó là im lặng.
NGUONG_IM_LANG = 0.01

#: Độ dài một khung khi tính tỉ lệ im lặng.
KHUNG_IM_LANG_GIAY = 0.02


@dataclass(frozen=True)
class DoAmThanh:
    """Số đo của một đoạn mẫu. Đo ở worker, chấm điểm ở đây."""

    do_dai_giay: float
    #: Căn bậc hai trung bình bình phương biên độ — độ to trung bình.
    rms: float
    #: Biên độ lớn nhất, 1,0 là chạm trần và đã méo.
    dinh: float
    #: Tỉ lệ khung im lặng trên tổng số khung, 0,0–1,0.
    ti_le_im_lang: float


@dataclass(frozen=True)
class CanhBao:
    """Một điều cần nói với người dùng trước khi họ lưu giọng.

    ``ma`` để giao diện chọn màu và test khớp chính xác; ``thong_diep`` là câu
    tiếng Việt nói rõ CÁCH SỬA — "mẫu không đạt" là câu vô dụng.
    """

    ma: str
    thong_diep: str


def kiem_chat_luong(do: DoAmThanh) -> list[CanhBao]:
    """Chấm đoạn mẫu theo bốn ngưỡng đo được. CẢNH BÁO, KHÔNG CHẶN.

    Vì sao không chặn: người dùng có thể cố tình dùng mẫu lạ — giọng thì thầm
    RMS thấp, đoạn ngắn của một câu đặc biệt. Chặn là bắt họ đi đường vòng.
    Nhưng im lặng cho qua còn tệ hơn: mẫu tồi làm hỏng MỌI video về sau, và
    người dùng chỉ phát hiện sau khi đã lồng tiếng xong cả video.

    Trả về ĐỦ mọi lỗi trong một lần, không dừng ở lỗi đầu — báo lắt nhắt thì
    người dùng phải thu lại ba vòng mới xong.
    """
    ra: list[CanhBao] = []

    if do.do_dai_giay < DO_DAI_TOI_THIEU_GIAY:
        ra.append(
            CanhBao(
                "qua_ngan",
                f"Đoạn mẫu chỉ {do.do_dai_giay:.1f} giây — ngắn quá, không đủ đặc trưng giọng. "
                f"Thu lại ít nhất {DO_DAI_TOI_THIEU_GIAY:.0f} giây.",
            )
        )
    elif do.do_dai_giay > DO_DAI_TOI_DA_GIAY:
        ra.append(
            CanhBao(
                "qua_dai",
                f"Đoạn mẫu dài {do.do_dai_giay:.1f} giây — dài hơn "
                f"{DO_DAI_TOI_DA_GIAY:.0f} giây là phí, cắt bớt cho gọn.",
            )
        )

    if do.dinh >= DINH_VO_TIENG:
        ra.append(
            CanhBao(
                "vo_tieng",
                "Tiếng chạm trần biên độ nên bị vỡ — thu lại nhỏ hơn, "
                "hoặc để micro xa miệng thêm một gang tay.",
            )
        )

    if do.rms < RMS_TOI_THIEU:
        ra.append(
            CanhBao(
                "qua_nho",
                "Tiếng quá nhỏ, gần như im lặng — thu lại to hơn, "
                "hoặc kiểm tra xem micro có đúng thiết bị đang dùng không.",
            )
        )

    if do.ti_le_im_lang > TI_LE_IM_LANG_TOI_DA:
        ra.append(
            CanhBao(
                "nhieu_im_lang",
                f"{do.ti_le_im_lang * 100:.0f}% đoạn mẫu là im lặng — cắt lại phần có tiếng nói, "
                "hoặc đọc liền mạch hơn.",
            )
        )

    return ra


def tham_so_goi(*, nha_cung_cap: str, ma_giong: str, model: str, giong_id: str) -> dict[str, str]:
    """Một dòng ``giong_doc`` -> tham số ghi vào ``video.process_config``.

    Bốn nhà cung cấp, bốn dạng khác nhau:

    - ``edge``: chỉ cần mã giọng, không có model;
    - ``gemini`` / ``openrouter``: mã giọng + model;
    - ``fish_mlx``: KHÔNG có mã giọng và KHÔNG có model — giọng đến từ đoạn mẫu
      (spec B3: Fish S2-Pro không có trường ``voice``), worker tra đoạn mẫu
      theo ``giong_doc_id``.

    Luôn ghi ``giong_doc_id``: đó là thứ duy nhất trỏ ngược về dòng bảng, nhờ
    nó mà đổi tên giọng hay sửa đoạn mẫu không làm hỏng video đã xếp hàng.

    ``tts_model`` chỉ có mặt khi thật sự có model — để lọt khoá rỗng vào
    ``process_config`` là worker đọc ra chuỗi rỗng rồi gửi nó đi làm tên model.
    """
    ra = {
        "tts_provider": nha_cung_cap,
        "giong_doc": ma_giong or "",
        "giong_doc_id": giong_id,
    }
    if model:
        ra["tts_model"] = model
    return ra
```

- [ ] **Step 5: Chạy test cho chắc là qua**

Run: `cd apps/worker && pytest tests/test_cong_chat_luong_giong.py -v`
Expected: PASS, 19 passed

- [ ] **Step 6: Commit**

```bash
cd apps/worker && ruff format . && ruff check --fix .
git add packages/reup_core/src/reup_core/giong.py packages/reup_core/src/reup_core/enums.py apps/worker/tests/test_cong_chat_luong_giong.py
git commit -m "feat(giong): cổng chất lượng đoạn mẫu và hằng số dùng chung cho thư viện giọng"
```

---

### Task 2: Đường dẫn `media/giong/<id>/`

**Files:**
- Modify: `packages/reup_core/src/reup_core/paths.py`
- Test: `apps/worker/tests/test_paths_giong.py`

**Interfaces:**
- Produces:
  - `giong_dir(giong_id: str) -> Path`
  - `giong_mau_wav(giong_id: str) -> Path`
  - `giong_mau_txt(giong_id: str) -> Path`
  - `giong_codes(giong_id: str) -> Path`
  - `giong_nghe_thu(giong_id: str) -> Path`
  - `giong_tai_len(giong_id: str, duoi: str) -> Path`

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/worker/tests/test_paths_giong.py`:

```python
"""Đường dẫn file của thư viện giọng.

``paths.py`` là nơi DUY NHẤT được ghép đường dẫn (luật số 3 CLAUDE.md). Test
này khoá bốn tên file spec C2 đã chốt, và khoá một cái bẫy có thật: đã có sẵn
``voice_parts_dir(video_id)`` trả về ``media/work/<video_id>/giong`` — thư mục
chứa từng MẨU giọng của một video. Hai thứ khác hẳn nhau mà tên gần giống, lẫn
là xoá nhầm cả bộ mẫu giọng khi dọn thư mục work.
"""

from __future__ import annotations

from pathlib import Path

from reup_core import paths

GIONG_ID = "8c1f7b6e-0000-4000-8000-000000000001"


def test_moi_file_nam_trong_thu_muc_cua_dung_giong_do(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    thu_muc = paths.giong_dir(GIONG_ID)

    assert thu_muc == tmp_path.resolve() / "giong" / GIONG_ID
    for f in (
        paths.giong_mau_wav(GIONG_ID),
        paths.giong_mau_txt(GIONG_ID),
        paths.giong_codes(GIONG_ID),
        paths.giong_nghe_thu(GIONG_ID),
    ):
        assert f.parent == thu_muc


def test_dung_dung_bon_ten_file_spec_da_chot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    assert paths.giong_mau_wav(GIONG_ID).name == "mau.wav"
    assert paths.giong_mau_txt(GIONG_ID).name == "mau.txt"
    assert paths.giong_codes(GIONG_ID).name == "codes.npz"
    assert paths.giong_nghe_thu(GIONG_ID).name == "nghe-thu.wav"


def test_thu_muc_duoc_tao_tu_dong(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    d = paths.giong_dir(GIONG_ID)
    assert d.exists() and d.is_dir()


def test_file_tai_len_giu_nguyen_duoi(tmp_path: Path, monkeypatch) -> None:
    #: ffmpeg đoán định dạng đầu vào theo nội dung, nhưng giữ đuôi giúp người
    #: soi thư mục biết ngay file gốc là gì khi đi tìm nguyên nhân.
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    assert paths.giong_tai_len(GIONG_ID, ".m4a").name == "goc.m4a"
    assert paths.giong_tai_len(GIONG_ID, "mp3").name == "goc.mp3"
    assert paths.giong_tai_len(GIONG_ID, "").name == "goc"


def test_KHAC_han_thu_muc_mau_giong_cua_mot_video(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    assert paths.giong_dir(GIONG_ID) != paths.voice_parts_dir(GIONG_ID)
    assert not paths.giong_dir(GIONG_ID).is_relative_to(paths.work_dir(GIONG_ID))
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/worker && pytest tests/test_paths_giong.py -v`
Expected: FAIL — `AttributeError: module 'reup_core.paths' has no attribute 'giong_dir'`

- [ ] **Step 3: Thêm hàm vào `paths.py`**

Thêm vào CUỐI `packages/reup_core/src/reup_core/paths.py`, TRƯỚC `tmp_sibling`:

```python
def giong_dir(giong_id: str) -> Path:
    """Thư mục của MỘT giọng trong thư viện giọng (spec C2).

    KHÁC ``voice_parts_dir(video_id)`` — cái đó là ``media/work/<video_id>/giong``,
    chứa từng mẩu giọng đã đọc của một video và bị xoá cùng thư mục work. Thư
    mục này sống lâu dài theo giọng, không theo video.
    """
    return _ensure(media_root() / "giong" / str(giong_id))


def giong_mau_wav(giong_id: str) -> Path:
    """Đoạn mẫu đã chuẩn hoá: mono, 44,1 kHz, đã cắt im lặng, ≤ 15 giây."""
    return giong_dir(giong_id) / "mau.wav"


def giong_mau_txt(giong_id: str) -> Path:
    """Phần chữ của đoạn mẫu — Whisper gõ ra, người dùng sửa lại cho khớp."""
    return giong_dir(giong_id) / "mau.txt"


def giong_codes(giong_id: str) -> Path:
    """``reference_codes`` đã mã hoá một lần, để lồng tiếng cả video không phải
    mã hoá lại đoạn mẫu ở từng câu (spec C3). Chỉ giọng ``fish_mlx`` mới có.
    """
    return giong_dir(giong_id) / "codes.npz"


def giong_nghe_thu(giong_id: str) -> Path:
    """Câu đọc thử — mọi giọng đọc CÙNG một câu nên nghe lần lượt là so được."""
    return giong_dir(giong_id) / "nghe-thu.wav"


def giong_tai_len(giong_id: str, duoi: str) -> Path:
    """File người dùng vừa tải lên, giữ nguyên phần mở rộng.

    Giữ lại file gốc chứ không xoá sau khi chuẩn hoá: cắt lại đoạn khác từ
    cùng file là việc thường xuyên, và bắt người dùng tải lên lần nữa chỉ vì
    ta đã vứt file đi là kiểu bất tiện không cần thiết.
    """
    duoi = duoi if duoi.startswith(".") or not duoi else f".{duoi}"
    return giong_dir(giong_id) / f"goc{duoi}"
```

- [ ] **Step 4: Chạy test cho chắc là qua**

Run: `cd apps/worker && pytest tests/test_paths_giong.py tests/test_paths.py -v`
Expected: PASS, tất cả xanh (5 test mới + các test cũ của `test_paths.py`)

- [ ] **Step 5: Commit**

```bash
cd apps/worker && ruff format . && ruff check --fix .
git add packages/reup_core/src/reup_core/paths.py apps/worker/tests/test_paths_giong.py
git commit -m "feat(giong): đường dẫn media/giong/<id>/ cho thư viện giọng"
```

---

### Task 3: Bảng `giong_doc` + migration + seed giọng dựng sẵn

Bảng là nguồn sự thật DUY NHẤT (spec C1): hiện `video_service.cac_giong_doc` trả ba nhóm cứng, thêm giọng clone vào khuôn đó là thêm tầng thứ tư. Gộp lại thì thêm giọng chỉ là thêm một dòng trong bảng.

**Files:**
- Create: `packages/reup_core/src/reup_core/models/giong_doc.py`
- Modify: `packages/reup_core/src/reup_core/models/__init__.py`
- Create: `apps/api/alembic/versions/0012_giong_doc.py`
- Test: `apps/worker/tests/test_model_giong_doc.py`

Tên bảng giữ nguyên `giong_doc` như spec C2 chốt (tiếng Việt không có dạng số nhiều để thêm).

**Interfaces:**
- Consumes: `reup_core.enums.NguonGiong`, `reup_core.enums.TrangThaiGiong` (Task 1)
- Produces: `reup_core.models.GiongDoc`

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/worker/tests/test_model_giong_doc.py`:

```python
"""Bảng ``giong_doc`` — một dòng một giọng, dựng sẵn lẫn clone.

Test này khoá hai thứ dễ hỏng âm thầm:

1. Chỉ số duy nhất trên ``mac_dinh`` phải là chỉ số MỘT PHẦN (chỉ ràng buộc
   những dòng ``mac_dinh = true``). Khai thiếu ``sqlite_where`` bên cạnh
   ``postgresql_where`` thì trên SQLite nó thành chỉ số duy nhất TOÀN PHẦN, và
   giọng thứ hai có ``mac_dinh = false`` sẽ bị từ chối — hỏng chỉ trong test,
   không hỏng khi chạy thật, tức loại hỏng khó tìm nhất.
2. Có đúng những cột spec C2 chốt, cộng năm cột trạng thái mà luồng chạy nền
   cần (``trang_thai``, ``loi``, ``canh_bao``, ``do_dai_giay``, ``nghe_thu_bang``).
"""

from __future__ import annotations

import pytest
from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.models import GiongDoc
from reup_core.models.base import Base
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _giong(**kw) -> GiongDoc:
    mac = {
        "ten": "Giọng thử",
        "nha_cung_cap": "edge",
        "ma_giong": "vi-VN-HoaiMyNeural",
        "ngon_ngu": "vi",
        "nguon": NguonGiong.DUNG_SAN.value,
        "trang_thai": TrangThaiGiong.SAN_SANG.value,
    }
    mac.update(kw)
    return GiongDoc(**mac)


def test_ten_bang_va_du_cot_spec_C2(db) -> None:
    cot = set(GiongDoc.__table__.columns.keys())
    assert GiongDoc.__tablename__ == "giong_doc"
    assert {
        "id",
        "ten",
        "nha_cung_cap",
        "ma_giong",
        "model",
        "ngon_ngu",
        "nguon",
        "mau_text",
        "co_ma_hoa",
        "mac_dinh",
        "ghi_chu",
        "created_at",
    } <= cot
    #: Năm cột cho luồng chạy nền — thiếu chúng thì giao diện không phân biệt
    #: được "đang xử lý" với "hỏng", và cảnh báo chất lượng không có chỗ nằm.
    assert {"trang_thai", "loi", "canh_bao", "do_dai_giay", "nghe_thu_bang"} <= cot


def test_nhieu_giong_KHONG_mac_dinh_cung_ton_tai_duoc(db) -> None:
    db.add_all([_giong(ten=f"Giọng {i}", mac_dinh=False) for i in range(3)])
    db.commit()
    assert len(db.scalars(select(GiongDoc)).all()) == 3


def test_chi_MOT_giong_duoc_lam_mac_dinh(db) -> None:
    db.add(_giong(ten="Một", mac_dinh=True))
    db.commit()
    db.add(_giong(ten="Hai", mac_dinh=True))
    with pytest.raises(IntegrityError):
        db.commit()


def test_mac_dinh_cua_cac_cot(db) -> None:
    db.add(_giong())
    db.commit()
    row = db.scalars(select(GiongDoc)).one()
    assert row.mac_dinh is False
    assert row.co_ma_hoa is False
    assert row.canh_bao == []
    assert row.trang_thai == TrangThaiGiong.SAN_SANG.value


def test_giong_clone_khong_can_ma_giong(db) -> None:
    #: Fish không có trường ``voice`` — giọng đến từ đoạn mẫu, nên ``ma_giong``
    #: PHẢI cho phép rỗng, nếu không mọi giọng clone đều không lưu được.
    db.add(
        _giong(
            ten="Giọng tôi",
            nha_cung_cap="fish_mlx",
            ma_giong=None,
            nguon=NguonGiong.TU_THU.value,
            mau_text="Xin chào, đây là giọng của tôi.",
        )
    )
    db.commit()
    assert db.scalars(select(GiongDoc)).one().ma_giong is None
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/worker && pytest tests/test_model_giong_doc.py -v`
Expected: FAIL — `ImportError: cannot import name 'GiongDoc' from 'reup_core.models'`

- [ ] **Step 3: Viết model**

Tạo `packages/reup_core/src/reup_core/models/giong_doc.py`:

```python
from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ..enums import TrangThaiGiong
from .base import Base, TimestampMixin, uuid_pk


class GiongDoc(Base, TimestampMixin):
    """Một giọng đọc trong thư viện — dựng sẵn của nhà cung cấp, hoặc clone.

    Vì sao GỘP hai loại vào một bảng (spec C1): giao diện cũ bắt chọn tuần tự
    ba ô (nhà cung cấp → model → giọng), thêm giọng clone vào khuôn đó là thêm
    tầng thứ tư. Gộp lại thì thêm giọng chỉ là thêm một dòng, và người dùng
    chọn MỘT lần — hệ thống tự biết gọi nhà cung cấp nào.

    Chỉ số duy nhất MỘT PHẦN trên ``mac_dinh`` chặn ở tầng DB việc có hai giọng
    mặc định. Ràng buộc ở tầng service thôi là không đủ: hai request đặt mặc
    định gần như cùng lúc sẽ cùng đọc thấy "chưa ai là mặc định".
    """

    __tablename__ = "giong_doc"
    __table_args__ = (
        sa.Index(
            "uq_giong_doc_mac_dinh",
            "mac_dinh",
            unique=True,
            #: Cả hai dialect đều phải khai: thiếu ``sqlite_where`` thì test
            #: chạy trên SQLite thấy chỉ số duy nhất TOÀN PHẦN và giọng thứ hai
            #: không mặc định cũng bị từ chối.
            postgresql_where=sa.text("mac_dinh"),
            sqlite_where=sa.text("mac_dinh"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()

    #: Tên người dùng đặt: "Giọng tôi", "Chị Lan thuê". Với giọng dựng sẵn thì
    #: là tên nhà cung cấp đặt ("Hoài My", "Kore — chắc chắn").
    ten: Mapped[str] = mapped_column(sa.String(120), nullable=False)

    #: edge · gemini · openrouter · fish_mlx
    nha_cung_cap: Mapped[str] = mapped_column(sa.String(32), nullable=False)

    #: Mã giọng dựng sẵn (``vi-VN-HoaiMyNeural``). NULL với giọng clone — Fish
    #: không có trường ``voice``, giọng đến từ đoạn mẫu.
    ma_giong: Mapped[str | None] = mapped_column(sa.String(64))

    #: Model TTS đi kèm, nếu nhà cung cấp cần (Gemini, OpenRouter).
    model: Mapped[str | None] = mapped_column(sa.String(64))

    ngon_ngu: Mapped[str] = mapped_column(sa.String(8), nullable=False, default="vi")

    #: nữ · nam · trung tính. Giữ lại vì ô chọn giọng hiện giới tính, và bỏ đi
    #: là ``GET /videos/tts-options`` mất một trường đang có.
    gioi_tinh: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="")

    #: ``NguonGiong`` — dung_san · tu_thu · cat_tu_file · thue_doc · tam_tu_may
    nguon: Mapped[str] = mapped_column(sa.String(16), nullable=False)

    #: Phần chữ của đoạn mẫu; chỉ giọng clone mới có. Whisper gõ ra, người dùng
    #: sửa lại cho khớp TỪNG CHỮ — sai một chữ là model clone học sai chữ đó.
    mau_text: Mapped[str | None] = mapped_column(sa.Text)

    #: Đã mã hoá xong ``reference_codes`` chưa. Giọng clone thêm trước khi có
    #: Kế hoạch B thì cờ này là ``false`` và vẫn dùng được (đọc bằng Edge).
    co_ma_hoa: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    #: Giọng dùng khi video không chọn riêng. Đúng MỘT dòng được bật.
    mac_dinh: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    ghi_chu: Mapped[str | None] = mapped_column(sa.Text)

    #: ``TrangThaiGiong``. Giọng dựng sẵn sinh ra đã ``san_sang``; giọng clone
    #: đi qua quãng ``dang_xu_ly`` vài chục giây (chuẩn hoá + gõ chữ + đọc thử).
    trang_thai: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default=TrangThaiGiong.SAN_SANG.value
    )

    #: Lý do hỏng, hiện thẳng trên thẻ giọng. Hỏng mà không nói lý do thì người
    #: dùng chỉ biết bấm Thêm lại và hỏng y hệt.
    loi: Mapped[str | None] = mapped_column(sa.Text)

    #: Cảnh báo cổng chất lượng: ``[{"ma": ..., "thong_diep": ...}]``. Lưu lại
    #: chứ không tính lại mỗi lần đọc — tính lại phải giải mã file wav.
    canh_bao: Mapped[list[dict[str, Any]]] = mapped_column(sa.JSON, nullable=False, default=list)

    #: Độ dài đoạn mẫu sau chuẩn hoá, hiện trên thẻ giọng ("12,4s").
    do_dai_giay: Mapped[float | None] = mapped_column(sa.Float)

    #: Nhà cung cấp THẬT SỰ đã dựng file nghe thử. Khác ``nha_cung_cap`` khi
    #: rơi về đường lui — âm thầm đổi giọng mà không nói là kiểu hỏng tệ nhất
    #: (spec B4): người dùng nghe giọng Edge và tưởng đó là giọng clone của mình.
    nghe_thu_bang: Mapped[str | None] = mapped_column(sa.String(32))

    #: Mốc cắt của nguồn ``cat_tu_file`` (giây). Lưu lại để cắt lại được mà
    #: không phải tải file lên lần nữa.
    cat_tu_giay: Mapped[float | None] = mapped_column(sa.Float)
    cat_den_giay: Mapped[float | None] = mapped_column(sa.Float)
```

Sửa `packages/reup_core/src/reup_core/models/__init__.py` — thêm import và tên vào `__all__`, giữ thứ tự bảng chữ cái:

```python
from .cost_log import CostLog
from .giong_doc import GiongDoc
from .job_run import JobRun
```

```python
    "CostLog",
    "GiongDoc",
    "JobRun",
```

- [ ] **Step 4: Chạy test cho chắc là qua**

Run: `cd apps/worker && pytest tests/test_model_giong_doc.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Viết migration + seed**

Tạo `apps/api/alembic/versions/0012_giong_doc.py`:

```python
"""feat(giong): bảng giong_doc — thư viện giọng gộp dựng sẵn và clone

Nguồn sự thật DUY NHẤT cho danh sách giọng. Trước bản này, danh sách nằm cứng
trong ``api/src/services/video_service.py`` (``_GIONG_EDGE``, ``_GIONG_GEMINI``,
``_GIONG_OPENROUTER``) nên thêm một giọng là phải sửa code và deploy lại.

38 dòng seed dưới đây CHÉP NGUYÊN từ ba hằng số đó — chép chứ không import:
migration phải cho ra cùng kết quả mãi mãi, mà hằng số trong code thì đổi theo
thời gian. Sau bản này ba hằng số kia bị xoá khỏi ``video_service``.

Chỉ số duy nhất MỘT PHẦN trên ``mac_dinh`` chặn ở tầng DB việc có hai giọng
mặc định — hai request đặt mặc định gần như cùng lúc đều đọc thấy "chưa ai là
mặc định" nếu chỉ chặn ở tầng service.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

#: Giọng mặc định lúc khởi đầu — edge-tts miễn phí và không tính lượt, nên
#: người mới dùng không đốt hạn mức nào trước khi kịp hiểu mình đang chọn gì.
MA_GIONG_MAC_DINH = "vi-VN-HoaiMyNeural"

#: (mã giọng, tên, giới tính)
_EDGE = [
    ("vi-VN-HoaiMyNeural", "Hoài My", "nữ"),
    ("vi-VN-NamMinhNeural", "Nam Minh", "nam"),
]

_GEMINI = [
    ("Kore", "Kore — chắc chắn", "nữ"),
    ("Aoede", "Aoede — nhẹ nhàng", "nữ"),
    ("Leda", "Leda — trẻ trung", "nữ"),
    ("Callirrhoe", "Callirrhoe — thong thả", "nữ"),
    ("Autonoe", "Autonoe — tươi sáng", "nữ"),
    ("Despina", "Despina — mượt", "nữ"),
    ("Erinome", "Erinome — rõ ràng", "nữ"),
    ("Laomedeia", "Laomedeia — sôi nổi", "nữ"),
    ("Achernar", "Achernar — êm", "nữ"),
    ("Gacrux", "Gacrux — chững chạc", "nữ"),
    ("Pulcherrima", "Pulcherrima — dẫn chuyện", "nữ"),
    ("Vindemiatrix", "Vindemiatrix — dịu", "nữ"),
    ("Sulafat", "Sulafat — ấm", "nữ"),
    ("Zephyr", "Zephyr — sáng", "nữ"),
    ("Puck", "Puck — hoạt bát", "nam"),
    ("Charon", "Charon — trầm, kể chuyện", "nam"),
    ("Fenrir", "Fenrir — mạnh", "nam"),
    ("Orus", "Orus — chắc", "nam"),
    ("Enceladus", "Enceladus — thì thầm", "nam"),
    ("Iapetus", "Iapetus — rõ", "nam"),
    ("Umbriel", "Umbriel — thư thái", "nam"),
    ("Algieba", "Algieba — mượt", "nam"),
    ("Algenib", "Algenib — khàn", "nam"),
    ("Rasalgethi", "Rasalgethi — giàu thông tin", "nam"),
    ("Alnilam", "Alnilam — dứt khoát", "nam"),
    ("Schedar", "Schedar — điềm đạm", "nam"),
    ("Achird", "Achird — thân thiện", "nam"),
    ("Zubenelgenubi", "Zubenelgenubi — đời thường", "nam"),
    ("Sadachbia", "Sadachbia — sống động", "nam"),
    ("Sadaltager", "Sadaltager — hiểu biết", "nam"),
]

_OPENROUTER = [
    ("nova", "Nova — sáng, nhanh", "nữ"),
    ("shimmer", "Shimmer — nhẹ, ấm", "nữ"),
    ("alloy", "Alloy — trung tính, đều", "trung tính"),
    ("fable", "Fable — kể chuyện", "trung tính"),
    ("echo", "Echo — trầm, chắc", "nam"),
    ("onyx", "Onyx — trầm, dày", "nam"),
]

#: Model seed cho từng bên: bản RẺ đứng trước. Token audio của
#: ``openai/gpt-audio`` là $32/1M so với $0,60/1M của bản mini — đắt gấp 53 lần.
_MODEL_MAC_DINH = {
    "gemini": "gemini-2.5-flash-preview-tts",
    "openrouter": "openai/gpt-audio-mini",
}

giong_doc_table = sa.table(
    "giong_doc",
    sa.column("id", sa.Uuid()),
    sa.column("ten", sa.String()),
    sa.column("nha_cung_cap", sa.String()),
    sa.column("ma_giong", sa.String()),
    sa.column("model", sa.String()),
    sa.column("ngon_ngu", sa.String()),
    sa.column("gioi_tinh", sa.String()),
    sa.column("nguon", sa.String()),
    sa.column("co_ma_hoa", sa.Boolean()),
    sa.column("mac_dinh", sa.Boolean()),
    sa.column("trang_thai", sa.String()),
    sa.column("canh_bao", sa.JSON()),
)


def _dong(nha: str, ma: str, ten: str, gioi_tinh: str) -> dict:
    return {
        "id": uuid.uuid4(),
        "ten": ten,
        "nha_cung_cap": nha,
        "ma_giong": ma,
        "model": _MODEL_MAC_DINH.get(nha),
        "ngon_ngu": "vi",
        "gioi_tinh": gioi_tinh,
        "nguon": "dung_san",
        "co_ma_hoa": False,
        "mac_dinh": nha == "edge" and ma == MA_GIONG_MAC_DINH,
        "trang_thai": "san_sang",
        "canh_bao": [],
    }


def upgrade() -> None:
    op.create_table(
        "giong_doc",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ten", sa.String(120), nullable=False),
        sa.Column("nha_cung_cap", sa.String(32), nullable=False),
        sa.Column("ma_giong", sa.String(64), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("ngon_ngu", sa.String(8), nullable=False, server_default="vi"),
        sa.Column("gioi_tinh", sa.String(16), nullable=False, server_default=""),
        sa.Column("nguon", sa.String(16), nullable=False),
        sa.Column("mau_text", sa.Text(), nullable=True),
        sa.Column("co_ma_hoa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mac_dinh", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("trang_thai", sa.String(16), nullable=False, server_default="san_sang"),
        sa.Column("loi", sa.Text(), nullable=True),
        sa.Column("canh_bao", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("do_dai_giay", sa.Float(), nullable=True),
        sa.Column("nghe_thu_bang", sa.String(32), nullable=True),
        sa.Column("cat_tu_giay", sa.Float(), nullable=True),
        sa.Column("cat_den_giay", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_index(
        "uq_giong_doc_mac_dinh",
        "giong_doc",
        ["mac_dinh"],
        unique=True,
        postgresql_where=sa.text("mac_dinh"),
    )

    op.bulk_insert(
        giong_doc_table,
        [
            *[_dong("edge", ma, ten, gt) for ma, ten, gt in _EDGE],
            *[_dong("gemini", ma, ten, gt) for ma, ten, gt in _GEMINI],
            *[_dong("openrouter", ma, ten, gt) for ma, ten, gt in _OPENROUTER],
        ],
    )


def downgrade() -> None:
    op.drop_index("uq_giong_doc_mac_dinh", table_name="giong_doc")
    op.drop_table("giong_doc")
```

- [ ] **Step 6: Chạy migration trên DB thật và ĐẾM**

```bash
cd apps/api && alembic upgrade head
docker exec reupstudio-postgres-1 psql -U reup -d reup -c \
  "SELECT nha_cung_cap, count(*) FROM giong_doc GROUP BY 1 ORDER BY 1;"
docker exec reupstudio-postgres-1 psql -U reup -d reup -c \
  "SELECT ten, ma_giong FROM giong_doc WHERE mac_dinh;"
```

Expected: `edge 2`, `gemini 30`, `openrouter 6` (tổng 38) và đúng MỘT dòng mặc định là `Hoài My | vi-VN-HoaiMyNeural`.

Kiểm chỉ số một phần thật sự là một phần (bảng có 37 dòng `mac_dinh = false` mà vẫn insert được — nếu chỉ số toàn phần thì bước seed ở trên đã nổ):

```bash
docker exec reupstudio-postgres-1 psql -U reup -d reup -c \
  "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_giong_doc_mac_dinh';"
```

Expected: dòng trả về có `WHERE (mac_dinh)`.

- [ ] **Step 7: Commit**

```bash
cd apps/api && ruff format . && ruff check --fix .
git add packages/reup_core/src/reup_core/models/giong_doc.py packages/reup_core/src/reup_core/models/__init__.py apps/api/alembic/versions/0012_giong_doc.py apps/worker/tests/test_model_giong_doc.py
git commit -m "feat(giong): bảng giong_doc + migration 0012 + seed 38 giọng dựng sẵn"
```

---

### Task 4: Service thư viện giọng — đọc, thêm, sửa, xoá, đặt mặc định

Toàn bộ luật nghiệp vụ nằm ở đây, router chỉ validate rồi gọi. Ba luật quan trọng nhất: không xoá được giọng dựng sẵn; xoá giọng đang mặc định thì phải chuyển mặc định đi chỗ khác chứ không để rỗng; đổi `mau_text` là làm `codes.npz` cũ vô nghĩa nên phải mã hoá lại.

**Files:**
- Create: `apps/api/src/services/giong_doc_service.py`
- Test: `apps/api/tests/test_giong_doc_service.py`

**Interfaces:**
- Consumes: `reup_core.models.GiongDoc`, `reup_core.enums.NguonGiong`, `reup_core.enums.TrangThaiGiong`, `reup_core.paths.giong_tai_len`
- Produces:
  - `danh_sach(db: Session) -> list[GiongDoc]`
  - `lay(db: Session, giong_id: uuid.UUID) -> GiongDoc`
  - `giong_mac_dinh(db: Session) -> GiongDoc | None`
  - `tao(db: Session, *, ten: str, nguon: str, nha_cung_cap: str, ghi_chu: str = "", cat_tu_giay: float | None = None, cat_den_giay: float | None = None, co_file: bool = False) -> GiongDoc`
  - `luu_file_tai_len(giong_id: uuid.UUID, ten_file: str, noi_dung: bytes) -> Path`
  - `sua(db: Session, giong_id: uuid.UUID, *, ten: str | None = None, ghi_chu: str | None = None, mac_dinh: bool | None = None, mau_text: str | None = None) -> tuple[GiongDoc, bool]`
  - `dat_mac_dinh(db: Session, giong_id: uuid.UUID) -> GiongDoc`
  - `xoa(db: Session, giong_id: uuid.UUID) -> None`

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/api/tests/test_giong_doc_service.py`:

```python
"""Luật nghiệp vụ của thư viện giọng.

Ba thứ hỏng âm thầm nếu không khoá lại:

- Xoá giọng đang là mặc định mà không chuyển mặc định đi đâu -> mọi video sau
  đó không biết đọc bằng gì, và lỗi chỉ nổ ra ở worker giữa chừng pipeline.
- Xoá được giọng dựng sẵn -> mất luôn danh sách seed, muốn lấy lại phải chạy
  lại migration.
- Sửa chữ của đoạn mẫu mà giữ nguyên ``codes.npz`` -> model clone đọc theo bản
  mã hoá CŨ, tức theo chữ sai mà người dùng vừa sửa xong.

Dùng SQLite trong RAM chứ không đối tượng giả: chỉ số duy nhất một phần trên
``mac_dinh`` là một phần của luật, mà đối tượng giả không kiểm được nó.
"""

from __future__ import annotations

import uuid

import pytest
from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.models import GiongDoc
from reup_core.models.base import Base
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.errors import ApiError, NotFound
from src.services import giong_doc_service as sv


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _dung_san(db, ten: str, ma: str, *, mac_dinh: bool = False) -> GiongDoc:
    row = GiongDoc(
        ten=ten,
        nha_cung_cap="edge",
        ma_giong=ma,
        ngon_ngu="vi",
        gioi_tinh="nữ",
        nguon=NguonGiong.DUNG_SAN.value,
        mac_dinh=mac_dinh,
        trang_thai=TrangThaiGiong.SAN_SANG.value,
    )
    db.add(row)
    db.commit()
    return row


class TestTao:
    def test_giong_moi_bat_dau_o_trang_thai_dang_xu_ly(self, db) -> None:
        #: Chưa chuẩn hoá, chưa gõ chữ, chưa có file nghe thử — hiện nó như
        #: sẵn sàng là mời người dùng chọn một giọng chưa dùng được.
        row = sv.tao(
            db,
            ten="Giọng tôi",
            nguon=NguonGiong.TU_THU.value,
            nha_cung_cap="fish_mlx",
            co_file=True,
        )
        db.commit()
        assert row.trang_thai == TrangThaiGiong.DANG_XU_LY.value
        assert row.co_ma_hoa is False
        assert row.mac_dinh is False

    def test_nguon_la_thi_bao_ro(self, db) -> None:
        with pytest.raises(ApiError, match="Nguồn giọng"):
            sv.tao(db, ten="X", nguon="tu_dau_ra", nha_cung_cap="fish_mlx", co_file=True)

    def test_khong_tu_tao_giong_DUNG_SAN(self, db) -> None:
        #: Giọng dựng sẵn chỉ đến từ seed. Cho tạo tay là mở đường cho một danh
        #: sách giọng dựng sẵn không khớp với thứ nhà cung cấp thật sự có.
        with pytest.raises(ApiError, match="dựng sẵn"):
            sv.tao(db, ten="X", nguon=NguonGiong.DUNG_SAN.value, nha_cung_cap="edge")

    def test_ba_nguon_tu_file_deu_BAT_BUOC_co_file(self, db) -> None:
        for nguon in (
            NguonGiong.TU_THU.value,
            NguonGiong.CAT_TU_FILE.value,
            NguonGiong.THUE_DOC.value,
        ):
            with pytest.raises(ApiError, match="chưa chọn file"):
                sv.tao(db, ten="X", nguon=nguon, nha_cung_cap="fish_mlx", co_file=False)

    def test_tam_tu_may_KHONG_can_file(self, db) -> None:
        row = sv.tao(
            db,
            ten="Giọng tạm",
            nguon=NguonGiong.TAM_TU_MAY.value,
            nha_cung_cap="fish_mlx",
            co_file=False,
        )
        db.commit()
        assert row.nguon == NguonGiong.TAM_TU_MAY.value

    def test_cat_tu_file_phai_co_moc_hop_le(self, db) -> None:
        with pytest.raises(ApiError, match="Mốc cắt"):
            sv.tao(
                db,
                ten="X",
                nguon=NguonGiong.CAT_TU_FILE.value,
                nha_cung_cap="fish_mlx",
                co_file=True,
                cat_tu_giay=12.0,
                cat_den_giay=8.0,
            )


class TestDatMacDinh:
    def test_giong_cu_bi_TAT_truoc_khi_bat_giong_moi(self, db) -> None:
        cu = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural", mac_dinh=True)
        moi = _dung_san(db, "Nam Minh", "vi-VN-NamMinhNeural")

        sv.dat_mac_dinh(db, moi.id)
        db.commit()

        assert [g.mac_dinh for g in (db.get(GiongDoc, cu.id), db.get(GiongDoc, moi.id))] == [
            False,
            True,
        ]

    def test_dat_lai_chinh_no_khong_lam_sao(self, db) -> None:
        g = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural", mac_dinh=True)
        sv.dat_mac_dinh(db, g.id)
        db.commit()
        assert db.get(GiongDoc, g.id).mac_dinh is True

    def test_khong_dat_mac_dinh_giong_dang_xu_ly(self, db) -> None:
        #: Đặt mặc định một giọng chưa dựng xong là hẹn giờ cho lỗi: video kế
        #: tiếp sẽ đòi một đoạn mẫu chưa tồn tại.
        moi = sv.tao(
            db, ten="Giọng tôi", nguon=NguonGiong.TU_THU.value, nha_cung_cap="fish_mlx", co_file=True
        )
        db.commit()
        with pytest.raises(ApiError, match="chưa xong"):
            sv.dat_mac_dinh(db, moi.id)


class TestXoa:
    def test_KHONG_xoa_duoc_giong_dung_san(self, db) -> None:
        g = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        with pytest.raises(ApiError, match="dựng sẵn"):
            sv.xoa(db, g.id)

    def test_xoa_giong_dang_mac_dinh_thi_CHUYEN_mac_dinh_sang_giong_khac(self, db) -> None:
        con_lai = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        cua_toi = sv.tao(
            db, ten="Giọng tôi", nguon=NguonGiong.TU_THU.value, nha_cung_cap="fish_mlx", co_file=True
        )
        cua_toi.trang_thai = TrangThaiGiong.SAN_SANG.value
        db.commit()
        sv.dat_mac_dinh(db, cua_toi.id)
        db.commit()

        sv.xoa(db, cua_toi.id)
        db.commit()

        assert db.get(GiongDoc, cua_toi.id) is None
        assert db.get(GiongDoc, con_lai.id).mac_dinh is True

    def test_mac_dinh_chuyen_sang_giong_SAN_SANG_cu_nhat(self, db) -> None:
        #: Chuyển sang một giọng đang xử lý là chuyển sang thứ chưa dùng được.
        dau_tien = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        _dung_san(db, "Nam Minh", "vi-VN-NamMinhNeural")
        cua_toi = sv.tao(
            db, ten="Giọng tôi", nguon=NguonGiong.TU_THU.value, nha_cung_cap="fish_mlx", co_file=True
        )
        cua_toi.trang_thai = TrangThaiGiong.SAN_SANG.value
        db.commit()
        sv.dat_mac_dinh(db, cua_toi.id)
        db.commit()

        sv.xoa(db, cua_toi.id)
        db.commit()

        assert db.get(GiongDoc, dau_tien.id).mac_dinh is True

    def test_id_khong_co_that(self, db) -> None:
        with pytest.raises(NotFound):
            sv.xoa(db, uuid.uuid4())


class TestSua:
    def test_doi_ten_khong_dung_lai_gi_ca(self, db) -> None:
        g = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        row, can_dung_lai = sv.sua(db, g.id, ten="Chị Mai")
        db.commit()
        assert row.ten == "Chị Mai"
        assert can_dung_lai is False

    def test_doi_mau_text_lam_ban_MA_HOA_cu_vo_nghia(self, db) -> None:
        g = sv.tao(
            db, ten="Giọng tôi", nguon=NguonGiong.TU_THU.value, nha_cung_cap="fish_mlx", co_file=True
        )
        g.trang_thai = TrangThaiGiong.SAN_SANG.value
        g.co_ma_hoa = True
        g.mau_text = "Chữ Whisper gõ sai"
        db.commit()

        row, can_dung_lai = sv.sua(db, g.id, mau_text="Chữ người dùng sửa lại cho đúng")
        db.commit()

        assert can_dung_lai is True
        assert row.co_ma_hoa is False
        assert row.trang_thai == TrangThaiGiong.DANG_XU_LY.value

    def test_mau_text_KHONG_doi_thi_khong_dung_lai(self, db) -> None:
        #: Giao diện gửi cả form mỗi lần Lưu. Coi "gửi lên" là "đã đổi" thì mỗi
        #: lần sửa ghi chú lại chạy lại cả Whisper lẫn mã hoá.
        g = sv.tao(
            db, ten="Giọng tôi", nguon=NguonGiong.TU_THU.value, nha_cung_cap="fish_mlx", co_file=True
        )
        g.mau_text = "Y hệt"
        g.trang_thai = TrangThaiGiong.SAN_SANG.value
        db.commit()

        _, can_dung_lai = sv.sua(db, g.id, mau_text="Y hệt", ghi_chu="thêm ghi chú")
        assert can_dung_lai is False

    def test_dat_mac_dinh_qua_sua(self, db) -> None:
        cu = _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural", mac_dinh=True)
        moi = _dung_san(db, "Nam Minh", "vi-VN-NamMinhNeural")
        sv.sua(db, moi.id, mac_dinh=True)
        db.commit()
        assert db.get(GiongDoc, cu.id).mac_dinh is False
        assert db.get(GiongDoc, moi.id).mac_dinh is True


class TestDanhSach:
    def test_giong_mac_dinh_dung_dau(self, db) -> None:
        #: Giọng mặc định là thứ người dùng cần thấy trước nhất — nó là giọng
        #: mọi video sẽ dùng nếu không ai chọn gì.
        _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        moi = _dung_san(db, "Nam Minh", "vi-VN-NamMinhNeural", mac_dinh=True)
        assert sv.danh_sach(db)[0].id == moi.id

    def test_giong_mac_dinh_tra_dung_dong(self, db) -> None:
        _dung_san(db, "Hoài My", "vi-VN-HoaiMyNeural")
        moi = _dung_san(db, "Nam Minh", "vi-VN-NamMinhNeural", mac_dinh=True)
        assert sv.giong_mac_dinh(db).id == moi.id

    def test_khong_co_giong_nao_thi_tra_None(self, db) -> None:
        assert sv.giong_mac_dinh(db) is None
        assert db.scalars(select(GiongDoc)).all() == []
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/api && pytest tests/test_giong_doc_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'giong_doc_service' from 'src.services'`

- [ ] **Step 3: Viết service**

Tạo `apps/api/src/services/giong_doc_service.py`:

```python
"""Logic nghiệp vụ của thư viện giọng. KHÔNG biết gì về HTTP/FastAPI."""

from __future__ import annotations

import uuid
from pathlib import Path

import sqlalchemy as sa
from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.logging import get_logger
from reup_core.models import GiongDoc
from reup_core.paths import giong_tai_len
from sqlalchemy.orm import Session

from ..errors import ApiError, NotFound

log = get_logger(__name__)

#: Nguồn nào BẮT BUỘC phải có file tải lên. ``tam_tu_may`` tự dựng nên không cần.
NGUON_CAN_FILE = frozenset(
    {NguonGiong.TU_THU.value, NguonGiong.CAT_TU_FILE.value, NguonGiong.THUE_DOC.value}
)


def danh_sach(db: Session) -> list[GiongDoc]:
    """Mọi giọng, giọng mặc định đứng đầu rồi tới giọng mới nhất.

    Sắp xếp trong Python chứ không trong SQL: bảng này cỡ vài chục dòng, và
    cùng một luật sắp xếp còn được ``xoa()`` dùng lại để chọn giọng kế nhiệm.
    """
    rows = list(db.scalars(sa.select(GiongDoc)).all())
    return sorted(rows, key=lambda g: (not g.mac_dinh, g.created_at), reverse=False)


def lay(db: Session, giong_id: uuid.UUID) -> GiongDoc:
    row = db.get(GiongDoc, giong_id)
    if row is None:
        raise NotFound(f"Không tìm thấy giọng {giong_id}")
    return row


def giong_mac_dinh(db: Session) -> GiongDoc | None:
    """Giọng dùng khi video không chọn riêng. ``None`` khi bảng còn rỗng."""
    return db.scalar(sa.select(GiongDoc).where(GiongDoc.mac_dinh.is_(True)))


def tao(
    db: Session,
    *,
    ten: str,
    nguon: str,
    nha_cung_cap: str,
    ghi_chu: str = "",
    cat_tu_giay: float | None = None,
    cat_den_giay: float | None = None,
    co_file: bool = False,
) -> GiongDoc:
    """Tạo dòng giọng mới ở trạng thái ``dang_xu_ly``.

    Chỉ TẠO DÒNG — chuẩn hoá, gõ chữ, mã hoá và đọc thử chạy trong Celery
    (luật số 1 CLAUDE.md: cả chuỗi đó mất vài chục giây).
    """
    if nguon not in {n.value for n in NguonGiong}:
        raise ApiError(f"Nguồn giọng '{nguon}' không hợp lệ.")
    if nguon == NguonGiong.DUNG_SAN.value:
        raise ApiError(
            "Giọng dựng sẵn chỉ đến từ danh sách nhà cung cấp, không thêm tay được."
        )
    if nguon in NGUON_CAN_FILE and not co_file:
        raise ApiError("Bạn chưa chọn file âm thanh cho giọng này.")
    if nguon == NguonGiong.CAT_TU_FILE.value:
        if cat_tu_giay is None or cat_den_giay is None or cat_den_giay <= cat_tu_giay:
            raise ApiError("Mốc cắt phải có cả điểm đầu và điểm cuối, và cuối phải sau đầu.")

    row = GiongDoc(
        ten=ten.strip() or "Giọng chưa đặt tên",
        nha_cung_cap=nha_cung_cap,
        ma_giong=None,
        model=None,
        ngon_ngu="vi",
        gioi_tinh="",
        nguon=nguon,
        ghi_chu=ghi_chu or None,
        trang_thai=TrangThaiGiong.DANG_XU_LY.value,
        canh_bao=[],
        cat_tu_giay=cat_tu_giay,
        cat_den_giay=cat_den_giay,
    )
    db.add(row)
    #: flush để có ``id`` ngay — router cần nó để ghi file tải lên vào đúng
    #: thư mục trước khi gửi task.
    db.flush()
    log.info("giong.tao", giong_id=str(row.id), nguon=nguon, nha=nha_cung_cap)
    return row


def luu_file_tai_len(giong_id: uuid.UUID, ten_file: str, noi_dung: bytes) -> Path:
    """Ghi file người dùng vừa tải lên vào thư mục của giọng.

    Ở service chứ không ở router: router chỉ được validate và gọi. Đường dẫn đi
    qua ``paths.py`` (luật số 3), đuôi file giữ nguyên để soi thư mục là biết
    file gốc là gì.
    """
    if not noi_dung:
        raise ApiError("File tải lên rỗng — chọn lại file khác.")
    dich = giong_tai_len(str(giong_id), Path(ten_file).suffix.lower())
    dich.write_bytes(noi_dung)
    log.info("giong.nhan_file", giong_id=str(giong_id), so_byte=len(noi_dung))
    return dich


def sua(
    db: Session,
    giong_id: uuid.UUID,
    *,
    ten: str | None = None,
    ghi_chu: str | None = None,
    mac_dinh: bool | None = None,
    mau_text: str | None = None,
) -> tuple[GiongDoc, bool]:
    """Sửa giọng. Trả ``(dòng, có cần dựng lại không)``.

    Chỉ ĐỔI CHỮ của đoạn mẫu mới phải dựng lại: bản ``codes.npz`` mã hoá theo
    chữ cũ, giữ nguyên là model clone đọc theo đúng chữ sai mà người dùng vừa
    sửa xong. Đổi tên hay ghi chú thì không đụng gì tới file.

    So sánh chữ MỚI với chữ CŨ chứ không coi "có gửi lên" là "đã đổi": giao
    diện gửi cả form mỗi lần Lưu, nên cách kia sẽ chạy lại Whisper mỗi lần
    người dùng sửa một dòng ghi chú.
    """
    row = lay(db, giong_id)

    if ten is not None and ten.strip():
        row.ten = ten.strip()
    if ghi_chu is not None:
        row.ghi_chu = ghi_chu or None

    can_dung_lai = False
    if mau_text is not None and mau_text.strip() != (row.mau_text or "").strip():
        row.mau_text = mau_text.strip()
        row.co_ma_hoa = False
        row.trang_thai = TrangThaiGiong.DANG_XU_LY.value
        row.loi = None
        can_dung_lai = True

    if mac_dinh:
        dat_mac_dinh(db, giong_id)

    db.flush()
    return row, can_dung_lai


def dat_mac_dinh(db: Session, giong_id: uuid.UUID) -> GiongDoc:
    """Chuyển cờ mặc định sang giọng này.

    Tắt cờ cũ rồi ``flush`` TRƯỚC khi bật cờ mới: chỉ số duy nhất một phần trên
    ``mac_dinh`` từ chối hai dòng ``true`` cùng lúc, nên gộp hai lệnh vào một
    lần ghi là ăn ``IntegrityError``.
    """
    row = lay(db, giong_id)
    if row.trang_thai != TrangThaiGiong.SAN_SANG.value:
        raise ApiError("Giọng này dựng chưa xong nên chưa đặt làm mặc định được.")

    db.execute(sa.update(GiongDoc).where(GiongDoc.mac_dinh.is_(True)).values(mac_dinh=False))
    db.flush()
    row.mac_dinh = True
    db.flush()
    log.info("giong.dat_mac_dinh", giong_id=str(giong_id))
    return row


def xoa(db: Session, giong_id: uuid.UUID) -> None:
    """Xoá một giọng. Giọng dựng sẵn thì không.

    Xoá giọng đang là mặc định thì chuyển mặc định sang giọng SẴN SÀNG cũ nhất
    còn lại. Để rỗng là mọi video sau đó không biết đọc bằng gì, và lỗi chỉ nổ
    ra ở worker giữa chừng pipeline.
    """
    row = lay(db, giong_id)
    if row.nguon == NguonGiong.DUNG_SAN.value:
        raise ApiError("Giọng dựng sẵn của nhà cung cấp thì không xoá được.")

    la_mac_dinh = row.mac_dinh
    db.delete(row)
    db.flush()

    if la_mac_dinh:
        con_lai = [
            g for g in danh_sach(db) if g.trang_thai == TrangThaiGiong.SAN_SANG.value
        ]
        if con_lai:
            ke_nhiem = min(con_lai, key=lambda g: g.created_at)
            ke_nhiem.mac_dinh = True
            db.flush()
            log.info("giong.mac_dinh_chuyen", giong_id=str(ke_nhiem.id))
        else:
            log.warning("giong.khong_con_giong_nao_lam_mac_dinh")

    log.info("giong.xoa", giong_id=str(giong_id))
```

- [ ] **Step 4: Chạy test cho chắc là qua**

Run: `cd apps/api && pytest tests/test_giong_doc_service.py -v`
Expected: PASS, 17 passed

- [ ] **Step 5: Commit**

```bash
cd apps/api && ruff format . && ruff check --fix .
git add apps/api/src/services/giong_doc_service.py apps/api/tests/test_giong_doc_service.py
git commit -m "feat(giong): service thư viện giọng — thêm, sửa, xoá, đặt mặc định"
```

---

### Task 5: Chuẩn hoá đoạn mẫu và đo âm thanh (hàm thuần + ffmpeg)

Tách phần DỰNG LỆNH và phần ĐỌC SỐ ĐO ra khỏi phần chạy ffmpeg, để test được mà không cần file âm thanh thật.

**Files:**
- Create: `apps/worker/src/pipeline/giong_mau.py`
- Test: `apps/worker/tests/test_giong_mau.py`

**Interfaces:**
- Consumes: `reup_core.giong.DoAmThanh` (Task 1), `ffmpeg.runner.run_ffmpeg`, `ffmpeg.runner.ffmpeg_bin`
- Produces:
  - `DAI_NHAT_GIAY: float = 15.0`
  - `lenh_chuan_hoa(src: Path, dst: Path, *, tu_giay: float | None = None, den_giay: float | None = None) -> list[str]`
  - `doc_so_do(volumedetect_stderr: str, do_dai_giay: float, im_lang_stderr: str) -> DoAmThanh`
  - `chuan_hoa(src: Path, dst: Path, *, tu_giay: float | None = None, den_giay: float | None = None) -> DoAmThanh`

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/worker/tests/test_giong_mau.py`:

```python
"""Chuẩn hoá đoạn giọng mẫu — mẫu tồi thì MỌI video về sau đều tồi.

Fish S2-Pro nhân bản giọng theo ngữ cảnh: nó chép lại đoạn mẫu, kể cả nhiễu,
tiếng vọng và mức âm lượng. Chất lượng đầu ra không bao giờ vượt được chất
lượng đoạn mẫu — nên đây là chỗ đáng đo kỹ nhất của cả thư viện giọng.

Test tách phần DỰNG LỆNH và phần ĐỌC SỐ ĐO khỏi phần chạy ffmpeg: chạy ffmpeg
thật thì phải có file âm thanh thật, mà theo CLAUDE.md ffmpeg thuộc diện kiểm
tay bằng script, không test tự động.
"""

from __future__ import annotations

from pathlib import Path

from src.pipeline.giong_mau import DAI_NHAT_GIAY, doc_so_do, lenh_chuan_hoa


class TestLenhChuanHoa:
    def test_ra_mono_44100(self) -> None:
        cmd = lenh_chuan_hoa(Path("vao.m4a"), Path("ra.wav"))
        assert "-ac" in cmd and cmd[cmd.index("-ac") + 1] == "1"
        assert "-ar" in cmd and cmd[cmd.index("-ar") + 1] == "44100"

    def test_luon_cat_ngan_toi_da(self) -> None:
        #: Đoạn mẫu dài hơn 15 giây chỉ tổ phí ngữ cảnh và làm chậm mỗi câu.
        cmd = lenh_chuan_hoa(Path("vao.wav"), Path("ra.wav"))
        assert "-t" in cmd and float(cmd[cmd.index("-t") + 1]) == DAI_NHAT_GIAY

    def test_cat_khoang_thoi_gian_khi_lay_tu_file_co_san(self) -> None:
        cmd = lenh_chuan_hoa(Path("vao.mp4"), Path("ra.wav"), tu_giay=12.5, den_giay=24.0)
        #: -ss phải đứng TRƯỚC -i mới tua nhanh được; đứng sau là giải mã từ
        #: đầu file, video một tiếng thì chờ rất lâu.
        assert cmd.index("-ss") < cmd.index("-i")
        assert cmd[cmd.index("-ss") + 1] == "12.5"
        assert float(cmd[cmd.index("-t") + 1]) == 11.5

    def test_cat_dai_hon_toi_da_thi_van_bi_khong_che(self) -> None:
        cmd = lenh_chuan_hoa(Path("vao.mp4"), Path("ra.wav"), tu_giay=0.0, den_giay=60.0)
        assert float(cmd[cmd.index("-t") + 1]) == DAI_NHAT_GIAY

    def test_can_am_luong_va_cat_im_lang_hai_dau(self) -> None:
        cmd = lenh_chuan_hoa(Path("vao.wav"), Path("ra.wav"))
        loc = cmd[cmd.index("-af") + 1]
        assert "silenceremove" in loc
        assert "loudnorm" in loc

    def test_khong_dung_shell_va_moi_phan_tu_la_chuoi(self) -> None:
        #: CLAUDE.md cấm shell=True; danh sách lẫn số là lỗi khi truyền subprocess.
        cmd = lenh_chuan_hoa(Path("vao.wav"), Path("ra.wav"), tu_giay=1.0, den_giay=9.0)
        assert all(isinstance(x, str) for x in cmd)

    def test_ghi_de_khong_hoi(self) -> None:
        assert "-y" in lenh_chuan_hoa(Path("a.wav"), Path("b.wav"))


class TestDocSoDo:
    #: Trích đúng dạng ffmpeg in ra thật.
    VOL = "[Parsed_volumedetect_0 @ 0x0] mean_volume: -21.4 dB\n" \
          "[Parsed_volumedetect_0 @ 0x0] max_volume: -3.1 dB\n"

    def test_doi_dB_sang_bien_do(self) -> None:
        do = doc_so_do(self.VOL, 12.0, "")
        #: -3,1 dB ≈ 0,70 biên độ; -21,4 dB ≈ 0,085.
        assert 0.69 < do.dinh < 0.71
        assert 0.08 < do.rms < 0.09
        assert do.do_dai_giay == 12.0

    def test_khong_co_im_lang_thi_ti_le_bang_khong(self) -> None:
        assert doc_so_do(self.VOL, 10.0, "").ti_le_im_lang == 0.0

    def test_cong_don_moi_doan_im_lang(self) -> None:
        im = (
            "[silencedetect @ 0x0] silence_start: 1.0\n"
            "[silencedetect @ 0x0] silence_end: 3.0 | silence_duration: 2\n"
            "[silencedetect @ 0x0] silence_start: 6.0\n"
            "[silencedetect @ 0x0] silence_end: 8.0 | silence_duration: 2\n"
        )
        assert doc_so_do(self.VOL, 10.0, im).ti_le_im_lang == 0.4

    def test_thieu_so_lieu_thi_ve_khong_chu_khong_no(self) -> None:
        #: ffmpeg đổi định dạng in ra là chuyện có thật. Nổ ở đây thì thêm
        #: giọng nào cũng hỏng; về 0 thì cổng chất lượng cảnh báo "quá nhỏ"
        #: và người dùng vẫn đi tiếp được.
        do = doc_so_do("không có gì", 5.0, "")
        assert do.rms == 0.0 and do.dinh == 0.0

    def test_do_dai_bang_khong_khong_chia_cho_khong(self) -> None:
        im = "[silencedetect @ 0x0] silence_duration: 2\n"
        assert doc_so_do(self.VOL, 0.0, im).ti_le_im_lang == 0.0
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/worker && pytest tests/test_giong_mau.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.pipeline.giong_mau'`

- [ ] **Step 3: Viết bản cài đặt**

Tạo `apps/worker/src/pipeline/giong_mau.py`:

```python
"""Chuẩn hoá và đo đoạn giọng mẫu trước khi đưa vào thư viện giọng.

Vì sao đo kỹ: Fish S2-Pro nhân bản giọng theo ngữ cảnh — nó CHÉP LẠI đoạn
mẫu, kể cả nhiễu, tiếng vọng và mức âm lượng. Chất lượng bản lồng tiếng không
bao giờ vượt được chất lượng đoạn mẫu. Đo ngày 2026-08-20 đã dính đúng bẫy
này: lấy đầu ra của Edge TTS làm mẫu, tức bắt model chép lại một giọng máy.

Ba hàm tách bạch để test được: ``lenh_chuan_hoa`` chỉ dựng danh sách tham số,
``doc_so_do`` chỉ đọc chữ ffmpeg in ra, ``chuan_hoa`` mới thật sự chạy.
"""

from __future__ import annotations

import re
from pathlib import Path

from reup_core.giong import DoAmThanh
from reup_core.logging import get_logger

from ..ffmpeg.runner import ffmpeg_bin, run_ffmpeg

log = get_logger(__name__)

#: Trần độ dài đoạn mẫu. Dài hơn chỉ tổ phí ngữ cảnh và làm chậm mỗi câu, mà
#: không thêm đặc trưng giọng nào.
DAI_NHAT_GIAY = 15.0

#: Ngưỡng coi là im lặng khi dò. -45 dB là mức phòng yên, không phải mức nhạc nhỏ.
NGUONG_IM_LANG_DB = -45


def lenh_chuan_hoa(
    src: Path,
    dst: Path,
    *,
    tu_giay: float | None = None,
    den_giay: float | None = None,
) -> list[str]:
    """Dựng lệnh ffmpeg đưa đoạn mẫu về mono 44,1kHz, cắt im lặng, cân âm lượng.

    Hàm THUẦN — chỉ trả danh sách tham số, không chạy gì. Nhờ vậy test khoá
    được từng lựa chọn mà không cần file âm thanh thật.

    ``-ss`` đặt TRƯỚC ``-i``: đứng sau thì ffmpeg giải mã từ đầu file, cắt một
    đoạn giữa video một tiếng sẽ chờ rất lâu.

    Luôn khống chế bằng ``-t``, kể cả khi người dùng chọn khoảng dài hơn
    ``DAI_NHAT_GIAY``.
    """
    dai = DAI_NHAT_GIAY
    if tu_giay is not None and den_giay is not None:
        dai = min(DAI_NHAT_GIAY, max(0.0, den_giay - tu_giay))

    cmd = [ffmpeg_bin(), "-y"]
    if tu_giay is not None:
        cmd += ["-ss", str(tu_giay)]
    cmd += ["-i", str(src), "-t", str(dai)]

    #: silenceremove cắt im lặng ở HAI đầu (stop_periods=-1 lo phần đuôi);
    #: loudnorm đưa về mức chuẩn để mọi giọng trong thư viện nghe ngang nhau.
    cmd += [
        "-af",
        (
            f"silenceremove=start_periods=1:start_threshold={NGUONG_IM_LANG_DB}dB:"
            f"start_silence=0.1,areverse,"
            f"silenceremove=start_periods=1:start_threshold={NGUONG_IM_LANG_DB}dB:"
            f"start_silence=0.1,areverse,"
            "loudnorm=I=-18:TP=-2:LRA=11"
        ),
        "-ac",
        "1",
        "-ar",
        "44100",
        "-vn",
        str(dst),
    ]
    return cmd


def _db_sang_bien_do(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def doc_so_do(volumedetect_stderr: str, do_dai_giay: float, im_lang_stderr: str) -> DoAmThanh:
    """Đọc số đo từ chữ ffmpeg in ra. Hàm THUẦN.

    Thiếu số liệu thì trả 0 chứ KHÔNG ném lỗi: ffmpeg đổi định dạng in ra là
    chuyện có thật, nổ ở đây thì thêm giọng nào cũng hỏng. Về 0 thì cổng chất
    lượng cảnh báo "quá nhỏ" và người dùng vẫn đi tiếp được.
    """

    def _lay(ten: str) -> float:
        m = re.search(rf"{ten}:\s*(-?[\d.]+) dB", volumedetect_stderr)
        return _db_sang_bien_do(float(m.group(1))) if m else 0.0

    tong_im = sum(float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", im_lang_stderr))

    return DoAmThanh(
        do_dai_giay=do_dai_giay,
        rms=_lay("mean_volume"),
        dinh=_lay("max_volume"),
        ti_le_im_lang=round(tong_im / do_dai_giay, 4) if do_dai_giay > 0 else 0.0,
    )


def chuan_hoa(
    src: Path,
    dst: Path,
    *,
    tu_giay: float | None = None,
    den_giay: float | None = None,
) -> DoAmThanh:
    """Chuẩn hoá đoạn mẫu rồi đo nó. Ghi ra file TẠM rồi đổi tên.

    Ghi thẳng vào ``dst`` thì crash giữa chừng để lại file dở dang mà bước sau
    tưởng là hợp lệ (luật CLAUDE.md về ffmpeg).
    """
    from reup_core.paths import tmp_sibling

    dst.parent.mkdir(parents=True, exist_ok=True)
    tam = tmp_sibling(dst)

    run_ffmpeg(lenh_chuan_hoa(src, tam, tu_giay=tu_giay, den_giay=den_giay)[1:])
    tam.rename(dst)

    from ..ffmpeg.probe import do_dai_am_thanh

    do_dai = do_dai_am_thanh(dst)
    #: volumedetect và silencedetect đều in ra stderr và không sinh file —
    #: xuất ra null.
    vol = run_ffmpeg(["-i", str(dst), "-af", "volumedetect", "-f", "null", "-"])
    im = run_ffmpeg(
        ["-i", str(dst), "-af", f"silencedetect=n={NGUONG_IM_LANG_DB}dB:d=0.3", "-f", "null", "-"]
    )

    do = doc_so_do(vol, do_dai, im)
    log.info(
        "giong_mau.chuan_hoa_xong",
        dst=str(dst),
        do_dai=do.do_dai_giay,
        rms=round(do.rms, 4),
        dinh=round(do.dinh, 4),
        im_lang=do.ti_le_im_lang,
    )
    return do
```

Kiểm `run_ffmpeg` nhận danh sách KHÔNG gồm tên chương trình (xem `apps/worker/src/ffmpeg/runner.py`); nếu nó tự thêm `ffmpeg_bin()` thì bỏ `[1:]` cho khớp.

- [ ] **Step 4: Chạy test cho chắc là qua**

Run: `cd apps/worker && pytest tests/test_giong_mau.py -v`
Expected: PASS, 12 passed

- [ ] **Step 5: Commit**

```bash
cd apps/worker && ruff format . && ruff check --fix .
git add apps/worker/src/pipeline/giong_mau.py apps/worker/tests/test_giong_mau.py
git commit -m "feat(giong): chuẩn hoá và đo đoạn giọng mẫu trước khi vào thư viện"
```

---

### Task 6: Task Celery dựng giọng — chuẩn hoá, gõ chữ, đọc thử

**Files:**
- Create: `apps/worker/src/tasks/giong.py`
- Modify: `apps/worker/src/celery_app.py`
- Test: `apps/worker/tests/test_task_giong.py`

**Interfaces:**
- Consumes: `pipeline.giong_mau.chuan_hoa`, `reup_core.giong.kiem_chat_luong`, `pipeline.transcribe.transcribe`, `tts.lay_provider`, `reup_core.paths.giong_*`
- Produces:
  - task `reup.chuan_bi_giong`, queue `media`
  - `chon_duong_mau(nguon: str) -> str` — `"tam_tu_may"` dựng bằng Edge, còn lại dùng file tải lên

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/worker/tests/test_task_giong.py`:

```python
"""Dựng một giọng cho thư viện: chuẩn hoá -> gõ chữ -> cổng chất lượng -> đọc thử.

Chạy qua Celery vì cả chuỗi mất vài chục giây (riêng Whisper đã vài giây),
quá xa mức 2 giây mà endpoint được phép chờ.

Test ở đây khoá phần ĐIỀU PHỐI: gọi đúng thứ tự, hỏng thì đánh dấu HONG chứ
không để giọng treo ở DANG_XU_LY mãi. Phần ffmpeg và Whisper là đối tượng
giả — chúng thuộc diện kiểm tay bằng script theo CLAUDE.md.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.giong import CanhBao, DoAmThanh

from src.tasks.giong import chon_duong_mau, dung_giong


class DbGia:
    def __init__(self, row):
        self.row = row

    def get(self, _model, _id):
        return self.row


@pytest.fixture
def giong():
    return SimpleNamespace(
        id=uuid.uuid4(),
        ten="Giọng thử",
        nguon=NguonGiong.TU_THU.value,
        nha_cung_cap="fish_mlx",
        ma_giong=None,
        model=None,
        mau_text=None,
        trang_thai=TrangThaiGiong.DANG_XU_LY.value,
        canh_bao=[],
        cat_tu_giay=None,
        cat_den_giay=None,
    )


def test_tam_tu_may_dung_bang_edge_con_lai_dung_file_tai_len() -> None:
    assert chon_duong_mau(NguonGiong.TAM_TU_MAY.value) == "edge"
    for n in (NguonGiong.TU_THU, NguonGiong.CAT_TU_FILE, NguonGiong.THUE_DOC):
        assert chon_duong_mau(n.value) == "tai_len"


def test_chay_du_bon_buoc_va_danh_dau_san_sang(giong, monkeypatch) -> None:
    da_goi = []
    monkeypatch.setattr(
        "src.tasks.giong.chuan_hoa",
        lambda *a, **k: (da_goi.append("chuan_hoa"), DoAmThanh(11.0, 0.12, 0.6, 0.05))[1],
    )
    monkeypatch.setattr(
        "src.tasks.giong.transcribe",
        lambda *a, **k: (da_goi.append("transcribe"), [SimpleNamespace(text="Xin chào các bạn")])[1],
    )
    monkeypatch.setattr("src.tasks.giong.doc_thu", lambda *a, **k: da_goi.append("doc_thu"))

    dung_giong(DbGia(giong), giong.id)

    assert da_goi == ["chuan_hoa", "transcribe", "doc_thu"]
    assert giong.trang_thai == TrangThaiGiong.SAN_SANG.value
    assert giong.mau_text == "Xin chào các bạn"
    assert giong.canh_bao == []


def test_canh_bao_duoc_luu_lai_nhung_KHONG_chan(giong, monkeypatch) -> None:
    #: Cảnh báo chứ không chặn — người dùng có thể cố tình dùng mẫu lạ. Nhưng
    #: phải nói ra, không để họ phát hiện sau khi lồng tiếng cả video.
    monkeypatch.setattr(
        "src.tasks.giong.chuan_hoa", lambda *a, **k: DoAmThanh(3.0, 0.005, 0.99, 0.6)
    )
    monkeypatch.setattr(
        "src.tasks.giong.transcribe", lambda *a, **k: [SimpleNamespace(text="ngắn")]
    )
    monkeypatch.setattr("src.tasks.giong.doc_thu", lambda *a, **k: None)

    dung_giong(DbGia(giong), giong.id)

    assert giong.trang_thai == TrangThaiGiong.SAN_SANG.value
    ma = {c["ma"] for c in giong.canh_bao}
    assert {"qua_ngan", "vo_tieng", "qua_nho", "nhieu_im_lang"} <= ma


def test_hong_thi_danh_dau_HONG_chu_khong_treo(giong, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.tasks.giong.chuan_hoa",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ffmpeg chết")),
    )
    with pytest.raises(RuntimeError):
        dung_giong(DbGia(giong), giong.id)
    assert giong.trang_thai == TrangThaiGiong.HONG.value
    assert "ffmpeg chết" in giong.loi


def test_whisper_gõ_ra_rong_thi_bao_hong(giong, monkeypatch) -> None:
    #: Không có phần chữ thì nhân bản giọng không chạy được — Fish cần CẢ
    #: audio lẫn transcript khớp từng chữ.
    monkeypatch.setattr("src.tasks.giong.chuan_hoa", lambda *a, **k: DoAmThanh(11.0, 0.1, 0.5, 0.0))
    monkeypatch.setattr("src.tasks.giong.transcribe", lambda *a, **k: [])
    monkeypatch.setattr("src.tasks.giong.doc_thu", lambda *a, **k: None)

    with pytest.raises(Exception, match="không nghe ra chữ nào"):
        dung_giong(DbGia(giong), giong.id)
    assert giong.trang_thai == TrangThaiGiong.HONG.value
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/worker && pytest tests/test_task_giong.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.tasks.giong'`

- [ ] **Step 3: Viết task**

Tạo `apps/worker/src/tasks/giong.py`:

```python
"""Dựng một giọng cho thư viện: chuẩn hoá -> gõ chữ -> cổng chất lượng -> đọc thử.

Tách ``dung_giong`` (nhận sẵn session) khỏi task Celery để test được phần điều
phối mà không cần Redis.
"""

from __future__ import annotations

from pathlib import Path

from reup_core.db import session_scope
from reup_core.enums import NguonGiong, TrangThaiGiong
from reup_core.giong import CAU_NGHE_THU, DOAN_MAU_TAM, kiem_chat_luong
from reup_core.logging import get_logger
from reup_core.models import GiongDoc
from reup_core.paths import giong_mau_txt, giong_mau_wav, giong_nghe_thu, giong_tai_len

from ..celery_app import app
from ..errors import ReupError
from ..pipeline.giong_mau import chuan_hoa
from ..pipeline.transcribe import transcribe
from ..tts import lay_provider

log = get_logger(__name__)


def chon_duong_mau(nguon: str) -> str:
    """Lấy đoạn mẫu từ đâu: dựng bằng máy, hay dùng file người dùng tải lên."""
    return "edge" if nguon == NguonGiong.TAM_TU_MAY.value else "tai_len"


def doc_thu(giong: GiongDoc) -> None:
    """Đọc CÂU CỐ ĐỊNH bằng chính giọng này, để nghe so với các giọng khác.

    Cố định câu cho mọi giọng mới so được sòng phẳng — mỗi giọng một câu khác
    thì nghe xong không biết khác nhau do giọng hay do câu.
    """
    dst = giong_nghe_thu(str(giong.id))
    provider = lay_provider(giong.nha_cung_cap, model=giong.model or "")
    provider.doc(CAU_NGHE_THU, dst, giong=giong.ma_giong or str(giong.id))


def _nguon_am_thanh(giong: GiongDoc) -> Path:
    """File âm thanh đầu vào — tải lên sẵn, hoặc dựng tạm bằng Edge."""
    if chon_duong_mau(giong.nguon) != "edge":
        tim = sorted(giong_tai_len(str(giong.id), "*").parent.glob("tai-len.*"))
        if not tim:
            raise ReupError("Chưa có file âm thanh nào được tải lên cho giọng này.")
        return tim[0]

    #: Giọng tạm: dựng bằng Edge ngay tại chỗ để cắm điện là chạy được, nhưng
    #: bảng đánh dấu rõ ``TAM_TU_MAY`` và giao diện ghi "giọng tạm".
    tam = giong_tai_len(str(giong.id), "mp3")
    lay_provider("edge").doc(DOAN_MAU_TAM, tam, giong="vi-VN-HoaiMyNeural")
    return tam


def dung_giong(db, giong_id) -> None:
    """Bốn bước dựng một giọng. Hỏng thì đánh dấu HONG rồi ném lại.

    Không đánh dấu thì giọng treo ở ``DANG_XU_LY`` mãi mãi và người dùng ngồi
    chờ một việc đã chết.
    """
    giong = db.get(GiongDoc, giong_id)
    if giong is None:
        raise ReupError(f"Không có giọng {giong_id}")

    try:
        mau = giong_mau_wav(str(giong.id))
        do = chuan_hoa(
            _nguon_am_thanh(giong),
            mau,
            tu_giay=giong.cat_tu_giay,
            den_giay=giong.cat_den_giay,
        )

        cues = transcribe(mau, language="vi")
        chu = " ".join(c.text.strip() for c in cues).strip()
        if not chu:
            raise ReupError(
                "Whisper không nghe ra chữ nào trong đoạn mẫu — "
                "nhân bản giọng cần cả âm thanh lẫn phần chữ khớp từng chữ."
            )
        giong.mau_text = chu
        giong_mau_txt(str(giong.id)).write_text(chu, encoding="utf-8")

        #: CẢNH BÁO chứ không chặn (spec C4). Lưu vào DB để giao diện hiện
        #: được ngay trên thẻ giọng.
        giong.canh_bao = [{"ma": c.ma, "thong_diep": c.thong_diep} for c in kiem_chat_luong(do)]

        doc_thu(giong)

        giong.trang_thai = TrangThaiGiong.SAN_SANG.value
        giong.loi = None
        log.info(
            "giong.dung_xong", giong_id=str(giong.id), canh_bao=len(giong.canh_bao), chu=chu[:60]
        )
    except Exception as exc:
        giong.trang_thai = TrangThaiGiong.HONG.value
        giong.loi = str(exc)[:500]
        log.error("giong.dung_hong", giong_id=str(giong_id), error=str(exc)[:200])
        raise


@app.task(name="reup.chuan_bi_giong")
def chuan_bi_giong_task(giong_id: str) -> dict:
    with session_scope() as db:
        dung_giong(db, giong_id)
    return {"giong_id": giong_id}
```

- [ ] **Step 4: Chạy test cho chắc là qua**

Run: `cd apps/worker && pytest tests/test_task_giong.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Đăng ký task với Celery**

`app.autodiscover_tasks(["src.tasks"])` ở `celery_app.py:76` KHÔNG bắt được module này — nó tìm `src.tasks.tasks`, mà `src/tasks/__init__.py` đang RỖNG. Task hiện có đăng ký bằng dòng import tay ở dòng 77.

Bỏ bước này thì API trả 202, người dùng thấy "đang xử lý…" và **giọng treo mãi ở trạng thái đó** — không lỗi, không log.

Thêm vào cuối `apps/worker/src/celery_app.py`:

```python
from .tasks import video as _video_tasks  # noqa: E402,F401
from .tasks import giong as _giong_tasks  # noqa: E402,F401
```

Kiểm:

```bash
cd apps/worker && python -c "
from src.celery_app import app
print('reup.chuan_bi_giong' in app.tasks)"
```

Expected: `True`

Nhớ: **Celery không tự nạp lại code** — worker đang chạy phải khởi động lại mới thấy task mới.

- [ ] **Step 6: Script kiểm tay**

CLAUDE.md yêu cầu mỗi task media mới kèm một script `try_*.py`. Tạo `apps/worker/scripts/try_them_giong.py`:

```python
"""Thêm một giọng từ file thật rồi nghe kết quả. Chạy tay, không phải test.

    python scripts/try_them_giong.py ~/Desktop/giong-toi.m4a
    python scripts/try_them_giong.py video.mp4 --tu 12.5 --den 26

In ra số đo, cảnh báo của cổng chất lượng, phần chữ Whisper gõ được, và đường
dẫn file đọc thử để NGHE BẰNG TAI — đây là thứ test tự động không thay được.
"""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from reup_core.giong import kiem_chat_luong

from src.pipeline.giong_mau import chuan_hoa
from src.pipeline.transcribe import transcribe


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("--tu", type=float, default=None)
    p.add_argument("--den", type=float, default=None)
    args = p.parse_args()

    ra = Path("/tmp") / f"giong-thu-{uuid.uuid4().hex[:8]}"
    ra.mkdir(parents=True, exist_ok=True)
    mau = ra / "mau.wav"

    do = chuan_hoa(Path(args.file), mau, tu_giay=args.tu, den_giay=args.den)
    print(f"\nđộ dài  {do.do_dai_giay:.1f}s")
    print(f"rms     {do.rms:.4f}")
    print(f"đỉnh    {do.dinh:.3f}")
    print(f"im lặng {do.ti_le_im_lang:.0%}")

    canh_bao = kiem_chat_luong(do)
    print("\ncảnh báo:" if canh_bao else "\ncảnh báo: không có")
    for c in canh_bao:
        print(f"  [{c.ma}] {c.thong_diep}")

    chu = " ".join(c.text.strip() for c in transcribe(mau, language="vi")).strip()
    print(f"\nWhisper gõ được:\n  {chu}\n")
    print(f"NGHE THỬ đoạn mẫu đã chuẩn hoá: {mau}")


main()
```

Chạy thử với một file thật:

```bash
cd apps/worker && python scripts/try_them_giong.py <đường-dẫn-file-thu-giọng>
open /tmp/giong-thu-*/mau.wav
```

- [ ] **Step 7: Commit**

```bash
cd apps/worker && ruff format . && ruff check --fix .
git add apps/worker/src/tasks/giong.py apps/worker/tests/test_task_giong.py apps/worker/src/celery_app.py apps/worker/scripts/try_them_giong.py
git commit -m "feat(giong): task dựng giọng — chuẩn hoá, Whisper gõ chữ, đọc thử"
```

---

### Task 7: API thư viện giọng

**Files:**
- Create: `apps/api/src/routers/giong_doc.py`
- Create: `apps/api/src/schemas/giong_doc.py`
- Modify: `apps/api/src/main.py`
- Modify: `apps/api/src/services/task_bridge.py`
- Test: `apps/api/tests/test_giong_doc_api.py`

**Interfaces:**
- Consumes: `giong_doc_service.*` (Task 4), `paths.giong_nghe_thu`, `paths.giong_mau_wav`
- Produces:
  - schemas `GiongDocOut`, `TaoGiongIn`, `SuaGiongIn`
  - `task_bridge.chuan_bi_giong(giong_id: uuid.UUID) -> str` — task `reup.chuan_bi_giong`, `queue="media"`
  - sáu endpoint dưới `/api/v1/giong-doc`

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/api/tests/test_giong_doc_api.py`:

```python
"""Thư viện giọng: chỗ DUY NHẤT quản mọi giọng, dựng sẵn lẫn clone.

Trước đây ba nhóm giọng hardcode trong ``video_service.cac_giong_doc`` và giao
diện bắt chọn ba tầng. Thêm giọng clone vào khuôn đó là thêm tầng thứ tư.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from reup_core.enums import NguonGiong, TrangThaiGiong

from src.errors import ApiError
from src.services import giong_doc_service


def test_tao_giong_tra_ve_trang_thai_dang_xu_ly() -> None:
    #: Endpoint trả 202 rồi worker mới chạy — chuẩn hoá + Whisper + đọc thử
    #: mất vài chục giây, quá xa mức 2 giây được phép chờ (luật số 1).
    db = _DbGia()
    g = giong_doc_service.tao(
        db, ten="Giọng tôi", nguon=NguonGiong.TU_THU.value, nha_cung_cap="fish_mlx", co_file=True
    )
    assert g.trang_thai == TrangThaiGiong.DANG_XU_LY.value


def test_khong_xoa_duoc_giong_dung_san() -> None:
    g = SimpleNamespace(
        id=uuid.uuid4(), nguon=NguonGiong.DUNG_SAN.value, mac_dinh=False, ten="Hoài My"
    )
    with pytest.raises(ApiError, match="dựng sẵn"):
        giong_doc_service.xoa(_DbGia(g), g.id)


def test_xoa_giong_dang_mac_dinh_thi_chuyen_mac_dinh_sang_giong_khac() -> None:
    #: Để rỗng thì video sau không biết đọc bằng gì và pipeline chết giữa chừng.
    xoa_di = SimpleNamespace(
        id=uuid.uuid4(), nguon=NguonGiong.TU_THU.value, mac_dinh=True, ten="Sắp xoá"
    )
    con_lai = SimpleNamespace(
        id=uuid.uuid4(), nguon=NguonGiong.DUNG_SAN.value, mac_dinh=False, ten="Hoài My"
    )
    db = _DbGia(xoa_di, danh_sach=[xoa_di, con_lai])
    giong_doc_service.xoa(db, xoa_di.id)
    assert con_lai.mac_dinh is True


def test_dat_mac_dinh_tat_co_cu() -> None:
    cu = SimpleNamespace(id=uuid.uuid4(), mac_dinh=True, nguon=NguonGiong.DUNG_SAN.value)
    moi = SimpleNamespace(id=uuid.uuid4(), mac_dinh=False, nguon=NguonGiong.TU_THU.value)
    db = _DbGia(moi, danh_sach=[cu, moi])
    giong_doc_service.dat_mac_dinh(db, moi.id)
    assert (cu.mac_dinh, moi.mac_dinh) == (False, True)


class _DbGia:
    def __init__(self, row=None, danh_sach=None):
        self.row = row
        self._ds = danh_sach or []
        self.da_them = []

    def get(self, _model, _id):
        return self.row

    def add(self, obj):
        self.da_them.append(obj)

    def delete(self, _obj):
        pass

    def flush(self):
        pass

    def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: self._ds)

    def scalar(self, _stmt):
        return self.row
```

Nếu Task 4 đã viết những test này rồi thì bỏ qua trùng lặp — chỉ giữ test nào chưa có.

- [ ] **Step 2: Chạy test cho chắc là hỏng hoặc đã qua**

Run: `cd apps/api && pytest tests/test_giong_doc_api.py -v`
Expected: hỏng ở test nào Task 4 chưa phủ; test đã phủ thì PASS.

- [ ] **Step 3: Bổ sung service cho phần còn thiếu**

Chạy test và bổ sung đúng phần thiếu vào `apps/api/src/services/giong_doc_service.py` (đã tạo ở Task 4). Không viết lại hàm đã có.

- [ ] **Step 4: Viết schema**

Tạo `apps/api/src/schemas/giong_doc.py`:

```python
"""Kiểu vào/ra cho thư viện giọng."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CanhBaoOut(BaseModel):
    ma: str
    thong_diep: str


class GiongDocOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    ten: str
    nha_cung_cap: str
    ma_giong: str | None = None
    model: str | None = None
    ngon_ngu: str = "vi"
    nguon: str
    mau_text: str | None = None
    trang_thai: str
    mac_dinh: bool = False
    ghi_chu: str | None = None
    loi: str | None = None
    canh_bao: list[CanhBaoOut] = Field(default_factory=list)
    created_at: datetime


class TaoGiongIn(BaseModel):
    """Tạo giọng. File âm thanh gửi kèm dạng multipart, không nằm trong body này."""

    ten: str = Field(min_length=1, max_length=80)
    nguon: str
    nha_cung_cap: str = "fish_mlx"
    ghi_chu: str = ""
    #: Chỉ dùng khi ``nguon="cat_tu_file"`` — cắt đoạn nào trong file dài.
    cat_tu_giay: float | None = None
    cat_den_giay: float | None = None


class SuaGiongIn(BaseModel):
    ten: str | None = Field(default=None, min_length=1, max_length=80)
    ghi_chu: str | None = None
    mac_dinh: bool | None = None
    #: Sửa lại phần chữ Whisper gõ chưa khớp. Lệch chữ là méo giọng.
    mau_text: str | None = None
```

- [ ] **Step 5: Thêm `task_bridge.chuan_bi_giong`**

Trong `apps/api/src/services/task_bridge.py`:

```python
CHUAN_BI_GIONG = "reup.chuan_bi_giong"


def chuan_bi_giong(giong_id: uuid.UUID) -> str:
    """Đẩy task dựng giọng: chuẩn hoá, Whisper gõ chữ, đọc thử.

    ``queue="media"``: ffmpeg và Whisper đều là việc CPU. BẮT BUỘC truyền
    queue — app Celery của API không mang ``task_routes`` của worker, thiếu nó
    task rơi vào hàng không ai nghe và giọng treo mãi ở "đang xử lý".
    """
    result = celery().send_task(CHUAN_BI_GIONG, args=[str(giong_id)], queue="media")
    return result.id
```

- [ ] **Step 6: Viết router**

Tạo `apps/api/src/routers/giong_doc.py`:

```python
"""Thư viện giọng — chỗ duy nhất quản mọi giọng đọc.

Router chỉ validate rồi gọi service (luật ba lớp CLAUDE.md).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from reup_core.paths import giong_nghe_thu
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import NotFound
from ..schemas.common import TaskAccepted
from ..schemas.giong_doc import GiongDocOut, SuaGiongIn
from ..services import giong_doc_service, task_bridge

router = APIRouter(prefix="/giong-doc", tags=["giong-doc"])


@router.get("", response_model=list[GiongDocOut])
def danh_sach(db: Session = Depends(get_db)):
    """Mọi giọng: dựng sẵn của Edge/Gemini/OpenRouter LẪN giọng đã clone."""
    return giong_doc_service.danh_sach(db)


@router.post("", response_model=TaskAccepted, status_code=202)
async def tao(
    ten: str = Form(...),
    nguon: str = Form(...),
    nha_cung_cap: str = Form("fish_mlx"),
    ghi_chu: str = Form(""),
    cat_tu_giay: float | None = Form(None),
    cat_den_giay: float | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """Thêm giọng mới. Trả 202 — dựng giọng mất vài chục giây, chạy nền.

    Commit TRƯỚC khi gửi task: worker chạy gần như tức thì, chậm một nhịp là
    nó đọc phải dòng chưa có.
    """
    giong = giong_doc_service.tao(
        db,
        ten=ten,
        nguon=nguon,
        nha_cung_cap=nha_cung_cap,
        ghi_chu=ghi_chu,
        cat_tu_giay=cat_tu_giay,
        cat_den_giay=cat_den_giay,
        co_file=file is not None,
    )
    if file is not None:
        giong_doc_service.luu_file_tai_len(giong.id, file.filename or "tai-len", await file.read())
    db.commit()

    task_id = task_bridge.chuan_bi_giong(giong.id)
    return TaskAccepted(task_id=task_id, message=f"Đang dựng giọng “{ten}”")


@router.get("/{giong_id}/nghe-thu")
def nghe_thu(giong_id: uuid.UUID, db: Session = Depends(get_db)):
    """Câu đọc thử CỐ ĐỊNH — mọi giọng đọc cùng câu để so cho sòng phẳng."""
    giong_doc_service.lay(db, giong_id)
    f = giong_nghe_thu(str(giong_id))
    if not f.exists() or f.stat().st_size == 0:
        raise NotFound("Giọng này chưa dựng xong hoặc dựng hỏng — chưa có gì để nghe.")
    return FileResponse(f, media_type="audio/wav", filename=f"nghe-thu-{giong_id}.wav")


@router.patch("/{giong_id}", response_model=GiongDocOut)
def sua(giong_id: uuid.UUID, body: SuaGiongIn, db: Session = Depends(get_db)):
    """Đổi tên, ghi chú, đặt mặc định, hoặc chữa lại phần chữ của đoạn mẫu."""
    giong, doc_lai = giong_doc_service.sua(
        db,
        giong_id,
        ten=body.ten,
        ghi_chu=body.ghi_chu,
        mac_dinh=body.mac_dinh,
        mau_text=body.mau_text,
    )
    db.commit()
    #: Sửa phần chữ là đổi đoạn mẫu -> phải mã hoá lại và đọc thử lại, nếu
    #: không thì giọng vẫn theo bản chữ cũ mà giao diện hiện chữ mới.
    if doc_lai:
        task_bridge.chuan_bi_giong(giong_id)
    return giong


@router.delete("/{giong_id}", status_code=204)
def xoa(giong_id: uuid.UUID, db: Session = Depends(get_db)):
    giong_doc_service.xoa(db, giong_id)
    db.commit()


@router.post("/{giong_id}/doc-lai", response_model=TaskAccepted, status_code=202)
def doc_lai(giong_id: uuid.UUID, db: Session = Depends(get_db)):
    """Dựng lại câu đọc thử — dùng khi đổi nhà cung cấp hoặc lần trước hỏng."""
    giong_doc_service.lay(db, giong_id)
    task_id = task_bridge.chuan_bi_giong(giong_id)
    return TaskAccepted(task_id=task_id, message="Đang dựng lại câu đọc thử")
```

- [ ] **Step 7: Gắn router vào app**

Trong `apps/api/src/main.py`, thêm vào cùng chỗ các router khác đang được `include_router`:

```python
from .routers import giong_doc
...
app.include_router(giong_doc.router, prefix="/api/v1")
```

Đọc file để bám đúng khuôn prefix đang dùng.

- [ ] **Step 8: Kiểm bằng máy chủ thật**

```bash
cd apps/api && uvicorn src.main:app --port 8000 &
sleep 4
curl -s http://localhost:8000/api/v1/giong-doc | python3 -m json.tool | head -20
kill %1
```

Expected: danh sách giọng dựng sẵn đã seed ở Task 3 (Edge, và Gemini/OpenRouter nếu có khoá).

- [ ] **Step 9: Chạy toàn bộ test rồi commit**

```bash
cd apps/api && pytest -q && ruff format . && ruff check --fix .
git add apps/api/src/routers/giong_doc.py apps/api/src/schemas/giong_doc.py apps/api/src/main.py apps/api/src/services/task_bridge.py apps/api/src/services/giong_doc_service.py apps/api/tests/test_giong_doc_api.py
git commit -m "feat(api): endpoint thư viện giọng — thêm, nghe thử, sửa, xoá"
```

---

### Task 8: Giao diện — mục "Giọng đọc" trong trang Cấu hình

**Files:**
- Create: `apps/web/components/ThuVienGiong.tsx`
- Create: `apps/web/components/ThemGiongModal.tsx`
- Modify: `apps/web/app/settings/page.tsx`
- Modify: `apps/web/lib/api.ts`

**Interfaces:**
- Consumes: sáu endpoint ở Task 7
- Produces: `<ThuVienGiong />`, `<ThemGiongModal />`

- [ ] **Step 1: Thêm đường gọi API**

Trong `apps/web/lib/api.ts`:

```ts
  giongDoc: () => request<GiongDoc[]>("/giong-doc"),

  ngheThuUrl: (id: string) => `${PREFIX}/giong-doc/${id}/nghe-thu`,

  themGiong: (form: FormData) =>
    request<TaskAccepted>("/giong-doc", { method: "POST", body: form }),

  suaGiong: (id: string, body: Record<string, unknown>) =>
    request<GiongDoc>(`/giong-doc/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  xoaGiong: (id: string) => request<void>(`/giong-doc/${id}`, { method: "DELETE" }),

  docLaiGiong: (id: string) =>
    request<TaskAccepted>(`/giong-doc/${id}/doc-lai`, { method: "POST" }),
```

Kiểm hàm `request` có tự đặt `Content-Type: application/json` không — nếu có thì phải BỎ header đó khi body là `FormData`, không thì trình duyệt không chèn được `boundary` và upload hỏng.

- [ ] **Step 2: Sinh lại type từ OpenAPI**

```bash
cd apps/api && uvicorn src.main:app --port 8000 &
sleep 4
cd apps/web && npx openapi-typescript http://localhost:8000/openapi.json -o lib/types.gen.ts
kill %1
```

- [ ] **Step 3: Viết `ThuVienGiong.tsx`**

```tsx
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { ThemGiongModal } from "@/components/ThemGiongModal";
import { api } from "@/lib/api";
import type { GiongDoc } from "@/lib/types";

const NHAN_NGUON: Record<string, string> = {
  dung_san: "dựng sẵn",
  tu_thu: "tự thu",
  cat_tu_file: "cắt từ file",
  thue_doc: "thuê đọc",
  tam_tu_may: "giọng tạm",
};

/**
 * Thư viện giọng — mọi giọng ở MỘT chỗ, dựng sẵn lẫn clone.
 *
 * Vì sao gộp: trước đây ba nhóm giọng cứng trong ba dropdown chọn tuần tự.
 * Thêm giọng clone vào khuôn đó là thêm tầng thứ tư. Gộp lại thì thêm giọng
 * chỉ là thêm một dòng trong bảng.
 *
 * Mọi thẻ đều nghe thử CÙNG MỘT CÂU — bấm lần lượt là so được ngay.
 */
export function ThuVienGiong() {
  const queryClient = useQueryClient();
  const [themMoi, setThemMoi] = useState(false);

  const { data: giong = [], isLoading } = useQuery({
    queryKey: ["giong-doc"],
    queryFn: api.giongDoc,
    //: Giọng đang dựng thì hỏi lại vài giây một lần cho tới khi xong. Đây
    //: KHÔNG phải polling tiến trình pipeline (thứ đã có WebSocket) mà là một
    //: việc ngắn, chỉ chạy khi đúng thẻ đó đang xử lý.
    refetchInterval: (q) =>
      (q.state.data ?? []).some((g) => g.trang_thai === "dang_xu_ly") ? 3000 : false,
  });

  const lam_moi = () => queryClient.invalidateQueries({ queryKey: ["giong-doc"] });

  const datMacDinh = useMutation({
    mutationFn: (id: string) => api.suaGiong(id, { mac_dinh: true }),
    onSuccess: lam_moi,
  });
  const xoa = useMutation({ mutationFn: api.xoaGiong, onSuccess: lam_moi });

  if (isLoading) return <p className="py-8 text-center text-[13px] text-muted">Đang tải…</p>;

  return (
    <div>
      {giong.map((g) => (
        <div key={g.id} className="mb-2 rounded-xl border border-border bg-panel p-3">
          <div className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                {g.mac_dinh && <span className="text-accent" title="giọng mặc định">●</span>}
                <span className="truncate text-[13.5px] font-medium">{g.ten}</span>
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11.5px] text-muted">
                <span>{NHAN_NGUON[g.nguon] ?? g.nguon}</span>
                <span className="opacity-40">·</span>
                <span className="font-mono">{g.nha_cung_cap}</span>
                {g.nha_cung_cap === "fish_mlx" && (
                  //: Fish Audio Research License — thương mại phải mua phép
                  //: riêng. Giấu đi là để người dùng vi phạm mà không biết.
                  <>
                    <span className="opacity-40">·</span>
                    <span className="text-warn">chạy tại máy · phi thương mại</span>
                  </>
                )}
              </div>
              {g.trang_thai === "dang_xu_ly" && (
                <div className="mt-1 text-[11px] text-run">Đang dựng giọng…</div>
              )}
              {g.trang_thai === "hong" && (
                <div className="mt-1 text-[11px] text-err">Dựng hỏng: {g.loi}</div>
              )}
              {g.canh_bao?.map((c) => (
                <div key={c.ma} className="mt-1 text-[11px] text-warn">
                  ⚠ {c.thong_diep}
                </div>
              ))}
            </div>

            <div className="flex shrink-0 items-center gap-1.5">
              {g.trang_thai === "san_sang" && (
                /* eslint-disable-next-line jsx-a11y/media-has-caption -- câu đọc thử, không có phụ đề */
                <audio controls preload="none" className="h-8 w-52" src={api.ngheThuUrl(g.id)} />
              )}
              {!g.mac_dinh && g.trang_thai === "san_sang" && (
                <button className="btn btn-sm" onClick={() => datMacDinh.mutate(g.id)}>
                  Đặt mặc định
                </button>
              )}
              {g.nguon !== "dung_san" && (
                <button
                  className="btn btn-sm border-err/35 text-err"
                  onClick={() => xoa.mutate(g.id)}
                >
                  Xoá
                </button>
              )}
            </div>
          </div>
        </div>
      ))}

      <button className="btn btn-primary btn-sm mt-2" onClick={() => setThemMoi(true)}>
        + Thêm giọng
      </button>

      {themMoi && (
        <ThemGiongModal
          onDong={() => setThemMoi(false)}
          onXong={() => {
            setThemMoi(false);
            lam_moi();
          }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Viết `ThemGiongModal.tsx`**

```tsx
"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";

const NGUON = [
  { ma: "tu_thu", nhan: "Tôi tự thu", goi_y: "Thu 10–15 giây bằng điện thoại, phòng yên, không nhạc nền." },
  { ma: "cat_tu_file", nhan: "Cắt từ file có sẵn", goi_y: "Chọn đoạn 10–15 giây trong file audio/video bạn có quyền dùng." },
  { ma: "thue_doc", nhan: "Thuê người đọc", goi_y: "Tải lên file người đọc gửi. Trả tiền một lần, dùng cho mọi video." },
  { ma: "tam_tu_may", nhan: "Giọng tạm dựng bằng máy", goi_y: "Chạy được ngay, nhưng là giọng máy — nên thay bằng giọng thật khi có điều kiện." },
];

interface Props {
  onDong: () => void;
  onXong: () => void;
}

/**
 * Thêm một giọng vào thư viện.
 *
 * KHÔNG hỏi người dùng phần chữ của đoạn mẫu: Whisper tự gõ ở bước sau, người
 * dùng chỉ việc sửa lại nếu lệch. Bắt gõ tay 15 giây lời nói là việc nản nhất
 * của cả luồng.
 */
export function ThemGiongModal({ onDong, onXong }: Props) {
  const [ten, setTen] = useState("");
  const [nguon, setNguon] = useState("tu_thu");
  const [file, setFile] = useState<File | null>(null);
  const [tu, setTu] = useState("");
  const [den, setDen] = useState("");

  const canFile = nguon !== "tam_tu_may";
  const coCat = nguon === "cat_tu_file";

  const them = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("ten", ten);
      form.append("nguon", nguon);
      form.append("nha_cung_cap", "fish_mlx");
      if (file) form.append("file", file);
      if (coCat && tu) form.append("cat_tu_giay", tu);
      if (coCat && den) form.append("cat_den_giay", den);
      return api.themGiong(form);
    },
    onSuccess: onXong,
  });

  const duocGui = ten.trim().length > 0 && (!canFile || file !== null) && !them.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-xl border border-border bg-panel p-4">
        <h3 className="mb-3 text-[15px] font-semibold">Thêm giọng</h3>

        <label className="mb-1 block text-[12px] text-muted">Tên giọng</label>
        <input
          className="mb-3 w-full rounded border border-border bg-bg px-2 py-1.5 text-[13px] outline-none focus:border-accent"
          value={ten}
          onChange={(e) => setTen(e.target.value)}
          placeholder="Giọng tôi"
        />

        <label className="mb-1 block text-[12px] text-muted">Nguồn giọng</label>
        <div className="mb-3 space-y-1.5">
          {NGUON.map((n) => (
            <label key={n.ma} className="flex cursor-pointer items-start gap-2 text-[12.5px]">
              <input
                type="radio"
                className="mt-1"
                checked={nguon === n.ma}
                onChange={() => setNguon(n.ma)}
              />
              <span>
                <span className="font-medium">{n.nhan}</span>
                <span className="block text-[11.5px] text-muted">{n.goi_y}</span>
              </span>
            </label>
          ))}
        </div>

        {canFile && (
          <>
            <label className="mb-1 block text-[12px] text-muted">File âm thanh hoặc video</label>
            <input
              type="file"
              accept="audio/*,video/*"
              className="mb-3 w-full text-[12px]"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </>
        )}

        {coCat && (
          <div className="mb-3 flex items-center gap-2 text-[12px]">
            <span className="text-muted">Lấy từ giây</span>
            <input
              className="w-20 rounded border border-border bg-bg px-2 py-1 outline-none focus:border-accent"
              value={tu}
              onChange={(e) => setTu(e.target.value)}
              placeholder="12.5"
            />
            <span className="text-muted">đến giây</span>
            <input
              className="w-20 rounded border border-border bg-bg px-2 py-1 outline-none focus:border-accent"
              value={den}
              onChange={(e) => setDen(e.target.value)}
              placeholder="26"
            />
          </div>
        )}

        <p className="mb-3 text-[11.5px] text-muted">
          Sau khi tải lên, hệ thống tự cắt còn tối đa 15 giây, cân âm lượng, rồi dùng Whisper gõ
          lại phần chữ cho bạn sửa. Chất lượng lồng tiếng không bao giờ vượt được chất lượng đoạn
          mẫu — nên mẫu thu người thật luôn hơn hẳn giọng máy.
        </p>

        {them.isError && (
          <div className="mb-2 text-[12px] text-err">
            {them.error instanceof ApiError ? them.error.message : "Không thêm được giọng"}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button className="btn btn-sm" onClick={onDong}>
            Huỷ
          </button>
          <button
            className="btn btn-primary btn-sm"
            disabled={!duocGui}
            onClick={() => them.mutate()}
          >
            {them.isPending ? "Đang gửi…" : "Thêm giọng"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Gắn mục vào trang Cấu hình**

Trong `apps/web/app/settings/page.tsx`:

Thêm cạnh hai hằng số đã có ở đầu file:

```tsx
const MUC_GIONG = "Giọng đọc";
```

Thêm import:

```tsx
import { ThuVienGiong } from "@/components/ThuVienGiong";
```

Thêm `<MucNav>` vào cột trái, ngay sau mục `MUC_KHOA_AI` (đọc file để bám đúng props `ten`/`dangXem`/`onChon` và cách tính `soO`/`coThayDoi`):

```tsx
            <MucNav
              ten={MUC_GIONG}
              dangXem={dangXem === MUC_GIONG}
              onChon={() => setDangXem(MUC_GIONG)}
            />
```

Thêm nhánh render ở cột phải, theo đúng khuôn nhánh `MUC_KHOA_AI`:

```tsx
            {dangXem === MUC_GIONG && (
              <>
                <div className="mb-3 flex items-center gap-3">
                  <h2 className="text-[15px] font-semibold">{MUC_GIONG}</h2>
                  <TheGiaiThich nhan="Giọng thế nào là tốt?">
                    Giọng clone chép lại đoạn mẫu bạn đưa — kể cả nhiễu, tiếng vọng và cái đều đều
                    của giọng máy. Nên mẫu <b className="text-fg">người thật thu</b> 10–15 giây
                    trong phòng yên luôn hơn hẳn mẫu dựng bằng máy. Đọc có lên xuống đúng kiểu bạn
                    muốn video nói, đừng đọc đều như đọc báo.
                  </TheGiaiThich>
                </div>
                <ThuVienGiong />
              </>
            )}
```

- [ ] **Step 6: Kiểm bằng mắt**

```bash
cd apps/api && uvicorn src.main:app --port 8000 &
cd apps/worker && celery -A src.celery_app worker -Q download,media,upload -l info &
cd apps/web && pnpm dev
```

Mở `http://localhost:3000/settings`, vào mục **Giọng đọc**. Kiểm sáu thứ:

1. Danh sách hiện các giọng dựng sẵn đã seed.
2. Bấm ▶ trên một giọng dựng sẵn → nghe được câu đọc thử.
3. "+ Thêm giọng" → chọn "Giọng tạm dựng bằng máy" → thêm được, thẻ hiện "Đang dựng giọng…" rồi tự chuyển sang nghe được (không phải bấm F5).
4. Thêm một giọng từ **file thu thật** của bạn → nghe thử thấy KHÁC HẲN giọng tạm.
5. Mẫu quá ngắn (dưới 7 giây) → thẻ hiện cảnh báo màu vàng, nhưng vẫn lưu được.
6. "Đặt mặc định" → chấm ● chuyển sang giọng đó, giọng cũ mất chấm.

- [ ] **Step 7: Commit**

```bash
cd apps/web && pnpm lint --fix
git add apps/web/components/ThuVienGiong.tsx apps/web/components/ThemGiongModal.tsx apps/web/app/settings/page.tsx apps/web/lib/api.ts apps/web/lib/types.gen.ts
git commit -m "feat(web): mục Giọng đọc trong Cấu hình — thư viện giọng gộp một chỗ"
```

---

### Task 9: Rút ô chọn giọng ở tab Chờ dịch từ ba ô xuống một

**Files:**
- Modify: `apps/web/components/PendingVideoRow.tsx`
- Modify: `apps/web/components/PendingTranslateTab.tsx`
- Modify: `apps/api/src/services/video_service.py` (`cac_giong_doc` đọc từ bảng)

**Interfaces:**
- Consumes: `api.giongDoc()` (Task 8), `giong.tham_so_goi` (Task 1)

- [ ] **Step 1: Cho `tts_options` đọc từ bảng thay vì hằng số cứng**

Trong `apps/api/src/services/video_service.py`, đổi `cac_giong_doc(db)` để đọc `giong_doc` thay vì ba danh sách cứng. Giữ nguyên hình dạng trả về để giao diện cũ không vỡ trong lúc chuyển:

```python
def cac_giong_doc(db: Session | None = None) -> list[dict[str, Any]]:
    """Giọng chọn được, ĐỌC TỪ BẢNG ``giong_doc``.

    Trước đây ba danh sách hardcode ở đây. Từ khi có thư viện giọng, bảng là
    nguồn sự thật duy nhất — thêm giọng chỉ là thêm một dòng, không phải sửa
    mã rồi triển khai lại.

    Giữ nguyên hình dạng cũ (nhóm theo nhà cung cấp) để giao diện đang chạy
    không vỡ trong lúc chuyển sang ô chọn một tầng.
    """
    from . import giong_doc_service

    if db is None:
        return []

    theo_ben: dict[str, dict[str, Any]] = {}
    for g in giong_doc_service.danh_sach(db):
        if g.trang_thai != TrangThaiGiong.SAN_SANG.value:
            continue
        nhom = theo_ben.setdefault(
            g.nha_cung_cap,
            {"provider": g.nha_cung_cap, "ghi_chu": _GHI_CHU_BEN.get(g.nha_cung_cap, ""),
             "models": [], "giong": [], "mac_dinh": False, "giong_mac_dinh": ""},
        )
        nhom["giong"].append({"ma": g.ma_giong or str(g.id), "ten": g.ten, "gioi_tinh": ""})
        if g.model and g.model not in nhom["models"]:
            nhom["models"].append(g.model)
        if g.mac_dinh:
            nhom["mac_dinh"] = True
            nhom["giong_mac_dinh"] = g.ma_giong or str(g.id)

    return list(theo_ben.values())
```

Thêm hằng `_GHI_CHU_BEN` giữ nguyên các câu đánh đổi đã có (`edge` miễn phí; `gemini` tốn hạn mức mỗi câu; `openrouter` trả tiền theo lượt; `fish_mlx` chạy tại máy, phi thương mại).

- [ ] **Step 2: Chạy test cũ cho chắc không vỡ**

Run: `cd apps/api && pytest -q`
Expected: PASS. Test nào khoá danh sách giọng cứng thì sửa cho khớp nguồn mới, và ghi rõ trong docstring vì sao đổi.

- [ ] **Step 3: Đổi ô chọn ở dòng chờ dịch thành MỘT ô**

Trong `apps/web/components/PendingVideoRow.tsx`, thay ba ô (nhà cung cấp → model → giọng) bằng một ô đọc `api.giongDoc()`:

```tsx
  const { data: giong = [] } = useQuery({
    queryKey: ["giong-doc"],
    queryFn: api.giongDoc,
    staleTime: 5 * 60 * 1000,
  });
  const sanSang = giong.filter((g) => g.trang_thai === "san_sang");
  const [giongId, setGiongId] = useState("");
  const dangChon = sanSang.find((g) => g.id === giongId) ?? sanSang.find((g) => g.mac_dinh);
```

```tsx
        <select
          className="rounded border border-border bg-bg px-2 py-1 text-[12px]"
          value={dangChon?.id ?? ""}
          onChange={(e) => setGiongId(e.target.value)}
          aria-label="Giọng đọc"
        >
          {sanSang.map((g) => (
            <option key={g.id} value={g.id}>
              {g.ten} — {g.nha_cung_cap}
            </option>
          ))}
        </select>
```

Khi bấm Dịch, gửi `giong_doc_id` thay vì ba trường rời:

```tsx
          onTranslate(video.id, {
            llmProvider,
            llmModel,
            xoaChuCung,
            giongDocId: dangChon?.id ?? "",
          })
```

- [ ] **Step 4: Cho backend nhận `giong_doc_id`**

Trong `apps/api/src/schemas/video.py`, thêm vào `TranslateRequest`:

```python
    #: Trỏ vào một dòng ``giong_doc``. Thay cho bộ ba
    #: ``tts_provider``/``giong_doc``/``tts_model`` — một mã là đủ, service tự
    #: tra ra ba thứ kia bằng ``giong.tham_so_goi``.
    giong_doc_id: uuid.UUID | None = None
```

Trong service xử lý `translate`, khi có `giong_doc_id` thì tra bảng rồi gọi `tham_so_goi(...)` (Task 1) để ghi đủ tham số vào `process_config`. Giữ đường cũ (ba trường rời) chạy song song cho video đã xếp hàng từ trước.

- [ ] **Step 5: Kiểm bằng mắt**

Mở tab Chờ dịch: chỉ còn MỘT ô chọn giọng, liệt kê mọi giọng sẵn sàng kèm tên nhà cung cấp. Chọn một giọng rồi bấm Dịch, kiểm `process_config` của video trong DB có `giong_doc_id` và `tts_provider` đúng.

```bash
docker exec reupstudio-postgres-1 psql -U reup -d reup -t -A -c \
  "SELECT process_config::text FROM videos ORDER BY updated_at DESC LIMIT 1"
```

- [ ] **Step 6: Chạy toàn bộ test rồi commit**

```bash
cd apps/api && pytest -q && cd ../worker && pytest -q && cd ../web && pnpm test && pnpm lint
ruff format . && ruff check --fix .
git add -A
git commit -m "feat(web): ô chọn giọng rút từ ba tầng xuống một, đọc từ thư viện giọng"
```

---

## Nghiệm thu kế hoạch C

- [ ] `cd apps/api && pytest -q` — xanh
- [ ] `cd apps/worker && pytest -q` — xanh
- [ ] `cd apps/web && pnpm test && pnpm lint` — xanh
- [ ] Cấu hình → Giọng đọc: thấy giọng dựng sẵn, nghe thử được
- [ ] Thêm được giọng từ file thu thật, nghe thử thấy khác giọng tạm
- [ ] Mẫu quá ngắn/quá nhỏ → hiện cảnh báo nhưng VẪN lưu được
- [ ] Xoá giọng đang mặc định → mặc định tự chuyển sang giọng khác, không để rỗng
- [ ] Không xoá được giọng dựng sẵn
- [ ] Tab Chờ dịch chỉ còn MỘT ô chọn giọng
- [ ] Điểm nối cho Kế hoạch B rõ ràng: `codes.npz` chưa dùng tới, `tham_so_goi` đã trả `giong_doc_id` cho `fish_mlx`
