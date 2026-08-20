# Kế hoạch A — Duyệt bản dịch trên video

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Người duyệt xem được video kèm phụ đề nổi trên hình ở cả hai chỗ dừng, đối chiếu Trung–Việt ĐÚNG câu, và dịch lại được từng câu hoặc cả video.

**Architecture:** Sửa gốc trước — hàm thuần ghép câu theo giao nhau thời gian thay cho ghép theo chỉ số (đang sai). Thêm ba endpoint mỏng (router chỉ validate, service làm việc). Web dùng một component chung `KhungDoiChieu` cho cả hai tab, phụ đề vẽ bằng overlay HTML đồng bộ theo `currentTime`, không burn gì cả.

**Tech Stack:** FastAPI, SQLAlchemy, Celery, Next.js App Router, TanStack Query, Tailwind.

**Spec:** `docs/superpowers/specs/2026-08-20-duyet-ban-dich-va-long-tieng-design.md` (Phần A)

## Global Constraints

- Python 3.12, type hint bắt buộc cho mọi hàm public. `pathlib.Path`, không dùng chuỗi đường dẫn.
- **Mọi đường dẫn file đi qua `packages/reup_core/src/reup_core/paths.py`.** Không `os.path.join`, không f-string ghép path ở chỗ khác.
- `routers/` chỉ validate input và gọi service. `services/` chứa logic, không biết gì về HTTP. `models/` chỉ định nghĩa bảng.
- `pipeline/` là hàm thuần: KHÔNG import celery, KHÔNG chạm DB.
- Việc chạm mạng hoặc chạy >2 giây phải qua Celery; endpoint trả `202 {task_id}`.
- `task_bridge` gửi task **bắt buộc truyền `queue=`** — app Celery của API không mang `task_routes` của worker; thiếu nó task rơi vào hàng không ai nghe, API vẫn trả 202 và không có gì xảy ra.
- Không `print` trong code chạy thật; dùng `structlog` qua `reup_core.logging.get_logger`.
- Không `except: pass`. Exception có nghĩa, kế thừa `ReupError`/`ApiError`.
- Web: server component mặc định, `'use client'` chỉ khi cần state/event. Fetch qua `lib/api.ts`, không `fetch` thẳng trong component. Không polling tiến trình — đã có WebSocket.
- Tailwind dùng biến đã định nghĩa (`bg-panel`, `text-muted`, `border-border`, `text-accent`, `text-err`, `text-ok`), không viết mã màu thô.
- Đặt tên: endpoint số nhiều kebab-case; task Celery `động_từ_danh_từ`; component React PascalCase; hook `use` + PascalCase.
- Format trước khi commit: `ruff format . && ruff check --fix .` (Python), `pnpm lint --fix` (web).
- Một task = một commit.

---

### Task 1: Ghép câu Trung–Việt theo giao nhau thời gian

Đây là lỗi gốc: `format_cues` gộp và tách câu rồi đánh số lại từ 0, nên `vi[i]` không còn là bản dịch của `zh[i]`. Đo trên DB thật: 8/10 video lệch số câu; video `bbba9781` lệch 7 giây và ghép ra chữ không liên quan.

**Files:**
- Create: `packages/reup_core/src/reup_core/doi_chieu.py`
- Test: `apps/worker/tests/test_ghep_doi_chieu.py`

Đặt ở `reup_core` chứ KHÔNG ở `apps/worker/src/pipeline/`: Task 3 sẽ cần hàm này từ phía API, mà **API không được import code worker** (xem docstring `apps/api/src/services/task_bridge.py` — worker mang theo whisper và những thứ nặng API không cài). `reup_core` chưa có thư mục test riêng; test cho nó nằm ở `apps/worker/tests/` như `test_paths.py` đã làm.

**Interfaces:**
- Produces:
  - `CauDon(i: int, start: float, end: float, text: str)` — frozen dataclass, câu tối giản
  - `CapDoiChieu(i: int, start: float, end: float, dich: str, goc: str)` — frozen dataclass
  - `ghep_theo_thoi_gian(dich: list[CauDon], goc: list[CauDon]) -> list[CapDoiChieu]`
  - `tu_dicts(items: list[dict]) -> list[CauDon]` — đọc cột `subtitles.cues` (JSON)

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/worker/tests/test_ghep_doi_chieu.py`:

```python
"""Ghép câu dịch với câu gốc — sai ở đây là người duyệt đối chiếu nhầm câu.

Không ghép theo CHỈ SỐ được: ``format_cues`` gộp câu ngắn, tách câu dài rồi
đánh số lại từ 0, nên câu Việt thứ i không phải bản dịch của câu Trung thứ i.
Đo trên DB thật ngày 2026-08-20: 8/10 video lệch số câu, video tệ nhất lệch
7 giây và ghép ra chữ hoàn toàn không liên quan.

Ghép theo giao nhau thời gian thì đúng, vì mốc giờ của câu Việt bắt nguồn từ
chính câu Trung sinh ra nó.
"""

from __future__ import annotations

from reup_core.doi_chieu import CauDon, ghep_theo_thoi_gian, tu_dicts


def _c(i: int, start: float, end: float, text: str) -> CauDon:
    return CauDon(i=i, start=start, end=end, text=text)


class TestGhepTheoThoiGian:
    def test_mot_doi_mot(self) -> None:
        dich = [_c(0, 0.0, 1.0, "Xin chào"), _c(1, 1.0, 2.0, "Tạm biệt")]
        goc = [_c(0, 0.0, 1.0, "你好"), _c(1, 1.0, 2.0, "再见")]
        ra = ghep_theo_thoi_gian(dich, goc)
        assert [r.goc for r in ra] == ["你好", "再见"]

    def test_mot_cau_goc_bi_TACH_thanh_hai_cau_dich(self) -> None:
        #: format_cues tách câu dài -> hai câu dịch cùng trỏ về một câu gốc.
        dich = [_c(0, 0.0, 1.5, "Nửa đầu"), _c(1, 1.5, 3.0, "nửa sau")]
        goc = [_c(0, 0.0, 3.0, "一句很长的话")]
        ra = ghep_theo_thoi_gian(dich, goc)
        assert [r.goc for r in ra] == ["一句很长的话", "一句很长的话"]

    def test_hai_cau_goc_bi_GOP_thanh_mot_cau_dich(self) -> None:
        #: Hiện CẢ HAI, nối bằng " / " — cách ghép 1-1 sẽ giấu mất một câu.
        dich = [_c(0, 0.0, 2.0, "Đây rồi. Có ngay đây.")]
        goc = [_c(0, 0.0, 1.0, "来"), _c(1, 1.0, 2.0, "好嘞")]
        ra = ghep_theo_thoi_gian(dich, goc)
        assert ra[0].goc == "来 / 好嘞"

    def test_khong_co_cau_goc_nao_trung_gio(self) -> None:
        dich = [_c(0, 10.0, 11.0, "Không có gốc")]
        goc = [_c(0, 0.0, 1.0, "早")]
        ra = ghep_theo_thoi_gian(dich, goc)
        assert ra[0].goc == ""

    def test_cham_bien_khong_tinh_la_giao_nhau(self) -> None:
        #: goc kết thúc ĐÚNG lúc dich bắt đầu -> không chồng lấn, không ghép.
        dich = [_c(0, 1.0, 2.0, "Sau")]
        goc = [_c(0, 0.0, 1.0, "Trước")]
        assert ghep_theo_thoi_gian(dich, goc)[0].goc == ""

    def test_giu_nguyen_chi_so_moc_gio_va_chu_cua_ban_dich(self) -> None:
        dich = [_c(7, 3.25, 4.5, "Bảy")]
        ra = ghep_theo_thoi_gian(dich, [])
        assert (ra[0].i, ra[0].start, ra[0].end, ra[0].dich) == (7, 3.25, 4.5, "Bảy")

    def test_danh_sach_rong(self) -> None:
        assert ghep_theo_thoi_gian([], []) == []
        assert ghep_theo_thoi_gian([], [_c(0, 0.0, 1.0, "x")]) == []

    def test_tu_dicts_doc_dung_cot_cues(self) -> None:
        ra = tu_dicts([{"i": 2, "start": 1.5, "end": 3.0, "text": "x", "sua_tay": True}])
        assert ra == [CauDon(i=2, start=1.5, end=3.0, text="x")]

    def test_khong_bo_sot_khi_cau_goc_dai_trum_nhieu_cau_dich(self) -> None:
        #: Con trỏ quét không được nhảy qua câu gốc còn dùng cho câu dịch sau.
        dich = [_c(0, 0.0, 1.0, "a"), _c(1, 1.0, 2.0, "b"), _c(2, 2.0, 3.0, "c")]
        goc = [_c(0, 0.0, 3.0, "TRÙM")]
        assert [r.goc for r in ghep_theo_thoi_gian(dich, goc)] == ["TRÙM"] * 3
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/worker && pytest tests/test_ghep_doi_chieu.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reup_core.doi_chieu'`

- [ ] **Step 3: Viết bản cài đặt tối thiểu**

Tạo `packages/reup_core/src/reup_core/doi_chieu.py`:

```python
"""Ghép câu dịch với câu gốc — dùng chung cho API và worker.

Nằm ở ``reup_core`` chứ không ở ``apps/worker``: API cần hàm này để trả bảng
đối chiếu, mà API KHÔNG được import code worker (xem docstring
``api/src/services/task_bridge.py``).

Hàm THUẦN: không chạm DB, không import celery.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CauDon:
    """Một câu phụ đề tối giản — chỉ những gì việc ghép cần."""

    i: int
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class CapDoiChieu:
    """Một dòng bảng đối chiếu: câu dịch và (các) câu gốc cùng khoảng thời gian."""

    i: int
    start: float
    end: float
    dich: str
    #: Các câu gốc chồng thời gian, nối bằng " / ". Rỗng nếu không có câu nào.
    goc: str


def ghep_theo_thoi_gian(dich: list[CauDon], goc: list[CauDon]) -> list[CapDoiChieu]:
    """Ghép câu dịch với câu gốc theo GIAO NHAU THỜI GIAN, không theo chỉ số.

    Vì sao không theo chỉ số: ``subtitle_format.format_cues`` gộp câu ngắn,
    tách câu dài rồi đánh số lại từ 0 — sau bước đó ``dich[i]`` không còn là
    bản dịch của ``goc[i]``. Đo trên dữ liệu thật ngày 2026-08-20: 8/10 video
    lệch số câu.

    Hai câu coi là cùng chỗ khi khoảng thời gian CHỒNG LẤN thật sự:
    ``goc.start < dich.end and goc.end > dich.start``. Chạm biên (câu này kết
    thúc đúng lúc câu kia bắt đầu) KHÔNG tính — nếu tính thì mỗi câu dịch đều
    dính thêm câu gốc liền trước.

    Cả hai danh sách phải đã sắp theo ``start`` tăng dần (mọi nơi trong
    pipeline đều giữ thứ tự này) — nhờ vậy quét được bằng con trỏ, không phải
    so từng cặp.
    """
    ra: list[CapDoiChieu] = []
    dau = 0

    for cau in dich:
        #: Bỏ qua hẳn câu gốc đã kết thúc trước khi câu dịch này bắt đầu. An
        #: toàn vì ``dich`` sắp tăng dần: câu dịch sau còn bắt đầu muộn hơn.
        while dau < len(goc) and goc[dau].end <= cau.start:
            dau += 1

        phan: list[str] = []
        vi_tri = dau
        while vi_tri < len(goc) and goc[vi_tri].start < cau.end:
            if goc[vi_tri].end > cau.start:
                phan.append(goc[vi_tri].text)
            vi_tri += 1

        ra.append(
            CapDoiChieu(
                i=cau.i,
                start=cau.start,
                end=cau.end,
                dich=cau.text,
                goc=" / ".join(phan),
            )
        )

    return ra


def tu_dicts(items: list[dict]) -> list[CauDon]:
    """Đọc cột ``subtitles.cues`` (JSON) thành ``CauDon``, bỏ qua khoá lạ."""
    return [
        CauDon(i=int(d["i"]), start=float(d["start"]), end=float(d["end"]), text=str(d["text"]))
        for d in items
    ]
```

- [ ] **Step 4: Chạy test cho chắc là qua**

Run: `cd apps/worker && pytest tests/test_ghep_doi_chieu.py -v`
Expected: PASS, 9 passed

- [ ] **Step 5: Kiểm bằng dữ liệu THẬT, không chỉ bằng test**

Bài học đã ghi trong `docs/known-issues.md`: lỗi nặng của dự án này đều lọt qua test. Chạy đối chiếu trên đúng video đã phát hiện lỗi:

```bash
cd apps/worker && python - <<'PY'
import json, subprocess
from src.pipeline.cues import cues_from_dicts, ghep_theo_thoi_gian

VID = "bbba9781-e2d5-46e8-a4d2-e8be90896804"
def lay(lang):
    out = subprocess.run([
        "docker", "exec", "reupstudio-postgres-1", "psql", "-U", "reup", "-d", "reup",
        "-t", "-A", "-c",
        f"SELECT cues::text FROM subtitles WHERE video_id='{VID}' AND lang='{lang}'",
    ], capture_output=True, text=True).stdout.strip()
    return cues_from_dicts(json.loads(out))

for c in ghep_theo_thoi_gian(lay("vi"), lay("zh"))[60:66]:
    print(f"{c.start:7.1f}  {c.dich[:38]:40s} <- {c.goc}")
PY
```

Expected: câu "Alo, hôm nay thế nào rồi?" ghép với `喂 今天还怎么样啊`, KHÔNG phải `好嘞`.

- [ ] **Step 6: Commit**

```bash
cd apps/worker && ruff format . && ruff check --fix .
git add packages/reup_core/src/reup_core/doi_chieu.py apps/worker/tests/test_ghep_doi_chieu.py
git commit -m "fix(pipeline): bảng đối chiếu ghép sai câu — ghép theo thời gian, không theo chỉ số"
```

---

### Task 2: Endpoint `/videos/{id}/preview` trả video nguồn

`/videos/{id}/file` chỉ trả bản render CUỐI, nên hai chỗ dừng không có gì để xem. `proxy.mp4` đã được dựng ở bước PROBE (`tasks/video.py:415`) nên có mặt từ lúc video vào tab Chờ dịch — đã kiểm: 10/10 thư mục `media/work/*` đều có, kích thước 304×540, 6–22 MB.

**Files:**
- Modify: `apps/api/src/services/video_service.py`
- Modify: `apps/api/src/routers/videos.py`
- Test: `apps/api/tests/test_preview_video.py`

**Interfaces:**
- Consumes: `paths.proxy_path(video_id: str) -> Path`, `paths.raw_video(platform: str, source_video_id: str) -> Path` (đã có)
- Produces: `video_service.duong_dan_xem_truoc(db: Session, video_id: uuid.UUID) -> Path`

- [ ] **Step 1: Viết test hỏng**

Tạo `apps/api/tests/test_preview_video.py`:

```python
"""Video nguồn để xem TRƯỚC khi render.

Tách khỏi ``/file`` chứ không dùng chung: ``/file`` mang nghĩa "bản render
cuối". Trộn hai thứ vào một đường là mở cửa cho lỗi xem nhầm bản — người dùng
tưởng đang xem bản đã dựng trong khi đó là bản gốc.

Ưu tiên proxy 540p (tua nhanh, 6–22 MB) và chỉ rơi về bản gốc khi thiếu.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.errors import NotFound
from src.services import video_service


@pytest.fixture
def video():
    return SimpleNamespace(
        id=uuid.uuid4(),
        deleted_at=None,
        source_platform="douyin",
        source_video_id="7300000000000000000",
    )


class DbGia:
    def __init__(self, video):
        self._video = video

    def get(self, _model, _id):
        return self._video


def test_uu_tien_proxy_khi_co(monkeypatch, tmp_path, video) -> None:
    proxy = tmp_path / "proxy.mp4"
    proxy.write_bytes(b"x" * 100)
    monkeypatch.setattr(video_service, "proxy_path", lambda _vid: proxy)
    monkeypatch.setattr(video_service, "raw_video", lambda _p, _s: tmp_path / "khong-dung.mp4")

    assert video_service.duong_dan_xem_truoc(DbGia(video), video.id) == proxy


def test_roi_ve_ban_goc_khi_thieu_proxy(monkeypatch, tmp_path, video) -> None:
    goc = tmp_path / "source.mp4"
    goc.write_bytes(b"x" * 100)
    monkeypatch.setattr(video_service, "proxy_path", lambda _vid: tmp_path / "khong-ton-tai.mp4")
    monkeypatch.setattr(video_service, "raw_video", lambda _p, _s: goc)

    assert video_service.duong_dan_xem_truoc(DbGia(video), video.id) == goc


def test_proxy_RONG_tinh_la_khong_co(monkeypatch, tmp_path, video) -> None:
    #: Ghi dở rồi crash để lại file 0 byte. Coi là hợp lệ thì trình duyệt
    #: nhận về video trắng và không ai biết vì sao.
    rong = tmp_path / "proxy.mp4"
    rong.write_bytes(b"")
    goc = tmp_path / "source.mp4"
    goc.write_bytes(b"x" * 100)
    monkeypatch.setattr(video_service, "proxy_path", lambda _vid: rong)
    monkeypatch.setattr(video_service, "raw_video", lambda _p, _s: goc)

    assert video_service.duong_dan_xem_truoc(DbGia(video), video.id) == goc


def test_khong_con_file_nao_thi_bao_ro(monkeypatch, tmp_path, video) -> None:
    monkeypatch.setattr(video_service, "proxy_path", lambda _vid: tmp_path / "a.mp4")
    monkeypatch.setattr(video_service, "raw_video", lambda _p, _s: tmp_path / "b.mp4")

    with pytest.raises(NotFound, match="chưa tải xong"):
        video_service.duong_dan_xem_truoc(DbGia(video), video.id)
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/api && pytest tests/test_preview_video.py -v`
Expected: FAIL — `AttributeError: module 'src.services.video_service' has no attribute 'duong_dan_xem_truoc'`

- [ ] **Step 3: Viết service**

Trong `apps/api/src/services/video_service.py`, thêm vào phần import ở đầu file:

```python
from reup_core.paths import proxy_path, raw_video
```

Thêm hàm (đặt cạnh `get_subtitles` cho gần nhóm chức năng đọc):

```python
def duong_dan_xem_truoc(db: Session, video_id: uuid.UUID) -> Path:
    """File video để XEM TRƯỚC khi render — proxy 540p, rơi về bản gốc nếu thiếu.

    Khác ``video.out_path`` (bản render cuối): ở hai chỗ dừng duyệt thì chưa
    có bản render nào, mà đó lại chính là lúc cần nhìn thấy hình nhất.

    File 0 byte tính là KHÔNG CÓ: ghi dở rồi crash để lại file rỗng, nhận nó
    là hợp lệ thì trình duyệt phát ra màn hình trắng mà không báo gì.
    """
    video = get_video(db, video_id)

    proxy = proxy_path(str(video_id))
    if proxy.exists() and proxy.stat().st_size > 0:
        return proxy

    goc = raw_video(video.source_platform, video.source_video_id)
    if goc.exists() and goc.stat().st_size > 0:
        return goc

    raise NotFound("Video chưa tải xong hoặc file đã bị xoá — chưa có gì để xem.")
```

Kiểm `from pathlib import Path` đã có trong file; nếu chưa thì thêm.

- [ ] **Step 4: Chạy test cho chắc là qua**

Run: `cd apps/api && pytest tests/test_preview_video.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Thêm route**

Trong `apps/api/src/routers/videos.py`, thêm NGAY TRƯỚC route `/{video_id}/file`:

```python
@router.get("/{video_id}/preview")
def preview_file(video_id: uuid.UUID, db: Session = Depends(get_db)):
    """Video NGUỒN để xem ở hai chỗ dừng duyệt, trước khi có bản render.

    ``FileResponse`` hỗ trợ range request nên thẻ ``<video>`` tua được mà
    không phải tải hết file.
    """
    f = video_service.duong_dan_xem_truoc(db, video_id)
    return FileResponse(f, media_type="video/mp4", filename=f"preview-{video_id}.mp4")
```

- [ ] **Step 6: Kiểm bằng máy chủ thật**

```bash
cd apps/api && uvicorn src.main:app --port 8000 &
sleep 4
VID=$(docker exec reupstudio-postgres-1 psql -U reup -d reup -t -A -c \
  "SELECT id FROM videos WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 1")
curl -s -o /dev/null -w "status=%{http_code} type=%{content_type} size=%{size_download}\n" \
  "http://localhost:8000/api/v1/videos/$VID/preview"
curl -s -r 0-99 -o /dev/null -w "range status=%{http_code}\n" \
  "http://localhost:8000/api/v1/videos/$VID/preview"
kill %1
```

Expected: `status=200 type=video/mp4`, và range request trả `206`.

- [ ] **Step 7: Commit**

```bash
cd apps/api && ruff format . && ruff check --fix .
git add apps/api/src/services/video_service.py apps/api/src/routers/videos.py apps/api/tests/test_preview_video.py
git commit -m "feat(api): endpoint xem video nguồn ở hai chỗ dừng duyệt"
```

---

### Task 3: Endpoint `/videos/{id}/doi-chieu` trả cặp câu đã ghép đúng

Ghép ở backend chứ không để React tự ghép: đây là logic nghiệp vụ đã có test, và giao diện không nên phải biết vì sao không ghép được theo chỉ số.

**Files:**
- Modify: `apps/api/src/schemas/video.py`
- Modify: `apps/api/src/services/video_service.py`
- Modify: `apps/api/src/routers/videos.py`
- Test: `apps/api/tests/test_doi_chieu_api.py`

**Interfaces:**
- Consumes: `ghep_theo_thoi_gian`, `CapDoiChieu`, `cues_from_dicts` từ Task 1
- Produces:
  - schema `CapDoiChieuOut(i: int, start: float, end: float, dich: str, goc: str, sua_tay: bool)`
  - `video_service.doi_chieu(db: Session, video_id: uuid.UUID) -> list[dict]`

Hàm ghép đã nằm sẵn ở `reup_core` từ Task 1 nên API dùng được ngay — `apps/api` KHÔNG được import code worker.

- [ ] **Step 1: Viết test hỏng cho service**

Tạo `apps/api/tests/test_doi_chieu_api.py`:

```python
"""Bảng đối chiếu Trung–Việt cho màn duyệt.

Ghép ở BACKEND chứ không để React tự ghép: đây là logic nghiệp vụ đã có test,
và giao diện không nên phải biết vì sao không ghép được theo chỉ số.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.errors import NotFound
from src.services import video_service


class DbGia:
    def __init__(self, video, rows):
        self._video = video
        self._rows = rows

    def get(self, _model, _id):
        return self._video

    def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: self._rows)


@pytest.fixture
def video():
    return SimpleNamespace(id=uuid.uuid4(), deleted_at=None)


def _sub(lang, cues):
    return SimpleNamespace(lang=lang, cues=cues)


def test_ghep_dung_cau_khi_lech_so_dong(video) -> None:
    #: 1 câu Trung dài -> 2 câu Việt sau khi tách. Ghép theo chỉ số sẽ để câu
    #: Việt thứ hai không có gốc.
    vi = _sub("vi", [
        {"i": 0, "start": 0.0, "end": 1.5, "text": "Nửa đầu"},
        {"i": 1, "start": 1.5, "end": 3.0, "text": "nửa sau"},
    ])
    zh = _sub("zh", [{"i": 0, "start": 0.0, "end": 3.0, "text": "一句很长的话"}])
    ra = video_service.doi_chieu(DbGia(video, [vi, zh]), video.id)
    assert [r["goc"] for r in ra] == ["一句很长的话", "一句很长的话"]


def test_bao_co_sua_tay(video) -> None:
    vi = _sub("vi", [
        {"i": 0, "start": 0.0, "end": 1.0, "text": "Đã sửa", "sua_tay": True},
        {"i": 1, "start": 1.0, "end": 2.0, "text": "Chưa sửa"},
    ])
    ra = video_service.doi_chieu(DbGia(video, [vi, _sub("zh", [])]), video.id)
    assert [r["sua_tay"] for r in ra] == [True, False]


def test_chua_dich_thi_bao_ro(video) -> None:
    zh = _sub("zh", [{"i": 0, "start": 0.0, "end": 1.0, "text": "你好"}])
    with pytest.raises(NotFound, match="chưa có bản dịch"):
        video_service.doi_chieu(DbGia(video, [zh]), video.id)


def test_khong_co_phu_de_goc_van_tra_ban_dich(video) -> None:
    #: Thiếu tiếng Trung không được làm hỏng cả bảng — vẫn đọc được bản dịch.
    vi = _sub("vi", [{"i": 0, "start": 0.0, "end": 1.0, "text": "Một mình"}])
    ra = video_service.doi_chieu(DbGia(video, [vi]), video.id)
    assert len(ra) == 1 and ra[0]["goc"] == "" and ra[0]["dich"] == "Một mình"
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/api && pytest tests/test_doi_chieu_api.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'doi_chieu'`

- [ ] **Step 3: Viết service**

Trong `apps/api/src/services/video_service.py` thêm import:

```python
from reup_core.doi_chieu import ghep_theo_thoi_gian, tu_dicts
```

và hàm:

```python
def doi_chieu(db: Session, video_id: uuid.UUID) -> list[dict[str, Any]]:
    """Bảng đối chiếu câu dịch ↔ câu gốc, đã ghép ĐÚNG theo thời gian.

    Trả về dict thay vì dataclass để router khỏi phải chuyển kiểu; thêm cờ
    ``sua_tay`` cho giao diện biết câu nào người dùng đã chữa (câu đó được
    giữ nguyên khi dịch lại toàn bộ).
    """
    get_video(db, video_id)

    rows = db.scalars(sa.select(Subtitle).where(Subtitle.video_id == video_id)).all()
    theo_lang = {r.lang: r.cues for r in rows}

    if "vi" not in theo_lang:
        raise NotFound(f"Video {video_id} chưa có bản dịch tiếng Việt.")

    vi_cues = theo_lang["vi"]
    da_sua = {int(c["i"]): bool(c.get("sua_tay")) for c in vi_cues}

    cap = ghep_theo_thoi_gian(tu_dicts(vi_cues), tu_dicts(theo_lang.get("zh", [])))
    return [
        {
            "i": c.i,
            "start": c.start,
            "end": c.end,
            "dich": c.dich,
            "goc": c.goc,
            "sua_tay": da_sua.get(c.i, False),
        }
        for c in cap
    ]
```

- [ ] **Step 4: Chạy test cho chắc là qua**

Run: `cd apps/api && pytest tests/test_doi_chieu_api.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Thêm schema và route**

Trong `apps/api/src/schemas/video.py`:

```python
class CapDoiChieuOut(BaseModel):
    """Một dòng bảng đối chiếu ở màn duyệt bản dịch."""

    i: int
    start: float
    end: float
    dich: str
    #: Câu gốc chồng thời gian, nối bằng " / ". Rỗng khi không có câu nào.
    goc: str
    sua_tay: bool = False
```

Trong `apps/api/src/routers/videos.py` thêm `CapDoiChieuOut` vào khối import schema, và thêm route sau `subtitles`:

```python
@router.get("/{video_id}/doi-chieu", response_model=list[CapDoiChieuOut])
def doi_chieu(video_id: uuid.UUID, db: Session = Depends(get_db)):
    """Cặp câu Trung–Việt đã ghép đúng theo thời gian, cho màn duyệt bản dịch."""
    return video_service.doi_chieu(db, video_id)
```

- [ ] **Step 6: Kiểm bằng dữ liệu thật**

```bash
cd apps/api && uvicorn src.main:app --port 8000 &
sleep 4
curl -s "http://localhost:8000/api/v1/videos/bbba9781-e2d5-46e8-a4d2-e8be90896804/doi-chieu" \
  | python3 -c "import json,sys; [print(f\"{r['start']:7.1f} {r['dich'][:34]:36s} <- {r['goc']}\") for r in json.load(sys.stdin)[60:66]]"
kill %1
```

Expected: "Alo, hôm nay thế nào rồi?" ghép với `喂 今天还怎么样啊`.

- [ ] **Step 7: Commit**

```bash
ruff format . && ruff check --fix .
git add apps/api/src/services/video_service.py apps/api/src/routers/videos.py apps/api/src/schemas/video.py apps/api/tests/test_doi_chieu_api.py
git commit -m "feat(api): endpoint đối chiếu Trung-Việt ghép đúng theo thời gian"
```

---

### Task 4: Đánh dấu câu người dùng sửa tay

Dịch lại toàn bộ KHÔNG được ghi đè công người dùng đã chữa. Cột `cues` là JSON nên thêm khoá không cần migration.

**Files:**
- Modify: `apps/api/src/services/video_service.py:247-284` (`sua_ban_dich`)
- Test: `apps/api/tests/test_sua_ban_dich.py` (thêm test vào file đã có)

**Interfaces:**
- Produces: mỗi cue người dùng sửa mang thêm khoá `"sua_tay": True` trong `subtitles.cues`

- [ ] **Step 1: Viết test hỏng**

Thêm vào cuối `apps/api/tests/test_sua_ban_dich.py`:

```python
def test_cau_da_sua_duoc_danh_dau_sua_tay(video_cho_duyet) -> None:
    """Đánh dấu để bước DỊCH LẠI toàn bộ không ghi đè công vừa chữa.

    ``edited_by_user`` ở cấp DÒNG không đủ: nó nói "có ai đó đã sửa gì đó
    trong bản dịch này", không nói câu nào. Dịch lại toàn bộ cần biết chính
    xác câu nào phải giữ.
    """
    video, db = video_cho_duyet
    row = video_service.sua_ban_dich(db, video.id, [{"i": 1, "text": "Câu hai đã chữa"}])

    theo_i = {c["i"]: c for c in row.cues}
    assert theo_i[1]["sua_tay"] is True
    assert theo_i[1]["text"] == "Câu hai đã chữa"
    #: Câu không đụng tới thì KHÔNG được đánh dấu — nếu không thì dịch lại
    #: toàn bộ chẳng còn câu nào được thay.
    assert "sua_tay" not in theo_i[0]
    assert "sua_tay" not in theo_i[2]


def test_sua_tay_giu_nguyen_moc_thoi_gian(video_cho_duyet) -> None:
    video, db = video_cho_duyet
    row = video_service.sua_ban_dich(db, video.id, [{"i": 0, "text": "Chữ mới"}])
    goc = {c["i"]: c for c in row.cues}[0]
    assert (goc["start"], goc["end"]) == (0.0, 1.3)
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/api && pytest tests/test_sua_ban_dich.py -v -k sua_tay`
Expected: FAIL — `KeyError: 'sua_tay'`

- [ ] **Step 3: Sửa service**

Trong `apps/api/src/services/video_service.py`, hàm `sua_ban_dich`, đổi dòng:

```python
        moi.append({**goc, "text": chu})
```

thành:

```python
        #: ``sua_tay`` đánh dấu ở cấp TỪNG CÂU. ``edited_by_user`` (cấp dòng)
        #: chỉ nói "có ai đó đã sửa gì đó", không nói câu nào — mà bước dịch
        #: lại toàn bộ cần biết chính xác câu nào phải giữ nguyên.
        moi.append({**goc, "text": chu, "sua_tay": True})
```

- [ ] **Step 4: Chạy cả file test cho chắc không vỡ cái cũ**

Run: `cd apps/api && pytest tests/test_sua_ban_dich.py -v`
Expected: PASS toàn bộ, kể cả các test đã có từ trước

- [ ] **Step 5: Commit**

```bash
cd apps/api && ruff format . && ruff check --fix .
git add apps/api/src/services/video_service.py apps/api/tests/test_sua_ban_dich.py
git commit -m "feat(api): đánh dấu từng câu người dùng sửa tay để dịch lại không ghi đè"
```

---

### Task 5: Dịch lại — từng câu hoặc toàn bộ

**Files:**
- Create: `apps/worker/src/tasks/dich_lai.py`
- Modify: `apps/api/src/schemas/video.py`
- Modify: `apps/api/src/services/video_service.py`
- Modify: `apps/api/src/services/task_bridge.py`
- Modify: `apps/api/src/routers/videos.py`
- Modify: `apps/worker/src/celery_app.py` (đăng ký module task mới nếu file đó liệt kê tay)
- Test: `apps/api/tests/test_dich_lai_api.py`, `apps/worker/tests/test_dich_lai_giu_cau_sua_tay.py`

**Interfaces:**
- Consumes: `task_bridge.celery()`, `video_service.get_video`
- Produces:
  - schema `DichLaiIn(llm_provider: str | None, llm_model: str | None, chi_so: list[int] | None)`
  - `video_service.kiem_truoc_khi_dich_lai(db, video_id, chi_so) -> None`
  - `task_bridge.dich_lai(video_id: uuid.UUID) -> str` — task name `reup.dich_lai`, `queue="media"`
  - worker: `gop_giu_cau_sua_tay(cu: list[dict], moi: list[dict]) -> list[dict]`

- [ ] **Step 1: Viết test hỏng cho hàm gộp (worker, hàm thuần)**

Tạo `apps/worker/tests/test_dich_lai_giu_cau_sua_tay.py`:

```python
"""Dịch lại KHÔNG được xoá công người dùng đã chữa tay.

Người dùng ngồi sửa 20 câu, rồi bấm "dịch lại toàn bộ bằng model khác" vì
những câu CÒN LẠI chưa ưng. Ghi đè tất thì 20 câu kia mất sạch, và mất im
lặng — không lỗi, không cảnh báo.
"""

from __future__ import annotations

from src.tasks.dich_lai import gop_giu_cau_sua_tay


def test_giu_cau_sua_tay_bo_qua_ban_dich_moi() -> None:
    cu = [
        {"i": 0, "start": 0.0, "end": 1.0, "text": "Người dùng chữa", "sua_tay": True},
        {"i": 1, "start": 1.0, "end": 2.0, "text": "Máy dịch cũ"},
    ]
    moi = [
        {"i": 0, "start": 0.0, "end": 1.0, "text": "Máy dịch lại"},
        {"i": 1, "start": 1.0, "end": 2.0, "text": "Máy dịch mới"},
    ]
    ra = gop_giu_cau_sua_tay(cu, moi)
    assert [c["text"] for c in ra] == ["Người dùng chữa", "Máy dịch mới"]
    assert ra[0]["sua_tay"] is True


def test_giu_nguyen_thu_tu_va_so_luong() -> None:
    cu = [{"i": i, "start": float(i), "end": i + 1.0, "text": f"cũ {i}"} for i in range(5)]
    moi = [{"i": i, "start": float(i), "end": i + 1.0, "text": f"mới {i}"} for i in range(5)]
    ra = gop_giu_cau_sua_tay(cu, moi)
    assert [c["i"] for c in ra] == [0, 1, 2, 3, 4]
    assert [c["text"] for c in ra] == [f"mới {i}" for i in range(5)]


def test_khong_co_cau_sua_tay_thi_lay_het_ban_moi() -> None:
    cu = [{"i": 0, "start": 0.0, "end": 1.0, "text": "cũ"}]
    moi = [{"i": 0, "start": 0.0, "end": 1.0, "text": "mới"}]
    assert gop_giu_cau_sua_tay(cu, moi)[0]["text"] == "mới"


def test_ban_moi_thieu_cau_thi_giu_cau_cu() -> None:
    #: Model trả thiếu câu là chuyện có thật. Bỏ luôn câu đó thì phụ đề hụt
    #: một đoạn mà video vẫn "xong".
    cu = [
        {"i": 0, "start": 0.0, "end": 1.0, "text": "cũ 0"},
        {"i": 1, "start": 1.0, "end": 2.0, "text": "cũ 1"},
    ]
    moi = [{"i": 0, "start": 0.0, "end": 1.0, "text": "mới 0"}]
    ra = gop_giu_cau_sua_tay(cu, moi)
    assert [c["text"] for c in ra] == ["mới 0", "cũ 1"]
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/worker && pytest tests/test_dich_lai_giu_cau_sua_tay.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.tasks.dich_lai'`

- [ ] **Step 3: Viết hàm gộp và task**

Tạo `apps/worker/src/tasks/dich_lai.py`:

```python
"""Dịch lại bản dịch đã có — cả video hoặc chỉ mấy câu người dùng tích.

Vì sao tách khỏi ``tasks/video.py``: file đó đã hơn 1100 dòng và mang cả chuỗi
pipeline chính. Dịch lại là nhánh riêng, chạy trên video ĐÃ dừng ở chỗ duyệt,
không đi qua chuỗi nào.
"""

from __future__ import annotations

from reup_core.db import session_scope
from reup_core.enums import PipelineStep
from reup_core.logging import get_logger
from reup_core.models import Subtitle, Video
from sqlalchemy import select

from .. import progress as prog
from ..celery_app import app
from ..errors import ReupError
from ..pipeline.cues import cues_from_dicts, cues_to_dicts
from ..pipeline.translate import translate_cues

log = get_logger(__name__)


def gop_giu_cau_sua_tay(cu: list[dict], moi: list[dict]) -> list[dict]:
    """Trộn bản dịch mới vào bản cũ, GIỮ NGUYÊN câu người dùng đã chữa tay.

    Hàm THUẦN, không chạm DB — test được thẳng.

    Ba luật:
    - câu có ``sua_tay`` -> giữ nguyên bản cũ, không đụng tới;
    - câu bản mới có -> lấy chữ mới, giữ mốc thời gian cũ;
    - câu bản mới THIẾU -> giữ bản cũ. Model trả thiếu câu là chuyện có thật,
      bỏ luôn thì phụ đề hụt một đoạn mà video vẫn "xong".
    """
    moi_theo_i = {int(c["i"]): c for c in moi}
    ra: list[dict] = []

    for cau in cu:
        i = int(cau["i"])
        if cau.get("sua_tay"):
            ra.append(cau)
            continue
        thay = moi_theo_i.get(i)
        ra.append({**cau, "text": str(thay["text"])} if thay else cau)

    return ra


@app.task(name="reup.dich_lai")
def dich_lai_task(video_id: str) -> dict:
    """Dịch lại rồi ghi đè bản dịch, trừ câu người dùng đã chữa.

    ``chi_so`` đọc từ ``process_config["dich_lai_chi_so"]`` — API đặt vào đó
    trước khi gửi task, giống cách ``llm_model`` đang đi. Rỗng/không có nghĩa
    là dịch lại TOÀN BỘ.
    """
    with session_scope() as db:
        video = db.get(Video, video_id)
        if video is None:
            raise ReupError(f"Không có video {video_id}")

        config = video.process_config or {}
        chi_so = config.get("dich_lai_chi_so") or []

        vi_row = db.scalar(
            select(Subtitle).where(Subtitle.video_id == video.id, Subtitle.lang == "vi")
        )
        zh_row = db.scalar(
            select(Subtitle).where(Subtitle.video_id == video.id, Subtitle.lang == "zh")
        )
        if vi_row is None or zh_row is None:
            raise ReupError(f"Video {video_id} thiếu phụ đề để dịch lại")

        cu = list(vi_row.cues)
        can_dich = [c for c in cu if not chi_so or int(c["i"]) in set(chi_so)]

        log.info("dich_lai.bat_dau", video_id=video_id, tong=len(cu), can_dich=len(can_dich))
        prog.progress(video_id, PipelineStep.TRANSLATE.value, 5)

        #: Dịch lại từ chữ TIẾNG VIỆT hiện có sang tiếng Việt tốt hơn là vô
        #: nghĩa — phải quay về câu gốc. Ghép lại nguồn theo thời gian.
        from reup_core.doi_chieu import ghep_theo_thoi_gian, tu_dicts

        cap = {c.i: c.goc for c in ghep_theo_thoi_gian(tu_dicts(cu), tu_dicts(list(zh_row.cues)))}
        nguon = [
            {"i": int(c["i"]), "start": c["start"], "end": c["end"], "text": cap.get(int(c["i"]), "")}
            for c in can_dich
            if cap.get(int(c["i"]))
        ]
        if not nguon:
            raise ReupError("Không tìm được câu gốc tương ứng để dịch lại")

        moi = cues_to_dicts(
            translate_cues(
                cues_from_dicts(nguon),
                model=config.get("llm_model") or "",
                **_khoa_llm(video),
            )
        )

        vi_row.cues = gop_giu_cau_sua_tay(cu, moi)
        vi_row.source = "llm"
        prog.progress(video_id, PipelineStep.TRANSLATE.value, 100)
        log.info("dich_lai.xong", video_id=video_id, doi=len(moi))

    #: Đọc lại giọng cho câu vừa đổi chữ — cơ chế vân tay tự bỏ qua câu không
    #: đổi, nên gọi thẳng chuỗi đọc lại là đủ.
    app.send_task("reup.doc_lai_sau_khi_sua", args=[video_id], queue="download")
    return {"doi": len(moi), "tong": len(cu)}


def _khoa_llm(video) -> dict[str, str]:
    """Khoá/địa chỉ/nhà cung cấp cho ``translate_cues``, đọc từ ``ai_providers``."""
    from .video import _khoa_llm_cho_translate

    return _khoa_llm_cho_translate(video)
```

- [ ] **Step 4: Chạy test cho chắc là qua**

Run: `cd apps/worker && pytest tests/test_dich_lai_giu_cau_sua_tay.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Đăng ký task với Celery**

`app.autodiscover_tasks(["src.tasks"])` ở `celery_app.py:76` KHÔNG bắt được module này — autodiscover tìm `src.tasks.tasks`, mà `src/tasks/__init__.py` đang rỗng. Task hiện có được đăng ký bằng dòng import tay ở cuối file. Bỏ bước này thì API trả 202, người dùng thấy "đang dịch lại", và **không bao giờ có gì xảy ra** — không lỗi, không log.

Thêm vào cuối `apps/worker/src/celery_app.py`, ngay dưới dòng import đã có:

```python
from .tasks import video as _video_tasks  # noqa: E402,F401
from .tasks import dich_lai as _dich_lai_tasks  # noqa: E402,F401
```

Kiểm task đã đăng ký thật:

```bash
cd apps/worker && python -c "
from src.celery_app import app
print('reup.dich_lai' in app.tasks)"
```

Expected: `True`

Nhớ bài học đã ghi: **Celery không tự nạp lại code.** Worker đang chạy phải khởi động lại thì mới thấy task mới.

- [ ] **Step 6: Viết test hỏng cho API**

Tạo `apps/api/tests/test_dich_lai_api.py`:

```python
"""Dịch lại: chỉ cho phép khi video đang ở chỗ dừng duyệt.

Cho dịch lại lúc pipeline đang chạy là hai tiến trình cùng ghi vào một dòng
phụ đề — bên nào ghi sau thắng, và không ai biết mình mất bản nào.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from reup_core.enums import VideoStatus

from src.errors import ApiError
from src.services import video_service


class DbGia:
    def __init__(self, video):
        self._video = video

    def get(self, _model, _id):
        return self._video


def _video(status=VideoStatus.REVIEW.value, cho_duyet=True):
    return SimpleNamespace(
        id=uuid.uuid4(),
        deleted_at=None,
        status=status,
        flags={"cho_duyet_ban_dich": cho_duyet},
        process_config={},
    )


def test_dat_chi_so_vao_process_config() -> None:
    v = _video()
    video_service.kiem_truoc_khi_dich_lai(DbGia(v), v.id, [3, 7], "openrouter", "model-x")
    assert v.process_config["dich_lai_chi_so"] == [3, 7]
    assert v.process_config["llm_model"] == "model-x"
    assert v.process_config["llm_provider_ma"] == "openrouter"


def test_khong_truyen_chi_so_nghia_la_toan_bo() -> None:
    v = _video()
    video_service.kiem_truoc_khi_dich_lai(DbGia(v), v.id, None, None, None)
    assert v.process_config["dich_lai_chi_so"] == []


def test_giu_model_cu_khi_khong_chon_lai() -> None:
    v = _video()
    v.process_config = {"llm_model": "model-cu", "llm_provider_ma": "gemini"}
    video_service.kiem_truoc_khi_dich_lai(DbGia(v), v.id, None, None, None)
    assert v.process_config["llm_model"] == "model-cu"
    assert v.process_config["llm_provider_ma"] == "gemini"


def test_tu_choi_khi_video_dang_chay() -> None:
    v = _video(status=VideoStatus.RUNNING.value)
    with pytest.raises(ApiError, match="đang chờ duyệt"):
        video_service.kiem_truoc_khi_dich_lai(DbGia(v), v.id, None, None, None)


def test_tu_choi_khi_chua_toi_cho_duyet_ban_dich() -> None:
    #: Trạng thái review nhưng chưa dịch lần nào — chưa có gì để dịch LẠI.
    v = _video(cho_duyet=False)
    with pytest.raises(ApiError, match="chưa dịch"):
        video_service.kiem_truoc_khi_dich_lai(DbGia(v), v.id, None, None, None)
```

- [ ] **Step 7: Chạy test cho chắc là hỏng**

Run: `cd apps/api && pytest tests/test_dich_lai_api.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'kiem_truoc_khi_dich_lai'`

- [ ] **Step 8: Viết service, task_bridge, schema, route**

`apps/api/src/services/video_service.py`:

```python
def kiem_truoc_khi_dich_lai(
    db: Session,
    video_id: uuid.UUID,
    chi_so: list[int] | None,
    llm_provider: str | None,
    llm_model: str | None,
) -> None:
    """Kiểm điều kiện rồi ghi lựa chọn vào ``process_config`` cho worker đọc.

    Chỉ cho dịch lại khi video đang đứng ở chỗ dừng duyệt bản dịch. Cho phép
    lúc pipeline đang chạy là hai tiến trình cùng ghi một dòng phụ đề — bên
    nào ghi sau thắng, và không ai biết mình mất bản nào.

    Model/nhà cung cấp KHÔNG chọn lại thì giữ nguyên cái đã dùng, không rơi về
    mặc định: người dùng bấm "dịch lại mấy câu này" thường muốn đúng model cũ.
    """
    video = get_video(db, video_id)

    if video.status != VideoStatus.REVIEW.value:
        raise ApiError("Chỉ dịch lại được khi video đang chờ duyệt bản dịch.")
    if not (video.flags or {}).get("cho_duyet_ban_dich"):
        raise ApiError("Video này chưa dịch lần nào — dùng nút Dịch, không phải dịch lại.")

    config = dict(video.process_config or {})
    config["dich_lai_chi_so"] = list(chi_so or [])
    if llm_model:
        config["llm_model"] = llm_model
    if llm_provider:
        config["llm_provider_ma"] = llm_provider
    video.process_config = config
```

`apps/api/src/services/task_bridge.py` — thêm hằng số cạnh các hằng số đã có và hàm:

```python
DICH_LAI = "reup.dich_lai"


def dich_lai(video_id: uuid.UUID) -> str:
    """Đẩy task dịch lại. Lựa chọn (câu nào, model nào) nằm trong ``process_config``.

    ``queue="media"`` giống ``translate_video``: bước dịch là gọi mạng, việc
    CPU, không cần GPU. BẮT BUỘC truyền queue — app Celery của API không mang
    ``task_routes`` của worker, thiếu nó task rơi vào hàng mặc định không ai
    nghe, API vẫn trả 202 và không bao giờ có gì xảy ra.
    """
    result = celery().send_task(DICH_LAI, args=[str(video_id)], queue="media")
    return result.id
```

`apps/api/src/schemas/video.py`:

```python
class DichLaiIn(BaseModel):
    """Yêu cầu dịch lại. ``chi_so`` rỗng/không có = dịch lại toàn bộ."""

    chi_so: list[int] | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
```

`apps/api/src/routers/videos.py` — thêm `DichLaiIn` vào khối import schema và route:

```python
@router.post("/{video_id}/retranslate", response_model=TaskAccepted, status_code=202)
def retranslate(video_id: uuid.UUID, body: DichLaiIn, db: Session = Depends(get_db)):
    """Dịch lại toàn bộ hoặc chỉ mấy câu đã tích.

    Commit TRƯỚC khi gửi task — worker chạy gần như tức thì, chậm một nhịp là
    nó đọc phải ``process_config`` cũ.
    """
    video_service.kiem_truoc_khi_dich_lai(
        db, video_id, body.chi_so, body.llm_provider, body.llm_model
    )
    db.commit()

    task_id = task_bridge.dich_lai(video_id)
    so = len(body.chi_so or [])
    return TaskAccepted(
        task_id=task_id,
        message=f"Đang dịch lại {so} câu" if so else "Đang dịch lại toàn bộ",
    )
```

- [ ] **Step 9: Chạy test cho chắc là qua**

Run: `cd apps/api && pytest tests/test_dich_lai_api.py -v`
Expected: PASS, 5 passed

- [ ] **Step 10: Chạy toàn bộ test hai bên**

Run: `cd apps/api && pytest -q && cd ../worker && pytest -q`
Expected: tất cả PASS, không vỡ test cũ nào

- [ ] **Step 11: Commit**

```bash
ruff format . && ruff check --fix .
git add apps/worker/src/tasks/dich_lai.py apps/worker/tests/test_dich_lai_giu_cau_sua_tay.py apps/api/src/services/video_service.py apps/api/src/services/task_bridge.py apps/api/src/schemas/video.py apps/api/src/routers/videos.py apps/api/tests/test_dich_lai_api.py
git commit -m "feat(translate): dịch lại từng câu hoặc toàn bộ, giữ câu đã sửa tay"
```

---

### Task 6: Hàm thuần cho overlay — đổi giây thành câu đang phát

Tách khỏi React để test được: đây là chỗ dễ sai nhất của overlay (biên câu, khoảng lặng giữa hai câu, tua ngược).

**Files:**
- Create: `apps/web/lib/cauDangPhat.ts`
- Test: `apps/web/lib/cauDangPhat.test.ts`

**Interfaces:**
- Produces:
  - `type CapDoiChieu = { i: number; start: number; end: number; dich: string; goc: string; sua_tay: boolean }`
  - `cauDangPhat(cues: CapDoiChieu[], giay: number): number` — trả chỉ số MẢNG (không phải `i`), `-1` khi không câu nào đang phát

- [ ] **Step 1: Kiểm bộ chạy test của web**

```bash
cd apps/web && cat package.json | grep -A3 '"scripts"' && ls vitest.config.* jest.config.* 2>/dev/null
```

Nếu chưa có bộ test nào thì cài vitest:

```bash
cd apps/web && pnpm add -D vitest && \
  node -e "const p=require('./package.json');p.scripts.test='vitest run';require('fs').writeFileSync('package.json',JSON.stringify(p,null,2))"
```

- [ ] **Step 2: Viết test hỏng**

Tạo `apps/web/lib/cauDangPhat.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { cauDangPhat, type CapDoiChieu } from "./cauDangPhat";

const c = (i: number, start: number, end: number): CapDoiChieu => ({
  i, start, end, dich: `câu ${i}`, goc: "", sua_tay: false,
});

// Ba câu, CÓ khoảng lặng giữa câu 1 và câu 2 — phụ đề thật luôn có khoảng hở.
const CUES = [c(0, 0, 1), c(1, 1, 2), c(2, 3, 4)];

describe("cauDangPhat", () => {
  it("trả câu đang phát", () => {
    expect(cauDangPhat(CUES, 0.5)).toBe(0);
    expect(cauDangPhat(CUES, 1.5)).toBe(1);
    expect(cauDangPhat(CUES, 3.5)).toBe(2);
  });

  it("trong khoảng lặng thì không câu nào", () => {
    expect(cauDangPhat(CUES, 2.5)).toBe(-1);
  });

  it("trước câu đầu và sau câu cuối thì không câu nào", () => {
    expect(cauDangPhat(CUES, -1)).toBe(-1);
    expect(cauDangPhat(CUES, 99)).toBe(-1);
  });

  it("đúng biên: start tính vào câu, end thì không", () => {
    // Không thế thì ở giây 1.0 cả hai câu cùng sáng.
    expect(cauDangPhat(CUES, 1)).toBe(1);
    expect(cauDangPhat(CUES, 2)).toBe(-1);
  });

  it("danh sách rỗng", () => {
    expect(cauDangPhat([], 1)).toBe(-1);
  });

  it("tua ngược vẫn đúng", () => {
    // Không được giữ trạng thái con trỏ giữa các lần gọi.
    expect(cauDangPhat(CUES, 3.5)).toBe(2);
    expect(cauDangPhat(CUES, 0.5)).toBe(0);
  });
});
```

- [ ] **Step 3: Chạy test cho chắc là hỏng**

Run: `cd apps/web && pnpm test`
Expected: FAIL — không tìm thấy module `./cauDangPhat`

- [ ] **Step 4: Viết bản cài đặt**

Tạo `apps/web/lib/cauDangPhat.ts`:

```ts
/** Một dòng bảng đối chiếu, đúng hình dạng `/videos/{id}/doi-chieu` trả về. */
export interface CapDoiChieu {
  i: number;
  start: number;
  end: number;
  dich: string;
  goc: string;
  sua_tay: boolean;
}

/**
 * Chỉ số MẢNG của câu đang phát ở giây `giay`, hoặc -1 nếu không câu nào.
 *
 * Trả chỉ số mảng chứ không trả `i`: overlay cần lấy ra đúng phần tử và cuộn
 * bảng tới đúng dòng, mà `i` có thể không liên tục sau khi dịch lại.
 *
 * Biên: `start` tính vào câu, `end` thì KHÔNG. Không thế thì ở đúng giây giao
 * nhau hai câu cùng sáng.
 *
 * Tìm nhị phân vì hàm này chạy ở mỗi `timeupdate` (khoảng 4 lần/giây) trên
 * danh sách tới 672 câu, và KHÔNG giữ trạng thái giữa các lần gọi — tua ngược
 * phải cho kết quả đúng như tua tới.
 */
export function cauDangPhat(cues: CapDoiChieu[], giay: number): number {
  let thap = 0;
  let cao = cues.length - 1;

  while (thap <= cao) {
    const giua = (thap + cao) >> 1;
    const cue = cues[giua];
    if (giay < cue.start) cao = giua - 1;
    else if (giay >= cue.end) thap = giua + 1;
    else return giua;
  }

  return -1;
}
```

- [ ] **Step 5: Chạy test cho chắc là qua**

Run: `cd apps/web && pnpm test`
Expected: PASS, 6 passed

- [ ] **Step 6: Commit**

```bash
cd apps/web && pnpm lint --fix
git add apps/web/lib/cauDangPhat.ts apps/web/lib/cauDangPhat.test.ts apps/web/package.json
git commit -m "feat(web): hàm thuần đổi giây thành câu đang phát cho overlay phụ đề"
```

---

### Task 7: Component `KhungDoiChieu` — video kèm phụ đề nổi trên hình

**Files:**
- Create: `apps/web/components/KhungDoiChieu.tsx`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/types.ts` (thêm kiểu nếu file này khai tay; nếu sinh từ OpenAPI thì chạy lại lệnh sinh)

**Interfaces:**
- Consumes: `cauDangPhat`, `CapDoiChieu` từ Task 6; endpoint `/preview`, `/doi-chieu`, `/voice-track`
- Produces: `<KhungDoiChieu>` với props dưới đây

- [ ] **Step 1: Thêm đường gọi API**

Trong `apps/web/lib/api.ts`, cạnh `fileUrl` và `voiceTrackUrl` đã có:

```ts
  previewUrl: (id: string) => `${PREFIX}/videos/${id}/preview`,

  doiChieu: (id: string) => request<CapDoiChieu[]>(`/videos/${id}/doi-chieu`),

  dichLai: (
    id: string,
    body: { chi_so?: number[]; llm_provider?: string; llm_model?: string },
  ) =>
    request<TaskAccepted>(`/videos/${id}/retranslate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
```

Thêm import `import type { CapDoiChieu } from "@/lib/cauDangPhat";` ở đầu file.

- [ ] **Step 2: Sinh lại type từ OpenAPI**

```bash
cd apps/api && uvicorn src.main:app --port 8000 &
sleep 4
cd apps/web && npx openapi-typescript http://localhost:8000/openapi.json -o lib/types.gen.ts
kill %1
```

Luật số 7 CLAUDE.md: type frontend sinh từ OpenAPI, không gõ tay interface trùng backend.

- [ ] **Step 3: Viết component**

Tạo `apps/web/components/KhungDoiChieu.tsx`:

```tsx
"use client";

import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { cauDangPhat, type CapDoiChieu } from "@/lib/cauDangPhat";

/** Lệch quá ngần này giây thì nắn dải tiếng về khớp hình. */
const NGUONG_LECH_GIAY = 0.15;

interface Props {
  videoId: string;
  cues: CapDoiChieu[];
  /** `zh` hiện câu gốc trên hình (tab Chờ dịch), `vi` hiện bản dịch (tab Chờ duyệt). */
  hien: "vi" | "zh";
  /** Có dải tiếng Việt để nghe kèm không — chỉ tab Chờ duyệt mới có. */
  coDaiTieng?: boolean;
  /** Chữ người dùng đang gõ, chưa lưu: `{ [i]: text }`. Overlay hiện chữ này NGAY. */
  dangSua?: Record<number, string>;
  /** Vùng an toàn của nền tảng đích, phần trăm 0–1. Bỏ trống thì không vẽ. */
  vungAnToan?: { top: number; bottom: number; left: number; right: number };
}

/**
 * Video kèm phụ đề vẽ nổi trên hình, đồng bộ với bảng câu bên cạnh.
 *
 * Vì sao overlay HTML chứ không `<track>` WebVTT: cần ba thứ mà `<track>`
 * không làm được — tô sáng câu đang phát đồng bộ với bảng, hiện NGAY chữ
 * người dùng đang gõ khi chưa lưu, và vẽ vùng an toàn của nền tảng.
 *
 * Vì sao không burn thử bằng ffmpeg: cả chỗ dừng này sinh ra để TRÁNH render.
 */
export function KhungDoiChieu({
  videoId,
  cues,
  hien,
  coDaiTieng = false,
  dangSua,
  vungAnToan,
}: Props) {
  const theVideo = useRef<HTMLVideoElement>(null);
  const theTieng = useRef<HTMLAudioElement>(null);
  const [giay, setGiay] = useState(0);
  const [ngheTiengViet, setNgheTiengViet] = useState(coDaiTieng);
  const [doc9x16, setDoc9x16] = useState(false);

  const dangO = useMemo(() => cauDangPhat(cues, giay), [cues, giay]);
  const cue = dangO >= 0 ? cues[dangO] : null;

  //: Chữ trên hình đọc từ `dangSua` TRƯỚC: sửa xong phải thấy ngay trên hình,
  //: không đợi lưu. Không thế thì không biết chữ mới có tràn khung không.
  const chuTrenHinh = cue
    ? hien === "vi"
      ? (dangSua?.[cue.i] ?? cue.dich)
      : cue.goc
    : "";

  // Khoá dải tiếng theo hình. Chỉ nắn khi lệch quá ngưỡng — nắn mỗi lần
  // `timeupdate` thì tiếng bị giật liên tục.
  useEffect(() => {
    const v = theVideo.current;
    const a = theTieng.current;
    if (!v || !a) return;

    const dongBo = () => {
      if (Math.abs(a.currentTime - v.currentTime) > NGUONG_LECH_GIAY) {
        a.currentTime = v.currentTime;
      }
    };
    const phat = () => {
      dongBo();
      if (ngheTiengViet) void a.play().catch(() => undefined);
    };
    const dung = () => a.pause();

    v.addEventListener("play", phat);
    v.addEventListener("pause", dung);
    v.addEventListener("seeked", dongBo);
    return () => {
      v.removeEventListener("play", phat);
      v.removeEventListener("pause", dung);
      v.removeEventListener("seeked", dongBo);
    };
  }, [ngheTiengViet]);

  const nhayToi = (s: number) => {
    const v = theVideo.current;
    if (!v) return;
    v.currentTime = s;
    void v.play().catch(() => undefined);
  };

  return (
    <div className="flex min-h-0 gap-3">
      <div className="relative shrink-0 self-start overflow-hidden rounded-lg bg-black">
        {/* eslint-disable-next-line jsx-a11y/media-has-caption --
            Phụ đề vẽ bằng overlay ngay bên dưới, không có track riêng. */}
        <video
          key={videoId}
          ref={theVideo}
          src={api.previewUrl(videoId)}
          controls
          //: Tắt tiếng gốc khi đang nghe bản lồng tiếng — hai giọng chồng nhau
          //: thì không nghe rõ giọng nào.
          muted={ngheTiengViet}
          onTimeUpdate={(e) => setGiay(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => {
            const el = e.currentTarget;
            //: Vùng an toàn chỉ có nghĩa trên khung DỌC. Nguồn ngang sẽ được
            //: đổi khung ở bước sau — vẽ dải lên bản ngang là chỉ sai chỗ.
            setDoc9x16(el.videoHeight > el.videoWidth * 1.5);
          }}
          className="max-h-[62vh] w-auto"
        />

        {/* Vùng an toàn nền tảng — bốn dải theo phần trăm, luật số 2 CLAUDE.md. */}
        {vungAnToan && doc9x16 && (
          <div className="pointer-events-none absolute inset-0">
            <div className="absolute inset-x-0 top-0 bg-warn/20" style={{ height: `${vungAnToan.top * 100}%` }} />
            <div className="absolute inset-x-0 bottom-0 bg-warn/20" style={{ height: `${vungAnToan.bottom * 100}%` }} />
            <div className="absolute inset-y-0 left-0 bg-warn/20" style={{ width: `${vungAnToan.left * 100}%` }} />
            <div className="absolute inset-y-0 right-0 bg-warn/20" style={{ width: `${vungAnToan.right * 100}%` }} />
          </div>
        )}

        {/* Phụ đề. Đặt ở 12% từ đáy — trong vùng an toàn của mọi nền tảng. */}
        {chuTrenHinh && (
          <div className="pointer-events-none absolute inset-x-0 bottom-[12%] px-4 text-center">
            <span className="inline-block whitespace-pre-wrap rounded bg-black/65 px-2 py-1 text-[15px] font-medium leading-snug text-white">
              {chuTrenHinh}
            </span>
          </div>
        )}

        {coDaiTieng && (
          // eslint-disable-next-line jsx-a11y/media-has-caption -- dải lời thoại, phụ đề ở trên
          <audio ref={theTieng} src={api.voiceTrackUrl(videoId)} preload="auto" />
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        {coDaiTieng && (
          <div className="mb-1.5 flex items-center gap-2 text-[11.5px]">
            <span className="text-muted">Đang nghe:</span>
            <button
              className={clsx("btn btn-sm", ngheTiengViet && "btn-primary")}
              onClick={() => setNgheTiengViet(true)}
            >
              Tiếng Việt
            </button>
            <button
              className={clsx("btn btn-sm", !ngheTiengViet && "btn-primary")}
              onClick={() => setNgheTiengViet(false)}
            >
              Tiếng gốc
            </button>
          </div>
        )}

        <BangCau cues={cues} dangO={dangO} hien={hien} dangSua={dangSua} onChon={nhayToi} />
      </div>
    </div>
  );
}

interface BangProps {
  cues: CapDoiChieu[];
  dangO: number;
  hien: "vi" | "zh";
  dangSua?: Record<number, string>;
  onChon: (giay: number) => void;
}

/** Bảng câu tự cuộn theo câu đang phát; bấm dòng nào nhảy tới đúng giây đó. */
function BangCau({ cues, dangO, hien, dangSua, onChon }: BangProps) {
  const khung = useRef<HTMLDivElement>(null);

  //: Cuộn theo câu đang phát. `block: "nearest"` để không giật khi câu đã nằm
  //: trong tầm nhìn rồi.
  useEffect(() => {
    if (dangO < 0) return;
    khung.current?.querySelector(`[data-o="${dangO}"]`)?.scrollIntoView({
      block: "nearest",
      behavior: "smooth",
    });
  }, [dangO]);

  return (
    <div ref={khung} className="max-h-[62vh] min-h-0 flex-1 overflow-y-auto rounded-lg border border-border bg-bg">
      {cues.map((c, o) => (
        <button
          key={c.i}
          data-o={o}
          onClick={() => onChon(c.start)}
          className={clsx(
            "flex w-full gap-2 border-b border-border/50 px-2 py-1.5 text-left text-[12.5px] last:border-0",
            o === dangO ? "bg-accent/15" : "hover:bg-panel2/50",
          )}
        >
          <span className="shrink-0 font-mono text-[10.5px] text-muted">{c.start.toFixed(1)}</span>
          <span className="min-w-0 flex-1 whitespace-pre-wrap">
            {hien === "vi" ? (dangSua?.[c.i] ?? c.dich) : c.goc || "—"}
          </span>
          {c.sua_tay && <span className="shrink-0 text-[10px] text-accent">đã sửa</span>}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Kiểm bằng mắt trên trình duyệt thật**

```bash
cd apps/api && uvicorn src.main:app --port 8000 &
cd apps/worker && celery -A src.celery_app worker -Q download,media,upload -l info &
cd apps/web && pnpm dev
```

Mở `http://localhost:3000/library`, vào tab Chờ duyệt, mở một video. Kiểm đủ sáu thứ — đây là phần KHÔNG test tự động được, và bài học trong `docs/known-issues.md` là lỗi nặng chỉ lộ ra khi nhìn:

1. Video phát được, tua được.
2. Phụ đề hiện trên hình, đổi đúng lúc theo lời.
3. Bấm một dòng trong bảng → video nhảy đúng tới câu đó.
4. Câu đang phát được tô sáng và bảng tự cuộn theo.
5. Bật "Tiếng Việt" → nghe giọng lồng, hình tắt tiếng gốc, tua rồi phát lại vẫn khớp.
6. Gõ sửa một câu → chữ trên hình đổi NGAY, chưa cần lưu.

- [ ] **Step 5: Commit**

```bash
cd apps/web && pnpm lint --fix
git add apps/web/components/KhungDoiChieu.tsx apps/web/lib/api.ts apps/web/lib/types.gen.ts
git commit -m "feat(web): khung xem video kèm phụ đề nổi trên hình, đồng bộ bảng đối chiếu"
```

---

### Task 8: Gắn vào tab Chờ duyệt — thay bảng ghép sai bằng khung mới

**Files:**
- Modify: `apps/web/components/DuyetBanDichTab.tsx`

**Interfaces:**
- Consumes: `<KhungDoiChieu>` (Task 7), `api.doiChieu`, `api.dichLai` (Task 7)

- [ ] **Step 1: Đổi nguồn dữ liệu sang `/doi-chieu`**

Trong `DuyetBanDichTab.tsx`, hàm `DongDuyet`, THAY khối `useQuery` phụ đề và `useMemo` ghép theo chỉ số:

```tsx
  const { data: subs } = useQuery({ queryKey: ["subtitles", video.id, "tat-ca"], ... });
  const doi = useMemo(() => { ... vi.map((c, i) => ({ vi: c, zh: zh[i] ?? null })) ... }, [subs]);
```

bằng:

```tsx
  //: Ghép ở BACKEND theo thời gian. Bản cũ ghép theo CHỈ SỐ, mà bước chuẩn
  //: hoá phụ đề gộp/tách câu rồi đánh số lại — đo trên DB thật ngày
  //: 2026-08-20: 8/10 video lệch, video tệ nhất ghép lệch 7 giây.
  const { data: doi = [] } = useQuery({
    queryKey: ["doi-chieu", video.id],
    queryFn: () => api.doiChieu(video.id),
    enabled: mo,
  });
```

- [ ] **Step 2: Thay thẻ `<audio>` và bảng cũ bằng `<KhungDoiChieu>`**

Trong khối `{mo && (...)}`, thay phần "Nghe thử giọng đã khớp thời gian" và toàn bộ `<div className="max-h-96 overflow-y-auto ...">` bằng:

```tsx
          <KhungDoiChieu
            videoId={video.id}
            cues={doi}
            hien="vi"
            coDaiTieng
            dangSua={sua}
          />
```

Giữ nguyên khối nút "Lưu và đọc lại N câu" đã có.

- [ ] **Step 3: Thêm ô sửa và tích chọn dưới khung**

Dưới `<KhungDoiChieu>`, thêm bảng sửa gọn (chỉ những câu cần sửa mới bung ra ô nhập — 672 `<textarea>` cùng lúc làm trang khựng):

```tsx
          <div className="mt-3 max-h-72 overflow-y-auto rounded-lg border border-border">
            {doi.map((c) => (
              <div key={c.i} className="flex items-start gap-2 border-b border-border/50 px-2 py-1.5 last:border-0">
                <input
                  type="checkbox"
                  className="mt-1 shrink-0"
                  checked={tich.has(c.i)}
                  onChange={() =>
                    setTich((cu) => {
                      const moi = new Set(cu);
                      moi.has(c.i) ? moi.delete(c.i) : moi.add(c.i);
                      return moi;
                    })
                  }
                  aria-label={`Chọn câu ${c.i + 1} để dịch lại`}
                />
                <span className="w-1/2 shrink-0 whitespace-pre-wrap text-[12px] text-muted">
                  {c.goc || "—"}
                </span>
                <textarea
                  className={clsx(
                    "min-w-0 flex-1 resize-y rounded border bg-transparent px-1.5 py-0.5 text-[12.5px] outline-none",
                    sua[c.i] !== undefined
                      ? "border-accent/60 bg-accent/[0.07]"
                      : "border-transparent hover:border-border focus:border-accent",
                  )}
                  rows={1}
                  value={sua[c.i] ?? c.dich}
                  onChange={(e) =>
                    setSua((cu) => {
                      const { [c.i]: _bo, ...con_lai } = cu;
                      return e.target.value === c.dich ? con_lai : { ...cu, [c.i]: e.target.value };
                    })
                  }
                  aria-label={`Sửa câu ${c.i + 1}`}
                />
              </div>
            ))}
          </div>
```

Thêm state ở đầu `DongDuyet`:

```tsx
  const [tich, setTich] = useState<Set<number>>(new Set());
```

- [ ] **Step 4: Thêm hai nút dịch lại**

Dưới bảng sửa:

```tsx
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px]">
            {tich.size > 0 && (
              <button
                className="btn btn-sm"
                disabled={dichLai.isPending}
                onClick={() => dichLai.mutate({ chi_so: [...tich] })}
              >
                {dichLai.isPending ? "Đang gửi…" : `Dịch lại ${tich.size} câu`}
              </button>
            )}
            <button
              className="btn btn-sm ml-auto"
              disabled={dichLai.isPending}
              onClick={() => dichLai.mutate({})}
            >
              Dịch lại toàn bộ
            </button>
          </div>
```

và mutation, đặt cạnh `luu`:

```tsx
  const dichLai = useMutation({
    mutationFn: (body: { chi_so?: number[] }) => api.dichLai(video.id, body),
    onSuccess: () => {
      setTich(new Set());
      setSua({});
      queryClient.invalidateQueries({ queryKey: ["doi-chieu", video.id] });
      queryClient.invalidateQueries({ queryKey: ["videos"] });
      //: Dịch lại tiêu thêm lượt/token — kéo lại dải hạn mức cho khớp.
      queryClient.invalidateQueries({ queryKey: ["llm-usage"] });
    },
  });
```

- [ ] **Step 5: Sửa `luu` để làm mới bảng đối chiếu**

Trong mutation `luu`, đổi `queryClient.invalidateQueries({ queryKey: ["subtitles", video.id] })` thành:

```tsx
      queryClient.invalidateQueries({ queryKey: ["doi-chieu", video.id] });
```

- [ ] **Step 6: Kiểm bằng mắt**

Mở tab Chờ duyệt với video `bbba9781`. Kiểm:
1. Cột "Bản gốc" giờ ghép ĐÚNG — câu "Alo, hôm nay thế nào rồi?" đứng cạnh `喂 今天还怎么样啊`, không phải `好嘞`.
2. Tích 2 câu → nút "Dịch lại 2 câu" hiện ra, bấm thì có thông báo và worker chạy.
3. Sửa tay một câu, lưu, rồi bấm "Dịch lại toàn bộ" → câu đã sửa GIỮ NGUYÊN.

- [ ] **Step 7: Commit**

```bash
cd apps/web && pnpm lint --fix
git add apps/web/components/DuyetBanDichTab.tsx
git commit -m "feat(web): tab Chờ duyệt xem bản dịch trên video, dịch lại từng câu"
```

---

### Task 9: Gắn vào tab Chờ dịch — xem bản gốc trước khi bấm Dịch

**Files:**
- Modify: `apps/web/components/PendingVideoRow.tsx`
- Modify: `apps/api/src/services/video_service.py` (cho `doi_chieu` chạy được khi CHƯA dịch)
- Modify: `apps/api/tests/test_doi_chieu_api.py`

**Interfaces:**
- Consumes: `<KhungDoiChieu>` (Task 7)

- [ ] **Step 1: Viết test hỏng — chưa dịch vẫn xem được bản gốc**

Ở chỗ dừng thứ nhất chưa có phụ đề tiếng Việt, nhưng vẫn phải xem được câu tiếng Trung. Thay test `test_chua_dich_thi_bao_ro` trong `apps/api/tests/test_doi_chieu_api.py` bằng:

```python
def test_chua_dich_thi_tra_cau_GOC_de_xem_truoc(video) -> None:
    """Chỗ dừng thứ nhất chưa có bản dịch, nhưng vẫn phải xem được bản gốc.

    Đó chính là điểm của chỗ dừng này: xem rồi mới quyết định có dịch không và
    chọn model nào. Ném lỗi ở đây là bắt người dùng bấm Dịch mù.
    """
    zh = _sub("zh", [
        {"i": 0, "start": 0.0, "end": 1.0, "text": "你好"},
        {"i": 1, "start": 1.0, "end": 2.0, "text": "再见"},
    ])
    ra = video_service.doi_chieu(DbGia(video, [zh]), video.id)
    assert [r["goc"] for r in ra] == ["你好", "再见"]
    assert [r["dich"] for r in ra] == ["", ""]


def test_khong_co_phu_de_nao_thi_bao_ro(video) -> None:
    with pytest.raises(NotFound, match="chưa có phụ đề"):
        video_service.doi_chieu(DbGia(video, []), video.id)
```

- [ ] **Step 2: Chạy test cho chắc là hỏng**

Run: `cd apps/api && pytest tests/test_doi_chieu_api.py -v`
Expected: FAIL — `NotFound: ... chưa có bản dịch tiếng Việt`

- [ ] **Step 3: Sửa service**

Trong `video_service.doi_chieu`, thay khối kiểm và ghép:

```python
    if "vi" not in theo_lang:
        raise NotFound(f"Video {video_id} chưa có bản dịch tiếng Việt.")

    vi_cues = theo_lang["vi"]
```

bằng:

```python
    if "vi" not in theo_lang and "zh" not in theo_lang:
        raise NotFound(f"Video {video_id} chưa có phụ đề nào.")

    #: Chưa dịch thì lấy câu GỐC làm khung, cột dịch để rỗng — chỗ dừng thứ
    #: nhất cần xem bản gốc để quyết định có dịch không và chọn model nào.
    #: Ném lỗi ở đây là bắt người dùng bấm Dịch mù.
    if "vi" not in theo_lang:
        return [
            {
                "i": int(c["i"]),
                "start": float(c["start"]),
                "end": float(c["end"]),
                "dich": "",
                "goc": str(c["text"]),
                "sua_tay": False,
            }
            for c in theo_lang["zh"]
        ]

    vi_cues = theo_lang["vi"]
```

- [ ] **Step 4: Chạy test cho chắc là qua**

Run: `cd apps/api && pytest tests/test_doi_chieu_api.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Thêm nút mở khung xem vào dòng chờ dịch**

Trong `apps/web/components/PendingVideoRow.tsx`, thêm state và nút mở, rồi khung xem khi mở:

```tsx
  const [xem, setXem] = useState(false);
  const { data: doi = [] } = useQuery({
    queryKey: ["doi-chieu", video.id],
    queryFn: () => api.doiChieu(video.id),
    enabled: xem,
  });
```

Nút, đặt cạnh nút Dịch đã có:

```tsx
        <button className="btn btn-sm shrink-0" onClick={() => setXem(!xem)} aria-expanded={xem}>
          {xem ? "Thu lại" : "▶ Xem bản gốc"}
        </button>
```

Khung, đặt sau khối dòng chính:

```tsx
      {xem && (
        <div className="mt-3 border-t border-border pt-3">
          {/* Xem bản gốc TRƯỚC khi bấm Dịch: dịch là bước tốn hạn mức và
              tốn thời gian, mà tới đây mới biết video nói gì. */}
          <KhungDoiChieu videoId={video.id} cues={doi} hien="zh" />
        </div>
      )}
```

- [ ] **Step 6: Kiểm bằng mắt**

Mở tab Chờ dịch. Kiểm: bấm "Xem bản gốc" → video phát, phụ đề TIẾNG TRUNG nổi trên hình, bấm dòng nào nhảy tới đó, không có nút chọn tiếng (vì chưa có dải lồng tiếng).

Nếu tab Chờ dịch đang trống, dựng một video mới: dán link ở trang Thư viện rồi đợi pipeline dừng ở `review`.

- [ ] **Step 7: Chạy toàn bộ test**

Run: `cd apps/api && pytest -q && cd ../worker && pytest -q && cd ../web && pnpm test`
Expected: tất cả PASS

- [ ] **Step 8: Commit**

```bash
ruff format . && ruff check --fix . && cd apps/web && pnpm lint --fix
git add apps/web/components/PendingVideoRow.tsx apps/api/src/services/video_service.py apps/api/tests/test_doi_chieu_api.py
git commit -m "feat(web): xem bản gốc kèm phụ đề Trung trước khi bấm Dịch"
```

---

## Nghiệm thu kế hoạch A

Chạy hết và tự kiểm:

- [ ] `cd apps/api && pytest -q` — xanh
- [ ] `cd apps/worker && pytest -q` — xanh
- [ ] `cd apps/web && pnpm test && pnpm lint` — xanh
- [ ] Tab Chờ dịch: xem được video kèm phụ đề Trung trước khi bấm Dịch
- [ ] Tab Chờ duyệt: xem được video kèm bản dịch nổi trên hình, nghe được giọng lồng khớp hình
- [ ] Bảng đối chiếu video `bbba9781` ghép ĐÚNG câu (kiểm bằng mắt, mốc giây 105–110)
- [ ] Sửa tay một câu rồi "Dịch lại toàn bộ" — câu đã sửa còn nguyên
- [ ] Tích vài câu rồi "Dịch lại N câu" — chỉ những câu đó đổi
