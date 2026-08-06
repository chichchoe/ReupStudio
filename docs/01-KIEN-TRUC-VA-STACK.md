# Kiến trúc & Stack

---

## 1. Stack đã chốt

Không thay đổi giữa chừng. Nếu muốn đổi, đổi trước khi bắt đầu M1.

### Frontend

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Framework | **Next.js 15** (App Router) + TypeScript | Router tốt, dev experience nhanh, dễ deploy |
| CSS | **Tailwind CSS** + **shadcn/ui** | Mockup đã theo hệ màu này, shadcn cho sẵn dialog/table/toast |
| Gọi API | **TanStack Query v5** | Cache, refetch, optimistic update — bắt buộc cho danh sách video |
| State cục bộ | **Zustand** | Nhẹ, dùng cho trạng thái Editor (mask, timeline) |
| Realtime | **WebSocket** thuần qua `useWebSocket` hook tự viết | Không cần thư viện, chỉ nhận event tiến trình |
| Video preview | thẻ `<video>` + file proxy 540p | Không dùng thư viện player nặng |
| Vẽ mask | `<canvas>` overlay tự viết | Không có thư viện nào vừa đủ, tự viết ~200 dòng |
| Calendar | tự viết grid CSS | Thư viện calendar đều nặng và khó tuỳ biến |

### Backend

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| API | **FastAPI** + Pydantic v2 | Async tốt, tự sinh OpenAPI, cùng ngôn ngữ với phần AI |
| ORM | **SQLAlchemy 2.0** + Alembic | Migration nghiêm túc, không dùng SQLModel để tránh giới hạn |
| DB | **PostgreSQL 16** | JSONB cho mask/metadata, transaction chắc chắn |
| Queue | **Celery 5** + **Redis 7** | Nhiều hàng đợi riêng theo loại việc, retry sẵn có |
| Realtime | FastAPI WebSocket + Redis pub/sub | Worker publish tiến trình, API broadcast xuống FE |
| Storage | Filesystem local (mount volume) | Đơn giản; thêm MinIO/S3 sau nếu cần |
| Config | pydantic-settings + `.env` | Không hardcode gì |

### Media & AI

| Việc | Thư viện | Ghi chú |
|---|---|---|
| Tải video | **yt-dlp** (dùng như Python lib, không gọi CLI) | Cập nhật thường xuyên |
| Xử lý video | **FFmpeg 7** qua subprocess, wrapper tự viết | Không dùng `ffmpeg-python` — che mất lỗi |
| Nhận dạng giọng | **faster-whisper** (large-v3, `int8_float16`) | Nhanh hơn openai-whisper 4×, ít VRAM hơn |
| OCR tiếng Trung | **PaddleOCR** (`ch` model) | Tốt nhất cho chữ Hán trên video |
| Phát hiện logo | **OpenCV** (phương sai theo thời gian + `matchTemplate`) | Tự viết, ~150 dòng |
| Inpaint nhanh | FFmpeg `delogo` + OpenCV `inpaint` | Không cần GPU |
| Inpaint AI | **ProPainter** | Chạy như subprocess riêng, có timeout |
| Tách nhạc nền | **Demucs v4** | Chỉ dùng khi bật lồng tiếng |
| Dịch | LLM qua HTTP (Claude/GPT/Gemini) | Lớp `translator/` trừu tượng để đổi provider |
| TTS | ElevenLabs / FPT.AI, interface chung | Có fallback khi hết hạn mức |

### Hạ tầng

```
docker-compose.yml
├── postgres        (5432)
├── redis           (6379)
├── api             FastAPI · uvicorn · 8000
├── worker-cpu      Celery · queue: download, translate, upload, render
├── worker-gpu      Celery · queue: asr, vision  (chạy trên host có GPU)
├── beat            Celery beat · quét kênh nguồn theo lịch
└── web             Next.js · 3000
```

Worker GPU nên chạy **trực tiếp trên host** thay vì trong Docker để đỡ đau đầu với CUDA runtime. Docker cho phần còn lại.

---

## 2. Cấu trúc repo

```
reup-studio/
├── CLAUDE.md                    ← quy ước cho AI, copy từ 04-CLAUDE.md
├── docker-compose.yml
├── .env.example
│
├── apps/
│   ├── api/                     ← FastAPI
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── config.py            settings từ env
│   │   │   ├── db.py                engine, session
│   │   │   ├── models/              SQLAlchemy models — 1 file 1 bảng
│   │   │   ├── schemas/             Pydantic in/out — 1 file 1 domain
│   │   │   ├── routers/             endpoint — 1 file 1 domain
│   │   │   ├── services/            LOGIC NGHIỆP VỤ Ở ĐÂY
│   │   │   ├── ws/                  WebSocket manager
│   │   │   └── deps.py
│   │   ├── alembic/
│   │   └── tests/
│   │
│   ├── worker/                  ← Celery + toàn bộ xử lý media
│   │   ├── src/
│   │   │   ├── celery_app.py
│   │   │   ├── tasks/               task Celery — MỎNG, chỉ điều phối
│   │   │   ├── pipeline/            từng bước pipeline, hàm thuần
│   │   │   │   ├── download.py
│   │   │   │   ├── transcribe.py
│   │   │   │   ├── translate.py
│   │   │   │   ├── detect.py            dò watermark + sub
│   │   │   │   ├── inpaint.py
│   │   │   │   ├── tts.py
│   │   │   │   ├── shortform.py         crop 9:16, hook, chia tập
│   │   │   │   ├── antidup.py
│   │   │   │   ├── render.py
│   │   │   │   └── upload.py
│   │   │   ├── downloaders/         1 file 1 nền tảng nguồn
│   │   │   │   ├── base.py
│   │   │   │   ├── douyin.py
│   │   │   │   ├── bilibili.py
│   │   │   │   └── kuaishou.py
│   │   │   ├── publishers/          1 file 1 nền tảng đích
│   │   │   │   ├── base.py
│   │   │   │   ├── tiktok.py
│   │   │   │   ├── youtube.py
│   │   │   │   ├── facebook.py
│   │   │   │   └── instagram.py
│   │   │   ├── ffmpeg/              wrapper FFmpeg
│   │   │   └── progress.py          publish tiến trình lên Redis
│   │   └── tests/
│   │
│   └── web/                     ← Next.js
│       ├── app/
│       │   ├── (dashboard)/
│       │   │   ├── page.tsx                 Tổng quan
│       │   │   ├── pipelines/page.tsx       Luồng tự động
│       │   │   ├── sources/page.tsx         Nguồn Trung Quốc
│       │   │   ├── library/page.tsx         Thư viện
│       │   │   ├── editor/[id]/page.tsx     Editor
│       │   │   ├── channels/page.tsx        Kênh Việt Nam
│       │   │   ├── schedule/page.tsx        Lịch đăng
│       │   │   ├── stats/page.tsx
│       │   │   └── settings/page.tsx
│       │   └── layout.tsx
│       ├── components/
│       │   ├── ui/                  shadcn
│       │   ├── video/               VideoRow, StatusDots, Thumb
│       │   ├── editor/              MaskCanvas, MaskTimeline, PropPanel
│       │   └── schedule/            CalendarGrid, EventChip
│       ├── lib/
│       │   ├── api.ts               client gọi API, typed
│       │   ├── ws.ts                WebSocket hook
│       │   └── types.ts             SINH TỪ OPENAPI, không gõ tay
│       └── stores/
│
├── packages/
│   └── shared/                  ← enum, hằng số dùng chung (trạng thái, tên bước)
│
├── media/                       ← KHÔNG commit
│   ├── raw/{platform}/{video_id}/
│   ├── work/{video_id}/             audio, mask, sub, proxy
│   └── out/{video_id}/{platform}.mp4
│
└── docs/                        ← copy bộ kế hoạch này vào đây
```

---

## 3. Luồng dữ liệu

### Pipeline một video

```
                    ┌─────────────────────────────────────────────┐
                    │              CELERY CHAIN                    │
                    └─────────────────────────────────────────────┘

[Nguồn]  ──►  download  ──►  probe  ──►  transcribe  ──►  translate
              (cpu)          (cpu)       (GPU)            (cpu, gọi LLM)
                                             │
                    ┌────────────────────────┘
                    ▼
              detect_regions  ──►  inpaint  ──►  shortform  ──►  tts
              (GPU)                (GPU/cpu)     (cpu)          (cpu, gọi API)
                    │
                    ▼
              render_variants  ──►  qc_check  ──►  schedule  ──►  upload
              (cpu, FFmpeg)        (GPU nhẹ)      (cpu)          (cpu)
```

Mỗi bước:

- Nhận `video_id`, đọc trạng thái từ DB
- Ghi output ra `media/work/{video_id}/`
- Cập nhật `video.step` và publish tiến trình lên Redis channel `progress:{video_id}`
- Trả về `video_id` cho bước sau

**Quan trọng:** mỗi bước phải **idempotent** — chạy lại lần 2 với cùng input phải cho cùng kết quả và không hỏng gì. Kiểm tra file output đã tồn tại thì bỏ qua. Điều này cho phép retry một bước mà không phải chạy lại từ đầu.

### Realtime tiến trình

```
Worker ──publish──► Redis channel "progress:{video_id}"
                          │
                    API subscribe
                          │
                    WebSocket /ws
                          │
                    FE cập nhật thanh %
```

Không dùng polling. Không lưu tiến trình % vào DB (chỉ lưu bước và trạng thái).

### Luồng tự động (Pipeline)

```
Celery beat (mỗi 15 phút)
   │
   ├─► với mỗi source_channel đang bật, tới hạn quét:
   │      scan_source_channel(id)
   │         ├─ lấy danh sách video mới
   │         ├─ lọc theo filter_preset
   │         ├─ bỏ trùng (source_id / md5 / phash)
   │         ├─ kiểm tra license_status của nguồn  ← chặn ở đây nếu chưa có quyền
   │         └─ tạo Video + đưa vào chain xử lý
   │
   └─► với mỗi pipeline có video ở trạng thái READY:
          auto_schedule(pipeline_id)
             └─ tìm suất trống theo hạn ngạch kênh → tạo ScheduledPost
```

---

## 4. Quyết định thiết kế cần nhớ

### 4.1 Mask lưu theo phần trăm, không theo pixel

```python
# ĐÚNG
{"x": 0.62, "y": 0.05, "w": 0.34, "h": 0.05}

# SAI — vỡ khi đổi độ phân giải hoặc khi preview ở 540p
{"x": 670, "y": 96, "w": 367, "h": 96}
```

### 4.2 Một video → nhiều bản render

Một `Video` sinh ra nhiều `RenderVariant`, mỗi variant ứng với một nền tảng đích (TikTok, Shorts, FB Reels) vì giới hạn thời lượng và cấu hình khác nhau. Đừng thiết kế 1-1 giữa video và file output — sẽ phải đập đi làm lại ở M4.

### 4.3 Giới hạn nền tảng nằm trong DB, không trong code

Bảng `platform_limits` chỉnh được từ giao diện. Nền tảng đổi giới hạn vài lần một năm; hardcode nghĩa là phải deploy lại mỗi lần.

### 4.4 Tách rõ ba lớp

```
routers/     ← chỉ validate input, gọi service, trả response.  KHÔNG có logic.
services/    ← toàn bộ logic nghiệp vụ.  KHÔNG biết gì về HTTP.
models/      ← chỉ định nghĩa bảng.  KHÔNG có method nghiệp vụ.
```

Tương tự bên worker:

```
tasks/       ← chỉ điều phối, bắt lỗi, cập nhật trạng thái. 10–30 dòng.
pipeline/    ← hàm thuần nhận input trả output.  KHÔNG biết gì về Celery.
```

Lý do: hàm trong `pipeline/` test được bằng cách gọi trực tiếp, không cần dựng Celery.

### 4.5 Không gọi API bên ngoài trong request HTTP

Mọi thứ chạm mạng ngoài (tải video, gọi LLM, upload) đều phải qua Celery. Endpoint chỉ tạo job và trả `task_id`.

### 4.6 Type FE sinh từ OpenAPI

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o apps/web/lib/types.ts
```

Chạy lại mỗi khi đổi schema. Không gõ tay interface — sẽ lệch với backend và bạn sẽ không biết cho tới lúc chạy.

### 4.7 Đường dẫn file tập trung một chỗ

```python
# worker/src/paths.py — CHỈ Ở ĐÂY mới ghép đường dẫn
def raw_path(platform: str, vid: str) -> Path: ...
def work_dir(vid: str) -> Path: ...
def out_path(vid: str, target: str) -> Path: ...
```

Không rải `os.path.join` khắp nơi. Khi đổi cấu trúc lưu trữ chỉ sửa một file.

---

## 5. Biến môi trường

```bash
# .env.example
DATABASE_URL=postgresql+psycopg://reup:reup@localhost:5432/reup
REDIS_URL=redis://localhost:6379/0
MEDIA_ROOT=./media

# AI
LLM_PROVIDER=anthropic            # anthropic | openai | google
LLM_API_KEY=
LLM_MODEL=claude-sonnet-5
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda               # cuda | cpu
ENABLE_AI_INPAINT=true

# TTS
TTS_PROVIDER=elevenlabs           # elevenlabs | fptai | zalo
TTS_API_KEY=
TTS_FALLBACK_PROVIDER=fptai

# Nền tảng đăng
TIKTOK_CLIENT_KEY=
TIKTOK_CLIENT_SECRET=
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=

# Giới hạn an toàn
MONTHLY_BUDGET_USD=200
MAX_CONCURRENT_RENDERS=2
MAX_VIDEO_DURATION_SEC=600
```

---

## 6. Thứ tự dựng hạ tầng ở M0

1. `docker-compose.yml` với postgres + redis trước, chưa cần gì khác
2. FastAPI với đúng một endpoint `/health` → chạy được là commit
3. Alembic init + migration đầu tiên tạo bảng `videos`
4. Next.js với layout + sidebar tĩnh (copy CSS từ mockup)
5. Celery app với đúng một task `ping` → gọi được từ API là commit
6. WebSocket `/ws` gửi được một message thử

Sau bước 6 bạn có bộ khung chạy được đầu-cuối. Mọi thứ sau đó chỉ là điền vào.
