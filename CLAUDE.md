# CLAUDE.md

> Copy file này vào **gốc repo** với tên `CLAUDE.md`. Mọi phiên làm việc với AI đều phải cho đọc file này trước.

Dự án: **ReupStudio** — công cụ web tự động lấy video từ nền tảng Trung Quốc, dịch/lồng tiếng sang tiếng Việt, chuẩn hoá cho nền tảng video ngắn và đăng lên TikTok / YouTube Shorts / Facebook Reels / Instagram Reels.

---

## Lệnh hay dùng

```bash
# Chạy toàn bộ
docker compose up -d

# API (dev)
cd apps/api && uvicorn src.main:app --reload --port 8000

# Worker (dev)
cd apps/worker && celery -A src.celery_app worker -Q download,media,upload -l info
cd apps/worker && celery -A src.celery_app worker -Q gpu -l info -c 1   # GPU: concurrency 1
cd apps/worker && celery -A src.celery_app beat -l info

# Web
cd apps/web && pnpm dev

# Migration
cd apps/api && alembic revision --autogenerate -m "mô tả"
cd apps/api && alembic upgrade head

# Sinh lại type cho FE sau khi đổi API
cd apps/web && npx openapi-typescript http://localhost:8000/openapi.json -o lib/types.ts

# Test
cd apps/api && pytest
cd apps/worker && pytest
cd apps/web && pnpm test

# Format & lint (chạy trước khi commit)
ruff format . && ruff check --fix .
cd apps/web && pnpm lint --fix
```

---

## Kiến trúc — đọc kỹ, đừng phá

### Ba lớp backend

```
routers/    chỉ validate input, gọi service, trả response.   KHÔNG có logic nghiệp vụ.
services/   toàn bộ logic nghiệp vụ.                          KHÔNG biết gì về HTTP/FastAPI.
models/     chỉ định nghĩa bảng SQLAlchemy.                   KHÔNG có method nghiệp vụ.
```

### Hai lớp worker

```
tasks/      task Celery, 10–30 dòng. Chỉ điều phối, bắt lỗi, cập nhật trạng thái, publish tiến trình.
pipeline/   hàm thuần: nhận input → trả output.  KHÔNG import celery, KHÔNG chạm DB.
```

Lý do: hàm trong `pipeline/` gọi thẳng được từ script test, không cần dựng Redis + Celery.

### Quy tắc bất di bất dịch

1. **Mọi việc chạm mạng ngoài hoặc chạy >2 giây phải qua Celery.** Endpoint trả `202 {task_id}`, không bao giờ chờ.
2. **Toạ độ mask lưu theo phần trăm 0–1**, không bao giờ theo pixel.
3. **Mọi đường dẫn file đi qua `worker/src/paths.py`.** Không có `os.path.join` hay f-string ghép path ở chỗ khác.
4. **Mỗi bước pipeline phải idempotent.** Chạy lại lần 2 phải cho cùng kết quả; nếu file output đã tồn tại và hợp lệ thì bỏ qua.
5. **Giới hạn nền tảng đọc từ bảng `platform_limits`**, không hardcode trong code.
6. **Token nền tảng luôn mã hoá bằng Fernet** trước khi lưu. Không log token, không trả token qua API.
7. **Type frontend sinh từ OpenAPI.** Không gõ tay interface trùng với backend.
8. **Một video sinh nhiều `render_variants`** (một bản mỗi nền tảng đích). Không thiết kế 1-1.

---

## Quy ước code Python

```python
# Đúng: hàm thuần, type đầy đủ, dataclass cho input/output phức tạp
def detect_static_logo(
    frames: list[np.ndarray],
    *,
    min_area_ratio: float = 0.001,
    max_area_ratio: float = 0.15,
) -> list[MaskRegion]:
    ...
```

- Python 3.12, **type hint bắt buộc** cho mọi hàm public.
- Dùng `pathlib.Path`, không dùng chuỗi đường dẫn.
- Dùng `structlog`, log có ngữ cảnh: `log.info("download.done", video_id=vid, size_mb=12.4)`.
- **Không dùng `print`** ở code chạy thật.
- Exception có nghĩa: `class DownloadBlockedError(ReupError)`. Không `raise Exception("lỗi")`.
- Không nuốt lỗi im lặng. `except: pass` là cấm.
- Hằng số magic number đặt tên: `MAX_SUB_CHARS_PER_LINE = 42`.
- Format bằng `ruff format`, lint bằng `ruff check`.

### Gọi FFmpeg

```python
# Đúng: dựng list, log lệnh, kiểm mã trả về, đọc stderr khi lỗi
cmd = ["ffmpeg", "-y", "-i", str(src), *filters, str(dst)]
log.debug("ffmpeg.run", cmd=" ".join(cmd))
proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
if proc.returncode != 0:
    raise FFmpegError(proc.stderr[-2000:])
```

- **Không dùng `shell=True`.**
- Luôn có `timeout`.
- Khi lỗi, giữ 2000 ký tự cuối stderr — FFmpeg báo lỗi ở cuối.
- Ghi ra file tạm rồi `rename` sang tên chính thức, để tránh file dở dang bị coi là hợp lệ.

### Gọi API bên ngoài (LLM, TTS, nền tảng)

- Bọc trong lớp có interface chung (`translator/base.py`, `tts/base.py`, `publishers/base.py`).
- Luôn có: timeout, retry với backoff, giới hạn số lần, ghi `cost_logs`.
- Không bao giờ hardcode key — đọc từ `config.settings`.

---

## Quy ước code Frontend

```tsx
// Đúng: server component mặc định, client component chỉ khi cần tương tác
'use client'

export function MaskCanvas({ videoId, masks, onChange }: MaskCanvasProps) { ... }
```

- Next.js App Router, **server component là mặc định**; chỉ thêm `'use client'` khi cần state/event.
- Data fetching qua **TanStack Query**, không `useEffect` + `fetch`.
- Không gọi `fetch` trực tiếp trong component — mọi lời gọi qua `lib/api.ts`.
- State toàn cục dùng **Zustand**, chỉ cho trạng thái Editor. Còn lại để TanStack Query lo.
- Tailwind: dùng biến CSS đã định nghĩa (`bg-panel`, `text-muted`), không viết mã màu thô.
- Component >200 dòng thì tách.
- Tên file: `PascalCase.tsx` cho component, `camelCase.ts` cho tiện ích.
- Không dùng `localStorage` cho dữ liệu nghiệp vụ — chỉ cho tuỳ chọn hiển thị (bộ lọc, chế độ xem).

### Optimistic update

Với thao tác nhanh (kéo thả lịch, bật/tắt switch, duyệt video) dùng optimistic update của TanStack Query. Người dùng không nên phải chờ round-trip cho những việc này.

---

## Đặt tên

| Loại | Quy ước | Ví dụ |
|---|---|---|
| Bảng DB | số nhiều, snake_case | `scheduled_posts` |
| Cột | snake_case | `source_video_id` |
| Endpoint | số nhiều, kebab | `/api/v1/source-channels` |
| Task Celery | `động_từ_danh_từ` | `download_video`, `scan_source_channel` |
| File pipeline | danh từ đơn | `transcribe.py`, `inpaint.py` |
| Enum | UPPER_SNAKE trong class PascalCase | `VideoStatus.READY` |
| Component React | PascalCase | `MaskTimeline` |
| Hook | `use` + PascalCase | `useVideoProgress` |

---

## Test

**Bắt buộc test tự động** cho:

- Chuẩn hoá phụ đề (cắt dòng, gộp khung, giới hạn ký tự)
- Thuật toán rải lịch đăng
- Tính hạn ngạch kênh
- Chia tập theo giới hạn thời lượng
- Chuyển đổi toạ độ mask (% ↔ pixel)
- Parser metadata từ mỗi downloader (dùng fixture JSON đã lưu)

**Không cần test tự động** cho: FFmpeg, gọi API nền tảng, model AI. Những phần này kiểm bằng script chạy tay trên file thật, đặt trong `scripts/`.

```
scripts/
├── try_download.py      # thử tải 1 link
├── try_detect.py        # dò mask, xuất ảnh có vẽ khung để mắt người kiểm
├── try_render.py        # render 5 giây để xem nhanh
└── try_publish.py       # đăng thử lên kênh test
```

Mỗi task media mới nên kèm một script `try_*.py`.

---

## Git

```
feat(download): M1-WK-02 tải video Douyin không watermark
fix(render): sửa lệch audio 200ms khi đổi tốc độ
refactor(pipeline): tách logic chọn preset khỏi render.py
docs: cập nhật known-issues sau buổi test 20 video
```

- Một task = một commit.
- Không commit `media/`, `.env`, model weights, file test lớn.
- Branch `main` luôn phải chạy được.

---

## Điều KHÔNG được làm

- ❌ Thêm thư viện mới mà không hỏi. Danh sách đã chốt trong `docs/01-KIEN-TRUC-VA-STACK.md`.
- ❌ Đổi schema DB mà không tạo migration Alembic.
- ❌ Viết logic nghiệp vụ trong router hoặc trong task Celery.
- ❌ Hardcode giới hạn nền tảng, đường dẫn file, API key.
- ❌ Dùng `shell=True` với subprocess.
- ❌ Gọi model AI trực tiếp trong tiến trình worker chính (dùng subprocess riêng, có timeout).
- ❌ Polling API từ frontend để lấy tiến trình — đã có WebSocket.
- ❌ Tạo file mới ngoài phạm vi task đang làm.
- ❌ Sửa file `docs/` khi đang làm task code.

---

## Ngữ cảnh nghiệp vụ cần nhớ

- **Video dọc 9:16 là mặc định.** Mọi thứ tối ưu cho video ngắn, không phải video dài.
- **Phụ đề phải tránh vùng UI của nền tảng** (nút bên phải TikTok, caption dưới). Có bảng `platform_limits` mô tả vùng an toàn.
- **Watermark Douyin nhảy giữa 4 góc** theo chu kỳ vài giây — mask phải có timeline, không phải một vị trí cố định.
- **Một số video Trung Quốc có phụ đề cứng** cần xoá trước khi burn sub tiếng Việt lên.
- **`license_status` của kênh nguồn chặn luồng tự động.** Nguồn `unknown` không bao giờ được tự động xử lý — đây là chốt an toàn pháp lý, không được bỏ qua vì tiện.
- **Hook 3 giây đầu quyết định retention.** Đừng coi nhẹ bước này.

---

## Khi bí

Nếu spec trong `docs/` mâu thuẫn với code hiện có, **hỏi trước, đừng tự quyết**. Nếu một task hoá ra lớn hơn mô tả, dừng lại và đề xuất tách nhỏ thay vì làm một mạch 800 dòng.
