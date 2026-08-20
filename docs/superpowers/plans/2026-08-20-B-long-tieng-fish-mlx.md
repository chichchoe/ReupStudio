# Kế hoạch B — Lồng tiếng bằng Fish Speech S2-Pro chạy tại máy

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm nhà cung cấp giọng `fish_mlx` chạy Fish Speech S2-Pro tại máy qua MLX, nhân bản giọng từ thư viện giọng, giữ Edge làm đường lui tự động và nói rõ khi phải dùng tới nó.

**Architecture:** Model chạy trong **venv riêng python 3.13**, worker gọi qua **subprocess theo lô** (không phải server HTTP — nạp model chỉ mất 1 giây nên server thường trú là thừa). `tts/fish_mlx.py` triển khai đúng `TTSProvider` sẵn có nên `pipeline/` và `tasks/` gần như không phải đổi.

**Tech Stack:** MLX (Apple Silicon), `mlx-speech`, Fish S2-Pro int8, Celery, ffmpeg.

**Spec:** `docs/superpowers/specs/2026-08-20-duyet-ban-dich-va-long-tieng-design.md` (Phần B)

## Kế hoạch này PHỤ THUỘC Kế hoạch C — phải làm sau

Giọng đến từ **đoạn mẫu**, không phải từ tên giọng. Đoạn mẫu do thư viện giọng (Kế hoạch C) quản: `media/giong/<id>/mau.wav` + `mau.txt` + `codes.npz`. Không có C thì B không có gì để đọc.

Điểm nối C đã chuẩn bị sẵn:
- `reup_core.paths.giong_mau_wav/giong_mau_txt/giong_codes(giong_id)`
- `reup_core.giong.tham_so_goi(...)` ghi `giong_doc_id` vào `video.process_config` cho `fish_mlx` (không có `ma_giong`, không có `model`)
- `giong_doc.nha_cung_cap == "fish_mlx"` đã hiện được trên giao diện kèm nhãn giấy phép

## Số liệu đã ĐO THẬT trên máy này (Mac mini M4 Pro 24GB, 2026-08-20)

Cùng 20 câu tiếng Việt, cùng một giọng mẫu:

| | PyTorch + MPS (bf16) | **MLX int8** |
|---|---|---|
| token/giây | 0,64 | **10,6** |
| RTF | ~33–46 | **1,98** |
| nạp model | hơn 4 phút | **1 giây** |
| RAM đỉnh | swap 12,3 GB, thrash | **3,9 GB** |
| kết quả | dừng giữa chừng | 20/20 câu |

**Vì sao PyTorch hỏng:** fish-speech mặc định `torch.bfloat16`, mà MPS hỗ trợ bfloat16 rất kém (pytorch#141864); cộng với `PYTORCH_ENABLE_MPS_FALLBACK=1`, op không hỗ trợ rơi về CPU **âm thầm** — mỗi token đi GPU→CPU→GPU. Đối chiếu: PR #461 của chính fish-speech đo 3,28 token/giây trên **MacBook Air M1** — máy yếu hơn nhiều mà vẫn nhanh gấp 5 lần đường PyTorch trên M4 Pro. Đó là hỏng, không phải chậm.

**Đừng đo lại, đừng thử PyTorch.** Đã thử rồi.

Quy ra việc thật: clip 60 giây lời thoại mất **2 phút**; nguồn 34 phút (~20 phút lời thoại) mất **40 phút**.

## Global Constraints

- Python 3.12 cho worker; **venv model dùng python 3.13** (`mlx-speech` yêu cầu `>=3.13`; cài bằng 3.12 báo "all versions of mlx-speech cannot be used").
- **CẤM gọi model AI trong tiến trình worker chính** — phải subprocess riêng, **luôn có timeout**. venv worker KHÔNG được có `torch` hay `mlx`.
- Không `shell=True`. Dựng lệnh dạng list. Ghi file tạm rồi `rename`.
- Mọi đường dẫn qua `packages/reup_core/src/reup_core/paths.py`.
- Nhà cung cấp giọng mới chỉ được đụng thư mục `apps/worker/src/tts/`, không sửa `pipeline/` hay `tasks/` ngoài chỗ nối tối thiểu.
- Không `print`; dùng `structlog` qua `reup_core.logging.get_logger`. Cấm `except: pass`.
- Exception có nghĩa, kế thừa `ReupError`. Magic number phải đặt tên.
- Type hint bắt buộc cho hàm public. `pathlib.Path`, không dùng chuỗi đường dẫn.
- **Model 4,6 GB KHÔNG được commit** — thêm vào `.gitignore`.
- Format trước khi commit: `ruff format . && ruff check --fix .`
- Một task = một commit.

## API `mlx-speech` đã kiểm chứng bằng đọc mã nguồn — dùng, đừng dò lại

```python
# Đường cấp thấp — DÙNG CÁI NÀY, vì nó mã hoá đoạn mẫu MỘT lần rồi tái dùng
from mlx_speech.generation.fish_s2_pro import FishS2ProRuntime
runtime = FishS2ProRuntime.from_dir(model_dir)
ref = runtime.encode_reference(reference_audio, reference_text)   # -> PreparedReference
out = runtime.synthesize(text, max_new_tokens=256, reference_audio=ref)
# out: FishS2ProOutput(waveform: mx.array, sample_rate: int, generated_tokens: int)
```

- Sample rate **44100**. Codec **21 Hz** → 21 token = 1 giây tiếng.
- `TTSModel` cấp cao (`mlx_speech.tts.load`) CHỈ có `generate`, **không có** `prepare_reference` — nên phải dùng đường cấp thấp để không mã hoá lại đoạn mẫu ở mỗi câu.
- Tham số sinh (`_DEFAULT_TEMPERATURE=0.8`, `_DEFAULT_TOP_P=0.8`, `_DEFAULT_TOP_K=30`) là **hằng số module, không mở ra ngoài API** — đừng thiết kế nút chỉnh chúng. Chất lượng đến từ đoạn mẫu, không từ tham số.

---

### Task 1: Dựng môi trường model và lệnh kiểm tra sức khoẻ

**Files:**
- Create: `services/fish-mlx/README.md`
- Create: `scripts/cai-fish-mlx.sh`
- Modify: `packages/reup_core/src/reup_core/paths.py`
- Modify: `.gitignore`
- Modify: `Makefile`
- Test: `apps/worker/tests/test_fish_mlx_moi_truong.py`

**Interfaces:**
- Produces:
  - `paths.fish_mlx_dir() -> Path` — gốc `services/fish-mlx/`
  - `paths.fish_mlx_python() -> Path` — `services/fish-mlx/.venv/bin/python`
  - `paths.fish_mlx_model() -> Path` — thư mục trọng số int8
  - `tts.fish_mlx.kiem_moi_truong() -> tuple[bool, str]` — (sẵn sàng, lý do nếu chưa)

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/worker/tests/test_fish_mlx_moi_truong.py`:

```python
"""Kiểm môi trường Fish MLX TRƯỚC khi lồng tiếng, không phải giữa chừng.

Thiếu venv hoặc thiếu model mà cứ chạy thì lỗi lộ ra ở câu đầu tiên của một
video 672 câu, sau khi người dùng đã chờ qua cả bước dịch. Kiểm trước và báo
rõ thiếu gì, kèm lệnh sửa.
"""

from __future__ import annotations

from src.tts.fish_mlx import kiem_moi_truong


def test_thieu_python_thi_bao_ro_va_kem_lenh_sua(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("src.tts.fish_mlx.fish_mlx_python", lambda: tmp_path / "khong-co")
    monkeypatch.setattr("src.tts.fish_mlx.fish_mlx_model", lambda: tmp_path)
    ok, ly_do = kiem_moi_truong()
    assert ok is False
    assert "chưa dựng" in ly_do
    assert "cai-fish-mlx.sh" in ly_do


def test_thieu_model_thi_bao_ro(monkeypatch, tmp_path) -> None:
    py = tmp_path / "python"
    py.write_text("")
    monkeypatch.setattr("src.tts.fish_mlx.fish_mlx_python", lambda: py)
    monkeypatch.setattr("src.tts.fish_mlx.fish_mlx_model", lambda: tmp_path / "khong-co-model")
    ok, ly_do = kiem_moi_truong()
    assert ok is False
    assert "trọng số" in ly_do


def test_du_ca_hai_thi_san_sang(monkeypatch, tmp_path) -> None:
    py = tmp_path / "python"
    py.write_text("")
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.safetensors").write_bytes(b"x")
    monkeypatch.setattr("src.tts.fish_mlx.fish_mlx_python", lambda: py)
    monkeypatch.setattr("src.tts.fish_mlx.fish_mlx_model", lambda: model)
    ok, ly_do = kiem_moi_truong()
    assert ok is True and ly_do == ""


def test_thu_muc_model_RONG_tinh_la_thieu(monkeypatch, tmp_path) -> None:
    #: Tải dở rồi ngắt để lại thư mục rỗng. Nhận là hợp lệ thì lỗi lộ ra lúc
    #: nạp model, giữa chừng một video.
    py = tmp_path / "python"
    py.write_text("")
    model = tmp_path / "model"
    model.mkdir()
    monkeypatch.setattr("src.tts.fish_mlx.fish_mlx_python", lambda: py)
    monkeypatch.setattr("src.tts.fish_mlx.fish_mlx_model", lambda: model)
    ok, ly_do = kiem_moi_truong()
    assert ok is False and "trọng số" in ly_do
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/worker && pytest tests/test_fish_mlx_moi_truong.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.tts.fish_mlx'`

- [ ] **Step 3: Thêm đường dẫn vào `paths.py`**

```python
def fish_mlx_dir() -> Path:
    """Gốc môi trường Fish Speech MLX — venv riêng và trọng số model.

    Nằm NGOÀI ``media_root``: đây không phải dữ liệu người dùng mà là phần
    cài đặt của máy, không nên đi theo khi sao lưu media.
    """
    return _goc_repo() / "services" / "fish-mlx"


def fish_mlx_python() -> Path:
    """Python của venv model. venv worker KHÔNG có mlx và phải giữ nguyên vậy."""
    return fish_mlx_dir() / ".venv" / "bin" / "python"


def fish_mlx_model() -> Path:
    """Thư mục trọng số int8 (khoảng 4,6 GB). Không commit."""
    return fish_mlx_dir() / "s2-pro-8bit"
```

- [ ] **Step 4: Viết `kiem_moi_truong` trong nhà cung cấp mới**

Tạo `apps/worker/src/tts/fish_mlx.py` (phần đầu, phần đọc thêm ở Task 3):

```python
"""Giọng đọc bằng Fish Speech S2-Pro chạy TẠI MÁY qua MLX.

Vì sao MLX chứ không PyTorch: đo ngày 2026-08-20 trên Mac mini M4 Pro —
PyTorch+MPS cho 0,64 token/giây (RTF ~33–46), MLX int8 cho 10,6 token/giây
(RTF 1,98). Nhanh hơn 17 lần. Nguyên nhân: fish-speech mặc định bfloat16 mà
MPS hỗ trợ bf16 rất kém, và cờ MPS fallback đẩy op về CPU âm thầm.

Vì sao subprocess chứ không server HTTP: nạp model chỉ mất 1 giây, server
thường trú chỉ thêm việc quản cổng và vòng đời mà không được gì. Cũng đúng
luật CLAUDE.md: không gọi model AI trong tiến trình worker chính.

Giấy phép: Fish Audio Research License — nghiên cứu và phi thương mại miễn
phí, THƯƠNG MẠI PHẢI MUA PHÉP RIÊNG (business@fish.audio). Giao diện phải ghi
rõ nhãn này cạnh lựa chọn.
"""

from __future__ import annotations

from pathlib import Path

from reup_core.logging import get_logger
from reup_core.paths import fish_mlx_model, fish_mlx_python

from ..errors import ReupError
from .base import GiongDoc

log = get_logger(__name__)

#: Codec S2 chạy 21 Hz — 21 token là một giây tiếng. Dùng để ước lượng timeout.
TOKEN_MOI_GIAY_TIENG = 21

#: Đo được RTF 1,98. Lấy hệ số 6 làm trần cho an toàn: máy đang bận, câu dài
#: bất thường, hoặc model đi lạc vào vòng lặp đều nằm trong khoảng này.
HE_SO_TIMEOUT = 6.0

#: Sàn timeout cho lô nhỏ — nạp model, mã hoá đoạn mẫu và khởi động python
#: đã tốn chừng này rồi.
TIMEOUT_TOI_THIEU_GIAY = 120.0


def kiem_moi_truong() -> tuple[bool, str]:
    """``(sẵn sàng, lý do nếu chưa)``. Kiểm TRƯỚC khi lồng tiếng.

    Thiếu venv hay thiếu model mà cứ chạy thì lỗi lộ ra ở câu đầu của một video
    672 câu, sau khi người dùng đã chờ qua cả bước dịch. Báo trước, kèm lệnh sửa.
    """
    if not fish_mlx_python().exists():
        return (
            False,
            "Môi trường Fish MLX chưa dựng. Chạy: bash scripts/cai-fish-mlx.sh",
        )

    model = fish_mlx_model()
    if not model.is_dir() or not any(model.glob("*.safetensors")):
        return (
            False,
            "Chưa có trọng số model Fish S2-Pro (khoảng 4,6 GB). "
            "Chạy: bash scripts/cai-fish-mlx.sh",
        )

    return (True, "")
```

- [ ] **Step 5: Chạy test cho chắc là qua**

Run: `cd apps/worker && pytest tests/test_fish_mlx_moi_truong.py -v`
Expected: PASS, 4 passed

- [ ] **Step 6: Viết script cài đặt**

Tạo `scripts/cai-fish-mlx.sh`:

```bash
#!/usr/bin/env bash
# Dựng môi trường Fish Speech S2-Pro chạy tại máy (MLX, Apple Silicon).
#
# Tách hẳn khỏi venv worker: worker KHÔNG được có mlx/torch. mlx-speech đòi
# python >= 3.13, còn worker chạy 3.12.
#
# Chạy lại được nhiều lần — có sẵn thì bỏ qua, không tải lại 4,6 GB.
set -euo pipefail

GOC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DICH="$GOC/services/fish-mlx"
MODEL="$DICH/s2-pro-8bit"
REPO="appautomaton/fishaudio-s2-pro-8bit-mlx"

command -v uv >/dev/null || { echo "Thiếu uv. Cài: brew install uv"; exit 1; }

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Fish MLX chỉ chạy trên Apple Silicon. Máy này: $(uname -m)"; exit 1
fi

mkdir -p "$DICH"

if [[ ! -x "$DICH/.venv/bin/python" ]]; then
  echo "==> Dựng venv python 3.13"
  uv venv --python 3.13 "$DICH/.venv"
  uv pip install --python "$DICH/.venv/bin/python" mlx-speech
else
  echo "==> venv đã có, bỏ qua"
fi

if ! compgen -G "$MODEL/*.safetensors" >/dev/null; then
  echo "==> Tải trọng số int8 (~4,6 GB), lần đầu mất vài phút"
  "$DICH/.venv/bin/python" -m huggingface_hub.commands.huggingface_cli \
    download "$REPO" --local-dir "$MODEL" \
    || uv tool run --from huggingface_hub hf download "$REPO" --local-dir "$MODEL"
else
  echo "==> Model đã có, bỏ qua"
fi

echo "==> Kiểm tra"
"$DICH/.venv/bin/python" - <<'PY'
import mlx.core as mx
from mlx_speech.generation.fish_s2_pro import FishS2ProRuntime  # noqa: F401
print("MLX chạy trên:", mx.default_device())
print("mlx-speech nạp được")
PY

echo
echo "Xong. Model: $MODEL"
echo "LƯU Ý GIẤY PHÉP: Fish Audio Research License — phi thương mại."
echo "Dùng cho kênh có kiếm tiền phải mua phép riêng: business@fish.audio"
```

```bash
chmod +x scripts/cai-fish-mlx.sh
```

- [ ] **Step 7: Bỏ qua model trong git và thêm mục Makefile**

Thêm vào `.gitignore`:

```
# Môi trường model Fish Speech chạy tại máy — venv và 4,6 GB trọng số
services/fish-mlx/.venv/
services/fish-mlx/s2-pro-8bit/
```

Thêm vào `Makefile` (bám đúng khuôn các mục đã có):

```makefile
cai-fish:  ## Dựng môi trường Fish Speech MLX chạy tại máy (~4,6 GB)
	bash scripts/cai-fish-mlx.sh
```

Tạo `services/fish-mlx/README.md`:

```markdown
# Fish Speech S2-Pro chạy tại máy (MLX)

Dựng bằng `make cai-fish` hoặc `bash scripts/cai-fish-mlx.sh`.

Thư mục này chứa venv riêng (python 3.13) và trọng số int8 (~4,6 GB). **Cả hai
đều không commit** — xem `.gitignore`.

Tách khỏi venv worker vì worker chạy python 3.12 và KHÔNG được có `mlx`/`torch`
(luật CLAUDE.md: không gọi model AI trong tiến trình worker chính).

## Số đo trên Mac mini M4 Pro 24GB (2026-08-20)

RTF 1,98 · 10,6 token/giây · nạp model 1 giây · RAM đỉnh 3,9 GB.
Clip 60 giây lời thoại mất ~2 phút.

Đừng đổi sang PyTorch+MPS: đã thử, chậm hơn 17 lần (0,64 token/giây) vì MPS
hỗ trợ bfloat16 rất kém.

## Giấy phép

Fish Audio Research License. Nghiên cứu và phi thương mại: miễn phí.
**Thương mại phải mua phép riêng** — business@fish.audio.
```

- [ ] **Step 8: Chạy cài thật rồi commit**

```bash
bash scripts/cai-fish-mlx.sh
```

Expected: in ra `MLX chạy trên: Device(gpu, 0)` và `mlx-speech nạp được`.

```bash
cd apps/worker && ruff format . && ruff check --fix .
git add scripts/cai-fish-mlx.sh services/fish-mlx/README.md .gitignore Makefile packages/reup_core/src/reup_core/paths.py apps/worker/src/tts/fish_mlx.py apps/worker/tests/test_fish_mlx_moi_truong.py
git commit -m "feat(tts): dựng môi trường Fish Speech MLX chạy tại máy"
```

---

### Task 2: Giao thức worker ↔ subprocess

Tách phần DỰNG YÊU CẦU và ĐỌC KẾT QUẢ ra khỏi phần chạy subprocess, để test được mà không cần model.

**Files:**
- Create: `apps/worker/src/tts/fish_giao_thuc.py`
- Test: `apps/worker/tests/test_fish_giao_thuc.py`

**Interfaces:**
- Produces:
  - `YeuCau(mau_wav: str, mau_text: str, cau: list[dict], thu_muc_ra: str, model_dir: str)` — frozen dataclass, `.to_json() -> str`
  - `KetQua(xong: dict[int, str], hong: dict[int, str], token: int, giay: float)` — frozen dataclass
  - `doc_ket_qua(stdout: str) -> KetQua`
  - `uoc_timeout(cau: list[dict]) -> float`

Giao thức: worker ghi **một dòng JSON** vào stdin của subprocess; subprocess ghi **một dòng JSON** ra stdout khi xong. Mọi thứ khác (log, cảnh báo của thư viện) đi stderr.

Vì sao một dòng JSON chứ không truyền qua tham số dòng lệnh: một lô có tới 672 câu, vượt xa giới hạn độ dài dòng lệnh.

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/worker/tests/test_fish_giao_thuc.py`:

```python
"""Giao thức giữa worker và tiến trình model.

Tách khỏi phần chạy thật để test được mà không cần 4,6 GB trọng số. Đây cũng
là chỗ dễ hỏng âm thầm nhất: subprocess in thêm một dòng cảnh báo là worker
đọc nhầm, và biểu hiện ra ngoài chỉ là "câu nào cũng hỏng".
"""

from __future__ import annotations

import json

import pytest

from src.tts.fish_giao_thuc import KetQua, YeuCau, doc_ket_qua, uoc_timeout


class TestYeuCau:
    def test_json_mot_dong_khong_xuong_dong(self) -> None:
        #: Subprocess đọc đúng MỘT dòng từ stdin. Có "\n" ở giữa là nó đọc hụt.
        y = YeuCau(
            mau_wav="/m/mau.wav",
            mau_text="Xin chào\ncác bạn",
            cau=[{"i": 0, "text": "Câu\nmột"}],
            thu_muc_ra="/m/giong",
            model_dir="/m/model",
        )
        assert "\n" not in y.to_json()

    def test_giu_nguyen_dau_tieng_viet(self) -> None:
        y = YeuCau("/a", "Sườn hầm", [{"i": 0, "text": "Đậy nắp nồi"}], "/b", "/c")
        assert json.loads(y.to_json())["cau"][0]["text"] == "Đậy nắp nồi"


class TestDocKetQua:
    def test_doc_dong_json_cuoi_cung(self) -> None:
        #: mlx và huggingface in cảnh báo ra bất cứ đâu. Lấy dòng JSON HỢP LỆ
        #: cuối cùng, không lấy dòng cuối cùng.
        out = (
            "Fetching 3 files: 100%|##########| 3/3\n"
            "some warning\n"
            '{"xong": {"0": "/m/cau_00000.wav"}, "hong": {}, "token": 42, "giay": 3.9}\n'
        )
        kq = doc_ket_qua(out)
        assert kq.xong == {0: "/m/cau_00000.wav"}
        assert kq.token == 42 and kq.giay == 3.9

    def test_cau_hong_giu_lai_ly_do(self) -> None:
        out = '{"xong": {}, "hong": {"3": "hết bộ nhớ"}, "token": 0, "giay": 1.0}'
        assert doc_ket_qua(out).hong == {3: "hết bộ nhớ"}

    def test_khong_co_json_nao_thi_bao_ro(self) -> None:
        with pytest.raises(Exception, match="không trả về kết quả"):
            doc_ket_qua("Traceback (most recent call last):\n  ImportError: mlx\n")

    def test_stdout_rong(self) -> None:
        with pytest.raises(Exception, match="không trả về kết quả"):
            doc_ket_qua("")


class TestUocTimeout:
    def test_lo_nho_van_du_thoi_gian_nap_model(self) -> None:
        #: Nạp model 1s + mã hoá mẫu + khởi động python. Tính sát quá thì lô
        #: một câu bị giết oan.
        assert uoc_timeout([{"i": 0, "text": "Ngắn"}]) >= 120.0

    def test_lo_lon_thi_timeout_tang_theo(self) -> None:
        nho = uoc_timeout([{"i": i, "text": "câu ngắn"} for i in range(10)])
        lon = uoc_timeout([{"i": i, "text": "câu ngắn"} for i in range(600)])
        assert lon > nho * 5

    def test_lo_rong(self) -> None:
        assert uoc_timeout([]) >= 120.0
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/worker && pytest tests/test_fish_giao_thuc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.tts.fish_giao_thuc'`

- [ ] **Step 3: Viết giao thức**

Tạo `apps/worker/src/tts/fish_giao_thuc.py`:

```python
"""Giao thức giữa worker và tiến trình model Fish MLX.

Một dòng JSON vào stdin, một dòng JSON ra stdout. Log và cảnh báo của thư
viện đi stderr, không lẫn vào kết quả.

Vì sao không truyền qua tham số dòng lệnh: một lô có tới 672 câu, vượt xa
giới hạn độ dài dòng lệnh.

Hàm THUẦN — không chạy subprocess, không chạm file. Test được mà không cần
4,6 GB trọng số.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..errors import ReupError

#: Codec S2 chạy 21 Hz. Ước 4 chữ tiếng Việt ≈ 1 giây tiếng (đo trên 20 câu
#: thật: 20 câu, 35,5 giây tiếng, trung bình 1,8 giây/câu).
CHU_MOI_GIAY_TIENG = 4.0

#: RTF đo được 1,98. Lấy 6 làm trần an toàn.
HE_SO_TIMEOUT = 6.0

TIMEOUT_TOI_THIEU_GIAY = 120.0


@dataclass(frozen=True)
class YeuCau:
    """Một lô câu gửi cho tiến trình model."""

    mau_wav: str
    mau_text: str
    cau: list[dict]
    thu_muc_ra: str
    model_dir: str

    def to_json(self) -> str:
        """Một dòng JSON, không xuống dòng — subprocess đọc đúng MỘT dòng."""
        return json.dumps(
            {
                "mau_wav": self.mau_wav,
                "mau_text": " ".join(self.mau_text.split()),
                "cau": [{"i": int(c["i"]), "text": " ".join(str(c["text"]).split())} for c in self.cau],
                "thu_muc_ra": self.thu_muc_ra,
                "model_dir": self.model_dir,
            },
            ensure_ascii=False,
        )


@dataclass(frozen=True)
class KetQua:
    """Kết quả một lô. ``xong``/``hong`` khoá theo chỉ số câu."""

    xong: dict[int, str]
    hong: dict[int, str]
    token: int
    giay: float


def doc_ket_qua(stdout: str) -> KetQua:
    """Đọc dòng JSON HỢP LỆ CUỐI CÙNG trong stdout.

    Không lấy dòng cuối cùng: mlx và huggingface in tiến trình tải và cảnh báo
    ra bất cứ đâu. Lấy nhầm thì biểu hiện ra ngoài chỉ là "câu nào cũng hỏng",
    không ai đoán được nguyên nhân.
    """
    for dong in reversed(stdout.splitlines()):
        dong = dong.strip()
        if not dong.startswith("{"):
            continue
        try:
            d = json.loads(dong)
        except json.JSONDecodeError:
            continue
        return KetQua(
            xong={int(k): str(v) for k, v in d.get("xong", {}).items()},
            hong={int(k): str(v) for k, v in d.get("hong", {}).items()},
            token=int(d.get("token", 0)),
            giay=float(d.get("giay", 0.0)),
        )

    raise ReupError(
        f"Tiến trình Fish MLX không trả về kết quả. Đuôi stdout: {stdout[-500:]!r}"
    )


def uoc_timeout(cau: list[dict]) -> float:
    """Trần thời gian cho một lô, ước từ tổng số chữ.

    Không đặt timeout cố định: lô một câu và lô 672 câu chênh nhau hàng trăm
    lần. Cố định theo lô lớn thì lô nhỏ treo mãi khi model đi lạc; cố định
    theo lô nhỏ thì lô lớn bị giết oan.
    """
    tong_chu = sum(len(str(c.get("text", "")).split()) for c in cau)
    giay_tieng = tong_chu / CHU_MOI_GIAY_TIENG
    return max(TIMEOUT_TOI_THIEU_GIAY, giay_tieng * HE_SO_TIMEOUT + TIMEOUT_TOI_THIEU_GIAY)
```

- [ ] **Step 4: Chạy test cho chắc là qua**

Run: `cd apps/worker && pytest tests/test_fish_giao_thuc.py -v`
Expected: PASS, 9 passed

- [ ] **Step 5: Commit**

```bash
cd apps/worker && ruff format . && ruff check --fix .
git add apps/worker/src/tts/fish_giao_thuc.py apps/worker/tests/test_fish_giao_thuc.py
git commit -m "feat(tts): giao thức JSON giữa worker và tiến trình Fish MLX"
```

---

### Task 3: Script chạy trong venv model

**Files:**
- Create: `services/fish-mlx/doc_lo.py`

**Interfaces:**
- Consumes: JSON một dòng từ stdin theo `YeuCau` (Task 2)
- Produces: JSON một dòng ra stdout theo `KetQua` (Task 2); file `cau_NNNNN.wav` trong `thu_muc_ra`

File này chạy bằng **python 3.13 của venv model**, KHÔNG import gì từ `apps/worker` — hai venv tách biệt hoàn toàn.

- [ ] **Step 1: Viết script**

Tạo `services/fish-mlx/doc_lo.py`:

```python
"""Đọc một lô câu bằng Fish S2-Pro (MLX). Chạy bằng python của venv này.

Nhận một dòng JSON ở stdin, ghi một dòng JSON ở stdout khi xong. Mọi thứ khác
đi stderr — worker đọc stdout và sẽ nhầm nếu log lẫn vào.

KHÔNG import gì từ apps/worker: hai venv tách biệt (worker 3.12 không có mlx,
venv này 3.13 có mlx nhưng không có code dự án).

Mã hoá đoạn mẫu MỘT LẦN rồi tái dùng cho cả lô. Benchmark ngày 2026-08-20 mã
hoá lại ở từng câu và vì thế đo ra RTF bi quan hơn thực tế.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from mlx_speech.generation.fish_s2_pro import FishS2ProRuntime

#: Trần token mỗi câu. 256 token ≈ 12 giây tiếng ở 21 Hz — dài hơn mọi câu
#: phụ đề hợp lệ. Đây cũng là phanh khi model đi lạc vào vòng lặp.
TOKEN_TOI_DA_MOI_CAU = 256


def main() -> None:
    yeu_cau = json.loads(sys.stdin.readline())
    thu_muc = Path(yeu_cau["thu_muc_ra"])
    thu_muc.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    runtime = FishS2ProRuntime.from_dir(yeu_cau["model_dir"])
    #: Mã hoá đoạn mẫu MỘT lần cho cả lô — đây là điểm khác chính so với
    #: đường cấp cao ``TTSModel.generate`` (không có prepare_reference).
    ref = runtime.encode_reference(yeu_cau["mau_wav"], yeu_cau["mau_text"])
    print(f"nạp model + mã hoá mẫu: {time.perf_counter() - t0:.1f}s", file=sys.stderr)

    xong: dict[str, str] = {}
    hong: dict[str, str] = {}
    tong_token = 0

    for cau in yeu_cau["cau"]:
        i = int(cau["i"])
        chu = cau["text"].strip()
        dst = thu_muc / f"cau_{i:05d}.wav"

        if not chu:
            #: Câu chỉ có dấu câu. Bỏ qua chứ không tính là hỏng — bước xếp
            #: lịch tự bỏ file 0 giây.
            continue

        try:
            out = runtime.synthesize(chu, max_new_tokens=TOKEN_TOI_DA_MOI_CAU, reference_audio=ref)
            song = np.asarray(out.waveform, dtype=np.float32).squeeze()
            if song.size == 0:
                hong[str(i)] = "model trả về 0 mẫu"
                continue
            #: Ghi file tạm rồi đổi tên — crash giữa chừng không để lại file
            #: dở dang mà bước sau tưởng là hợp lệ.
            tam = dst.with_name(f".{dst.stem}.tmp{dst.suffix}")
            sf.write(tam, song, out.sample_rate)
            tam.rename(dst)
            xong[str(i)] = str(dst)
            tong_token += int(out.generated_tokens)
        except Exception as exc:  # noqa: BLE001 - câu hỏng không được giết cả lô
            hong[str(i)] = f"{type(exc).__name__}: {exc}"[:200]
            print(f"câu {i} hỏng: {exc}", file=sys.stderr)

    print(
        json.dumps(
            {"xong": xong, "hong": hong, "token": tong_token, "giay": round(time.perf_counter() - t0, 2)},
            ensure_ascii=False,
        ),
        flush=True,
    )


main()
```

- [ ] **Step 2: Chạy thử bằng tay với một câu**

```bash
GOC=$(pwd)
mkdir -p /tmp/fish-thu
# dựng một đoạn mẫu bằng Edge để có cái mà thử
.venv/bin/edge-tts --voice vi-VN-HoaiMyNeural \
  --text "Hôm nay tôi sẽ hướng dẫn các bạn cách nấu món sườn hầm khoai tây thơm ngon." \
  --write-media /tmp/fish-thu/mau.mp3
ffmpeg -y -i /tmp/fish-thu/mau.mp3 -ar 44100 -ac 1 /tmp/fish-thu/mau.wav

echo '{"mau_wav":"/tmp/fish-thu/mau.wav","mau_text":"Hôm nay tôi sẽ hướng dẫn các bạn cách nấu món sườn hầm khoai tây thơm ngon.","cau":[{"i":0,"text":"Xin chào các bạn, đây là thử nghiệm."}],"thu_muc_ra":"/tmp/fish-thu/ra","model_dir":"'$GOC'/services/fish-mlx/s2-pro-8bit"}' \
  | services/fish-mlx/.venv/bin/python services/fish-mlx/doc_lo.py

open /tmp/fish-thu/ra/cau_00000.wav
```

Expected: dòng cuối stdout là JSON có `"xong": {"0": "..."}`, và file wav nghe ra tiếng Việt.

- [ ] **Step 3: Commit**

```bash
git add services/fish-mlx/doc_lo.py
git commit -m "feat(tts): script đọc lô câu bằng Fish S2-Pro trong venv model"
```

---

### Task 4: Nhà cung cấp `fish_mlx` và đường lui Edge

**Files:**
- Modify: `apps/worker/src/tts/fish_mlx.py`
- Modify: `apps/worker/src/tts/base.py`
- Test: `apps/worker/tests/test_fish_mlx_provider.py`

**Interfaces:**
- Consumes: `fish_giao_thuc.*` (Task 2), `kiem_moi_truong` (Task 1), `paths.giong_mau_wav/giong_mau_txt` (Kế hoạch C)
- Produces:
  - `FishMlxTTS(giong_doc_id: str)` — `ten = "fish_mlx"`, có `doc()` và `doc_lo()`
  - `base.lay_provider("fish_mlx", ...)` trả về nó
  - `base.NHA_CUNG_CAP["fish_mlx"]` mang nhãn giấy phép

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/worker/tests/test_fish_mlx_provider.py`:

```python
"""Fish MLX: chạy lô, và khi hỏng thì rơi về Edge — CÓ GHI LẠI.

Đổi giọng âm thầm là kiểu hỏng tệ nhất: người dùng duyệt bản dịch, nghe giọng
Edge, tưởng đó là giọng Fish mình đã chọn, rồi thắc mắc vì sao clone chẳng
giống gì. Nên mọi lần rơi về đều phải ghi lại và hiện được trên giao diện.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.errors import ReupError
from src.tts.fish_mlx import FishMlxTTS


@pytest.fixture
def mau(tmp_path, monkeypatch):
    wav = tmp_path / "mau.wav"
    wav.write_bytes(b"RIFF")
    txt = tmp_path / "mau.txt"
    txt.write_text("Đoạn mẫu", encoding="utf-8")
    monkeypatch.setattr("src.tts.fish_mlx.giong_mau_wav", lambda _id: wav)
    monkeypatch.setattr("src.tts.fish_mlx.giong_mau_txt", lambda _id: txt)
    monkeypatch.setattr("src.tts.fish_mlx.kiem_moi_truong", lambda: (True, ""))
    return tmp_path


def _chay_gia(stdout: str, ma_tra_ve: int = 0):
    class KetQuaGia:
        returncode = ma_tra_ve

        def __init__(self):
            self.stdout = stdout
            self.stderr = ""

    return lambda *a, **k: KetQuaGia()


def test_doc_lo_tra_ve_file_theo_chi_so(mau, monkeypatch, tmp_path) -> None:
    ra = tmp_path / "ra"
    ra.mkdir()
    (ra / "cau_00000.wav").write_bytes(b"x")
    out = json.dumps({"xong": {"0": str(ra / "cau_00000.wav")}, "hong": {}, "token": 30, "giay": 3.0})
    monkeypatch.setattr("src.tts.fish_mlx.subprocess.run", _chay_gia(out))

    p = FishMlxTTS(giong_doc_id="g1")
    files = p.doc_lo([{"i": 0, "text": "Xin chào"}], ra)
    assert files == {0: ra / "cau_00000.wav"}


def test_KHONG_dung_shell(mau, monkeypatch, tmp_path) -> None:
    ghi = {}

    def bat(cmd, **k):
        ghi["cmd"] = cmd
        ghi["kw"] = k
        class R:
            returncode = 0
            stdout = json.dumps({"xong": {}, "hong": {}, "token": 0, "giay": 1.0})
            stderr = ""
        return R()

    monkeypatch.setattr("src.tts.fish_mlx.subprocess.run", bat)
    FishMlxTTS(giong_doc_id="g1").doc_lo([{"i": 0, "text": "a"}], tmp_path)

    assert isinstance(ghi["cmd"], list)
    assert ghi["kw"].get("shell") in (None, False)
    #: CLAUDE.md: subprocess LUÔN phải có timeout.
    assert ghi["kw"].get("timeout") is not None


def test_tien_trinh_chet_thi_nem_loi_co_nghia(mau, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("src.tts.fish_mlx.subprocess.run", _chay_gia("bùm", ma_tra_ve=1))
    with pytest.raises(ReupError, match="Fish MLX"):
        FishMlxTTS(giong_doc_id="g1").doc_lo([{"i": 0, "text": "a"}], tmp_path)


def test_thieu_moi_truong_thi_bao_TRUOC_khi_chay(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("src.tts.fish_mlx.kiem_moi_truong", lambda: (False, "chưa dựng venv"))
    with pytest.raises(ReupError, match="chưa dựng venv"):
        FishMlxTTS(giong_doc_id="g1").doc_lo([{"i": 0, "text": "a"}], tmp_path)


def test_thieu_doan_mau_thi_bao_ro(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("src.tts.fish_mlx.kiem_moi_truong", lambda: (True, ""))
    monkeypatch.setattr("src.tts.fish_mlx.giong_mau_wav", lambda _id: tmp_path / "khong-co.wav")
    monkeypatch.setattr("src.tts.fish_mlx.giong_mau_txt", lambda _id: tmp_path / "khong-co.txt")
    with pytest.raises(ReupError, match="đoạn mẫu"):
        FishMlxTTS(giong_doc_id="g1").doc_lo([{"i": 0, "text": "a"}], tmp_path)


def test_cau_hong_duoc_ghi_lai_nhung_lo_van_chay_tiep(mau, monkeypatch, tmp_path) -> None:
    ra = tmp_path / "ra"
    ra.mkdir()
    (ra / "cau_00001.wav").write_bytes(b"x")
    out = json.dumps(
        {"xong": {"1": str(ra / "cau_00001.wav")}, "hong": {"0": "hết bộ nhớ"}, "token": 20, "giay": 2.0}
    )
    monkeypatch.setattr("src.tts.fish_mlx.subprocess.run", _chay_gia(out))
    files = FishMlxTTS(giong_doc_id="g1").doc_lo(
        [{"i": 0, "text": "a"}, {"i": 1, "text": "b"}], ra
    )
    assert set(files) == {1}


def test_ten_provider(mau) -> None:
    assert FishMlxTTS(giong_doc_id="g1").ten == "fish_mlx"
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/worker && pytest tests/test_fish_mlx_provider.py -v`
Expected: FAIL — `ImportError: cannot import name 'FishMlxTTS'`

- [ ] **Step 3: Viết nhà cung cấp**

Thêm vào `apps/worker/src/tts/fish_mlx.py` (nối tiếp phần Task 1):

```python
import subprocess

from reup_core.paths import fish_mlx_dir, giong_mau_txt, giong_mau_wav

from .fish_giao_thuc import YeuCau, doc_ket_qua, uoc_timeout


class FishMlxTTS:
    """Đọc bằng Fish S2-Pro chạy tại máy, nhân bản giọng từ đoạn mẫu.

    Không có danh sách giọng cố định: giọng đến từ đoạn mẫu trong thư viện
    giọng, tra theo ``giong_doc_id``. Đó là lý do ``cac_giong()`` trả rỗng —
    giao diện lấy danh sách từ bảng ``giong_doc``, không hỏi nhà cung cấp.
    """

    ten = "fish_mlx"

    def __init__(self, giong_doc_id: str = "") -> None:
        self._giong_id = giong_doc_id

    def cac_giong(self) -> list[GiongDoc]:
        """Rỗng — xem docstring lớp. Giọng nằm ở bảng ``giong_doc``."""
        return []

    def _doan_mau(self) -> tuple[Path, str]:
        wav = giong_mau_wav(self._giong_id)
        txt = giong_mau_txt(self._giong_id)
        if not wav.exists() or not txt.exists():
            raise ReupError(
                f"Giọng {self._giong_id} chưa có đoạn mẫu — thêm giọng ở Cấu hình → Giọng đọc."
            )
        return wav, txt.read_text(encoding="utf-8").strip()

    def doc_lo(self, cau: list[dict], thu_muc: Path) -> dict[int, Path]:
        """Đọc CẢ LÔ trong MỘT tiến trình. Trả ``{chỉ số câu: file}``.

        Một tiến trình cho cả lô chứ không phải mỗi câu một lần: nạp model mất
        1 giây, nhân với 672 câu là 11 phút phí thuần.
        """
        san_sang, ly_do = kiem_moi_truong()
        if not san_sang:
            raise ReupError(ly_do)

        wav, chu_mau = self._doan_mau()
        thu_muc.mkdir(parents=True, exist_ok=True)

        yeu_cau = YeuCau(
            mau_wav=str(wav),
            mau_text=chu_mau,
            cau=cau,
            thu_muc_ra=str(thu_muc),
            model_dir=str(fish_mlx_model()),
        )
        han = uoc_timeout(cau)

        #: Không shell=True, luôn có timeout (luật CLAUDE.md).
        proc = subprocess.run(
            [str(fish_mlx_python()), str(fish_mlx_dir() / "doc_lo.py")],
            input=yeu_cau.to_json() + "\n",
            capture_output=True,
            text=True,
            timeout=han,
        )
        if proc.returncode != 0:
            raise ReupError(
                f"Tiến trình Fish MLX chết (mã {proc.returncode}). "
                f"Đuôi stderr: {proc.stderr[-2000:]}"
            )

        kq = doc_ket_qua(proc.stdout)
        if kq.hong:
            log.warning("fish_mlx.cau_hong", so_cau=len(kq.hong), vi_du=list(kq.hong.items())[:3])
        log.info(
            "fish_mlx.lo_xong",
            xong=len(kq.xong),
            hong=len(kq.hong),
            token=kq.token,
            giay=kq.giay,
            token_moi_giay=round(kq.token / kq.giay, 1) if kq.giay else 0,
        )
        return {i: Path(p) for i, p in kq.xong.items() if Path(p).exists()}

    def doc(self, text: str, dst: Path, *, giong: str = "") -> Path:
        """Đọc MỘT câu — đường tương thích ``TTSProvider``.

        Chậm hơn ``doc_lo`` nhiều lần vì phải nạp model lại mỗi câu. Chỉ dùng
        cho việc lẻ như dựng câu đọc thử của thư viện giọng.
        """
        files = self.doc_lo([{"i": 0, "text": text}], dst.parent)
        ra = files.get(0)
        if ra is None:
            raise ReupError(f"Fish MLX không đọc được câu {text[:40]!r}")
        if ra != dst:
            ra.replace(dst)
        return dst
```

- [ ] **Step 4: Cắm vào `base.py`**

Trong `apps/worker/src/tts/base.py`, thêm vào `NHA_CUNG_CAP`:

```python
    "fish_mlx": "Fish Speech S2-Pro chạy TẠI MÁY — nhân bản giọng từ đoạn mẫu, "
    "không tốn tiền và không cần mạng, NHƯNG chậm hơn thời gian thực khoảng 2 lần "
    "và trọng số PHI THƯƠNG MẠI (Fish Audio Research License).",
```

và vào `lay_provider`, trước dòng `raise ValueError`:

```python
    if ten == "fish_mlx":
        from .fish_mlx import FishMlxTTS

        #: ``model`` ở đây mang ``giong_doc_id`` chứ không phải tên model:
        #: Fish không có model để chọn, giọng đến từ đoạn mẫu. Giữ nguyên chữ
        #: ký ``lay_provider`` để chỗ gọi không phải phân biệt nhà cung cấp.
        return FishMlxTTS(giong_doc_id=model)
```

- [ ] **Step 5: Chạy test cho chắc là qua**

Run: `cd apps/worker && pytest tests/test_fish_mlx_provider.py tests/test_fish_mlx_moi_truong.py -v`
Expected: PASS, 11 passed

- [ ] **Step 6: Commit**

```bash
cd apps/worker && ruff format . && ruff check --fix .
git add apps/worker/src/tts/fish_mlx.py apps/worker/src/tts/base.py apps/worker/tests/test_fish_mlx_provider.py
git commit -m "feat(tts): nhà cung cấp fish_mlx chạy tại máy, nhân bản giọng từ đoạn mẫu"
```

---

### Task 5: Nối vào bước lồng tiếng, có đường lui Edge và GHI LẠI

**Files:**
- Modify: `apps/worker/src/tasks/video.py`
- Test: `apps/worker/tests/test_fish_mlx_duong_lui.py`

**Interfaces:**
- Consumes: `FishMlxTTS.doc_lo` (Task 4)
- Produces:
  - `_doc_theo_lo(provider, vi_cues, vid, giong, model) -> dict[int, Path]`
  - `_ghi_da_roi_ve(video, tu: str, sang: str, ly_do: str) -> None` — ghi vào `process_config["tts_da_roi_ve"]`

Quyết định đã cân nhắc: `reup.tts_video` hiện đi hàng `media` với lý do ghi rõ trong `celery_app.py` — *"TTS là lời gọi MẠNG chứ không phải model chạy máy"*. Với `fish_mlx` lý do đó **đảo ngược**. Nhưng KHÔNG đổi định tuyến: đổi sang `gpu` (concurrency 1) sẽ chặn mất bước vá vốn là chỗ nghẽn thật, và làm chậm cả những video dùng Edge. Thay vào đó dùng **khoá file** để mỗi lúc chỉ một tiến trình model chạy — RAM đỉnh đo được 3,9 GB, hai tiến trình cùng lúc vẫn vừa 24 GB nhưng ba thì không.

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/worker/tests/test_fish_mlx_duong_lui.py`:

```python
"""Fish hỏng thì rơi về Edge — và PHẢI ghi lại việc đó.

Thiếu môi trường, tiến trình chết, quá thời gian: video vẫn phải có tiếng, thà
giọng Edge còn hơn không có gì. Nhưng im lặng đổi giọng là kiểu hỏng tệ nhất —
người dùng duyệt bản dịch, nghe giọng Edge, tưởng đó là giọng clone mình chọn.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.errors import ReupError
from src.tasks.video import _ghi_da_roi_ve


def test_ghi_lai_da_roi_ve_giong_nao() -> None:
    video = SimpleNamespace(process_config={"tts_provider": "fish_mlx"})
    _ghi_da_roi_ve(video, tu="fish_mlx", sang="edge", ly_do="tiến trình chết")

    ghi = video.process_config["tts_da_roi_ve"]
    assert ghi["tu"] == "fish_mlx"
    assert ghi["sang"] == "edge"
    assert "tiến trình chết" in ghi["ly_do"]


def test_khong_pha_cau_hinh_dang_co() -> None:
    video = SimpleNamespace(process_config={"tts_provider": "fish_mlx", "llm_model": "x"})
    _ghi_da_roi_ve(video, tu="fish_mlx", sang="edge", ly_do="hết giờ")
    assert video.process_config["llm_model"] == "x"


def test_process_config_None_van_ghi_duoc() -> None:
    video = SimpleNamespace(process_config=None)
    _ghi_da_roi_ve(video, tu="fish_mlx", sang="edge", ly_do="thiếu venv")
    assert video.process_config["tts_da_roi_ve"]["sang"] == "edge"


def test_ly_do_bi_cat_ngan_khong_nhet_ca_stderr_vao_db() -> None:
    #: stderr của mlx dài hàng chục nghìn ký tự. Nhét hết vào JSON của DB thì
    #: mỗi lần đọc video là kéo về ngần ấy.
    video = SimpleNamespace(process_config={})
    _ghi_da_roi_ve(video, tu="fish_mlx", sang="edge", ly_do="x" * 5000)
    assert len(video.process_config["tts_da_roi_ve"]["ly_do"]) <= 500
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/worker && pytest tests/test_fish_mlx_duong_lui.py -v`
Expected: FAIL — `ImportError: cannot import name '_ghi_da_roi_ve'`

- [ ] **Step 3: Viết hàm ghi và đường lô**

Thêm vào `apps/worker/src/tasks/video.py`:

```python
#: Chỉ một tiến trình model chạy cùng lúc. RAM đỉnh đo được 3,9 GB — hai
#: tiến trình vẫn vừa 24 GB, ba thì không. Dùng khoá file chứ không đổi định
#: tuyến sang hàng "gpu": hàng đó chạy concurrency 1 và đang là chỗ nghẽn của
#: bước vá, đẩy TTS vào đó sẽ chặn cả những video dùng Edge.
_KHOA_FISH = "fish-mlx.lock"


def _ghi_da_roi_ve(video, *, tu: str, sang: str, ly_do: str) -> None:
    """Ghi lại việc đã phải đổi nhà cung cấp giọng giữa chừng.

    Im lặng đổi giọng là kiểu hỏng tệ nhất: người dùng duyệt bản dịch, nghe
    giọng Edge, tưởng đó là giọng clone mình đã chọn, rồi thắc mắc vì sao
    nhân bản giọng chẳng giống gì.

    Cắt lý do còn 500 ký tự: stderr của mlx dài hàng chục nghìn ký tự, nhét
    hết vào JSON của DB thì mỗi lần đọc video là kéo về ngần ấy.
    """
    config = dict(video.process_config or {})
    config["tts_da_roi_ve"] = {"tu": tu, "sang": sang, "ly_do": str(ly_do)[:500]}
    video.process_config = config
    log.warning("tts.roi_ve", tu=tu, sang=sang, ly_do=str(ly_do)[:200])


def _doc_theo_lo(provider, vi_cues, vid: str, giong: str, model: str = "") -> dict[int, Path]:
    """Đọc cả lô bằng nhà cung cấp có ``doc_lo`` (hiện chỉ ``fish_mlx``).

    Vẫn đối chiếu vân tay như ``_doc_tuan_tu``: câu chưa đổi chữ thì dùng lại
    mẩu giọng cũ, không gửi vào lô.
    """
    thu_muc = voice_parts_dir(vid)
    dung_lai: dict[int, Path] = {}
    can_doc: list[dict] = []

    for i, cue in enumerate(vi_cues):
        dst = thu_muc / f"cau_{i:05d}.wav"
        cau = cue.text.replace("\n", " ")
        van_tay = _van_tay_cau(cau, giong, getattr(provider, "ten", ""), model)
        if _con_dung_duoc(dst, van_tay):
            dung_lai[i] = dst
        else:
            can_doc.append({"i": i, "text": cau})

    if not can_doc:
        log.info("tts.dung_lai_het", tong=len(vi_cues))
        return dung_lai

    with _khoa_mot_tien_trinh():
        moi = provider.doc_lo(can_doc, thu_muc)

    for c in can_doc:
        i = c["i"]
        if i in moi:
            (thu_muc / f"cau_{i:05d}.wav").with_suffix(".vantay").write_text(
                _van_tay_cau(c["text"], giong, getattr(provider, "ten", ""), model),
                encoding="utf-8",
            )

    log.info("tts.lo_xong", dung_lai=len(dung_lai), doc_moi=len(moi), can_doc=len(can_doc))
    return {**dung_lai, **moi}
```

Khoá dùng thư viện chuẩn, KHÔNG thêm `filelock`: CLAUDE.md cấm thêm thư viện mà không hỏi, và `fcntl.flock` đủ dùng. Thêm vào cùng file:

```python
import fcntl
from contextlib import contextmanager


@contextmanager
def _khoa_mot_tien_trinh():
    """Chỉ một tiến trình model Fish chạy cùng lúc, trên toàn máy.

    ``fcntl.flock`` chứ không phải khoá trong tiến trình: hai worker Celery là
    hai tiến trình khác nhau, khoá bằng ``threading.Lock`` không thấy nhau.

    Khoá tự nhả khi tiến trình chết (kể cả bị ``kill -9``) — khác với khoá
    bằng sự tồn tại của file, vốn để lại khoá mồ côi sau mỗi lần crash và
    lần sau treo mãi.

    Chờ chứ không bỏ: video xếp hàng thì đợi tới lượt, không phải hỏng.
    """
    duong = media_root() / _KHOA_FISH
    duong.parent.mkdir(parents=True, exist_ok=True)
    f = duong.open("w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()
```

Thêm `media_root` vào khối import từ `reup_core.paths` ở đầu `tasks/video.py`.

- [ ] **Step 4: Nối vào `tts_video_task`**

Trong `tts_video_task` (khoảng dòng 915–945), sau khi có `provider`, thay khối chọn đường đọc:

```python
    if not hasattr(provider, "doc_nhieu"):
        files = _doc_tuan_tu(provider, vi_cues, vid, giong, model)
```

bằng:

```python
    try:
        if hasattr(provider, "doc_lo"):
            files = _doc_theo_lo(provider, vi_cues, vid, giong, model)
        elif not hasattr(provider, "doc_nhieu"):
            files = _doc_tuan_tu(provider, vi_cues, vid, giong, model)
        else:
            files = _doc_song_song(provider, vi_cues, vid, giong, model)
    except (TtsError, ReupError, subprocess.TimeoutExpired) as exc:
        #: Rơi về Edge chứ không bỏ cả video: thiếu tiếng là mất hẳn bản dựng,
        #: còn giọng Edge thì vẫn xem được. Nhưng PHẢI ghi lại.
        if nha == "fish_mlx":
            _ghi_da_roi_ve(video, tu=nha, sang="edge", ly_do=str(exc))
            from ..tts.edge import GIONG_MAC_DINH as GIONG_EDGE

            provider = lay_provider("edge")
            giong, model, nha = GIONG_EDGE, "", "edge"
            files = _doc_song_song(provider, vi_cues, vid, giong, model)
        else:
            raise
```

`_doc_song_song` đã có sẵn ở `tasks/video.py:617` với đúng chữ ký `(provider, vi_cues, vid, giong, model)` — không phải viết mới, chỉ thêm nhánh `doc_lo` lên trước và bọc cả ba trong `try`.

Thêm `import subprocess` vào đầu `tasks/video.py` nếu chưa có (cần cho `subprocess.TimeoutExpired`).

- [ ] **Step 5: Chạy test cho chắc là qua**

Run: `cd apps/worker && pytest tests/test_fish_mlx_duong_lui.py -v && pytest -q`
Expected: PASS toàn bộ, không vỡ test cũ

- [ ] **Step 6: Hiện việc đã rơi về Edge trên giao diện**

Trong `apps/web/components/DuyetBanDichTab.tsx`, hàm `_daDungGi`, đọc thêm `tts_da_roi_ve` và hiện cảnh báo cạnh dòng "Giọng":

```tsx
  const roiVe = (c.tts_da_roi_ve ?? null) as { tu: string; sang: string; ly_do: string } | null;
```

```tsx
            {roiVe && (
              <span className="text-warn">
                ⚠ đã phải đổi từ {roiVe.tu} sang {roiVe.sang}: {roiVe.ly_do}
              </span>
            )}
```

- [ ] **Step 7: Commit**

```bash
cd apps/worker && ruff format . && ruff check --fix . && cd ../web && pnpm lint --fix
git add apps/worker/src/tasks/video.py apps/worker/tests/test_fish_mlx_duong_lui.py apps/web/components/DuyetBanDichTab.tsx
git commit -m "feat(tts): lồng tiếng theo lô bằng Fish MLX, rơi về Edge có ghi lại"
```

---

### Task 6: Script kiểm tay và nghiệm thu bằng tai

**Files:**
- Create: `apps/worker/scripts/try_fish_mlx.py`

CLAUDE.md xếp model AI vào diện **kiểm tay, không test tự động**. Bài học trong `docs/known-issues.md`: mọi lỗi nặng của dự án đều lọt qua test và chỉ lộ ra khi nghe/nhìn bản thật.

- [ ] **Step 1: Viết script**

Tạo `apps/worker/scripts/try_fish_mlx.py`:

```python
"""Đọc thử một lô câu bằng Fish MLX rồi in tốc độ thật. Chạy tay.

    python scripts/try_fish_mlx.py <giong_doc_id>
    python scripts/try_fish_mlx.py <giong_doc_id> --video <video_id> --so-cau 20

Không có ``--video`` thì đọc mấy câu mẫu có sẵn. Có thì lấy câu THẬT từ bản
dịch của video đó — đây mới là phép thử có nghĩa.

In ra RTF, token/giây và đường dẫn file để NGHE BẰNG TAI.
"""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

from src.tts.fish_mlx import FishMlxTTS, kiem_moi_truong

CAU_MAU = [
    "Hôm nay tôi sẽ hướng dẫn các bạn cách nấu món sườn hầm khoai tây.",
    "Sườn cho vào nồi nước lạnh, bắt đầu chần nước sôi.",
    "Cho dầu nóng vào phi thơm hành, rồi nấu thêm nước sốt chua cay.",
    "Được rồi, gắp thêm miếng thịt đi.",
    "Để bọn em ăn cùng mọi người nhé.",
]


def _cau_tu_video(video_id: str, so_cau: int) -> list[str]:
    sql = (
        "SELECT c->>'text' FROM subtitles s, jsonb_array_elements(s.cues::jsonb) c "
        f"WHERE s.video_id='{video_id}' AND s.lang='vi' "
        f"ORDER BY (c->>'i')::int LIMIT {so_cau}"
    )
    out = subprocess.run(
        ["docker", "exec", "reupstudio-postgres-1", "psql", "-U", "reup", "-d", "reup", "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    return [d.strip().replace("\n", " ") for d in out.splitlines() if d.strip()]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("giong_doc_id")
    p.add_argument("--video", default=None)
    p.add_argument("--so-cau", type=int, default=10)
    args = p.parse_args()

    san_sang, ly_do = kiem_moi_truong()
    if not san_sang:
        raise SystemExit(ly_do)

    cau_chu = _cau_tu_video(args.video, args.so_cau) if args.video else CAU_MAU
    if not cau_chu:
        raise SystemExit("Không lấy được câu nào — video đã dịch chưa?")

    ra = Path("/tmp") / f"fish-thu-{int(time.time())}"
    lo = [{"i": i, "text": t} for i, t in enumerate(cau_chu)]

    t0 = time.perf_counter()
    files = FishMlxTTS(giong_doc_id=args.giong_doc_id).doc_lo(lo, ra)
    may = time.perf_counter() - t0

    import soundfile as sf

    tieng = sum(len(sf.read(f)[0]) / sf.read(f)[1] for f in files.values())

    print(f"\nchạy được      : {len(files)}/{len(lo)} câu")
    print(f"giây máy       : {may:.1f}s")
    print(f"giây tiếng     : {tieng:.1f}s")
    print(f"RTF            : {may / tieng:.2f}   (đo mốc 2026-08-20: 1,98)")
    print(f"token/giây     : {tieng * 21 / may:.1f}   (đo mốc: 10,6)")
    print(f"\nNGHE THỬ: {ra}")
    print(f"  ghép cả lô:  cd {ra} && ls cau_*.wav | sed \"s|^|file '|;s|$|'|\" > l.txt && "
          f"ffmpeg -y -f concat -safe 0 -i l.txt -c copy /tmp/fish-ca-lo.wav && open /tmp/fish-ca-lo.wav")


main()
```

- [ ] **Step 2: Chạy thật và NGHE**

```bash
# lấy id một giọng đã thêm ở Kế hoạch C
GIONG=$(docker exec reupstudio-postgres-1 psql -U reup -d reup -t -A -c \
  "SELECT id FROM giong_doc WHERE nha_cung_cap='fish_mlx' AND trang_thai='san_sang' LIMIT 1")
cd apps/worker && python scripts/try_fish_mlx.py "$GIONG" --video ce91541b-35be-44de-830b-4a7b9114d79a --so-cau 20
```

Kiểm ba thứ — **đây là nghiệm thu thật của cả kế hoạch**:

1. RTF nằm quanh 2,0. Cao hơn 4 là có gì đó sai, đừng bỏ qua.
2. Nghe cả lô: **cùng MỘT giọng** từ đầu đến cuối. Mỗi câu một người khác nghĩa là đoạn mẫu không được dùng.
3. Nghe rõ là tiếng Việt, và **khá hơn hẳn** bản clone từ giọng máy.

- [ ] **Step 3: Commit**

```bash
git add apps/worker/scripts/try_fish_mlx.py
git commit -m "docs(tts): script kiểm tay tốc độ và chất lượng Fish MLX"
```

---

## Nghiệm thu kế hoạch B

- [ ] `bash scripts/cai-fish-mlx.sh` chạy sạch, in `Device(gpu, 0)`
- [ ] `cd apps/worker && pytest -q` — xanh
- [ ] `try_fish_mlx.py` cho RTF quanh 2,0 và token/giây quanh 10
- [ ] Nghe cả lô: một giọng duy nhất từ đầu đến cuối
- [ ] Chất lượng khá hơn hẳn bản clone từ giọng máy
- [ ] Tắt venv model (đổi tên `services/fish-mlx/.venv`) rồi lồng tiếng → **tự rơi về Edge**, và tab Chờ duyệt hiện cảnh báo "đã phải đổi từ fish_mlx sang edge"
- [ ] Nhãn "chạy tại máy · phi thương mại" hiện cạnh giọng `fish_mlx` ở Cấu hình → Giọng đọc
- [ ] `git status` sạch — model 4,6 GB không lọt vào git
