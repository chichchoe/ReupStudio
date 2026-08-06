# ReupStudio

Công cụ web tự động lấy video từ nền tảng Trung Quốc, dịch sang tiếng Việt và
(từ chặng M5) đăng lên các nền tảng video ngắn Việt Nam.

**Trạng thái hiện tại: hết chặng M1.** Dán link Douyin → tải → Whisper nhận dạng
tiếng Trung → LLM dịch → chuẩn hoá phụ đề → burn sub → tải file mp4 tiếng Việt về.

---

## Cài đặt nhanh

### 1. Yêu cầu

| Phần mềm | Phiên bản | Ghi chú |
|---|---|---|
| Python | 3.11+ | 3.10 vẫn chạy nhưng khuyến nghị 3.12 |
| Node | 22+ | cho giao diện web |
| FFmpeg | 5+ (khuyến nghị 7) | `brew install ffmpeg` |
| Docker | mới nhất | chạy PostgreSQL + Redis |
| GPU NVIDIA | ≥8GB VRAM | tuỳ chọn — không có thì Whisper chạy CPU (chậm hơn ~5×) |

### 2. Chuẩn bị

```bash
cp .env.example .env
make setup          # tạo venv, cài Python deps, npm install
make up             # bật PostgreSQL + Redis
make migrate        # tạo bảng
```

Cài thêm Whisper (nặng, tải model lần đầu vài GB):

```bash
.venv/bin/pip install -e "apps/worker[ai]"
```

Muốn dịch thật (mặc định đang dùng `mock` — chỉ thêm tiền tố `[VI]`):

```bash
# trong .env
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
```

### 3. Chạy — mở 3 terminal

```bash
make api        # http://localhost:8000/docs
make worker     # Celery
make web        # http://localhost:3000
```

Vào <http://localhost:3000/sources>, dán link Douyin, bấm **Thêm vào hàng đợi**,
rồi sang **Thư viện** xem tiến trình chạy realtime.

---

## Thử nhanh không cần Docker

Chạy toàn bộ pipeline trên một link, không cần Postgres/Redis/Celery:

```bash
cd apps/worker
python scripts/try_pipeline.py "https://v.douyin.com/xxxxx/"
```

Chỉ thử tải và xem metadata:

```bash
python scripts/try_download.py "https://v.douyin.com/xxxxx/"
```

---

## Cấu trúc

```
ReupStudio/
├── CLAUDE.md              quy ước cho AI viết code — đọc trước mọi phiên làm việc
├── docs/                  bộ kế hoạch đầy đủ (kiến trúc, DB, backlog 94 task, test)
├── packages/reup_core/    enum, model SQLAlchemy, đường dẫn file — dùng chung
├── apps/api/              FastAPI: router → service → model
├── apps/worker/           Celery: tasks/ (mỏng) → pipeline/ (hàm thuần)
├── apps/web/              Next.js 15 + Tailwind
└── media/                 raw/ work/ out/ — KHÔNG commit
```

Luồng xử lý một video:

```
download → probe → transcribe → translate → format_sub → render
  (cpu)     (cpu)    (GPU)        (LLM)       (cpu)       (FFmpeg)
```

Mỗi bước **idempotent**: chạy lại cho cùng kết quả, file đã có thì bỏ qua. Nhờ vậy
`POST /videos/{id}/retry?from_step=translate` không phải tải lại video.

---

## Kiểm thử

```bash
make test                    # 36 test cho phần logic thuần
cd apps/web && npm run build # kiểm type + build frontend
```

Test tự động chỉ bao phủ **logic thuần** (chuẩn hoá phụ đề, parser URL, chốt chặn
số dòng khi dịch, đường dẫn file). Phần FFmpeg và model AI kiểm bằng script trong
`apps/worker/scripts/` trên file thật — xem `docs/05-TEST-VA-VAN-HANH.md`.

---

## Lộ trình

| Chặng | Nội dung | Trạng thái |
|---|---|---|
| M0 | Hạ tầng: Docker, FastAPI, Celery, Next.js, migration | ✅ xong |
| M1 | Lát cắt dọc: link → dịch → burn sub → file mp4 | ✅ xong |
| M2 | Hàng đợi, theo dõi kênh nguồn, chống trùng pHash | ⬜ |
| M3 | Xoá watermark Douyin + phụ đề cứng | ⬜ |
| M4 | Chuẩn hoá 9:16, hook 3 giây, chia tập | ⬜ |
| M5 | Đăng lên TikTok / Shorts / Reels | ⬜ |
| M6 | Lịch đăng, hạn ngạch, khung giờ vàng | ⬜ |
| M7 | Luồng tự động hoàn toàn | ⬜ |
| M8 | Lồng tiếng, chống trùng, thống kê | ⬜ |

Chi tiết 94 task trong `docs/03-BACKLOG-CONG-VIEC.md`.

---

## Lưu ý về bản quyền

Reup video của creator khác mà không có phép có thể khiến video bị gỡ, kênh bị
strike hoặc mất quyền kiếm tiền. Xoá watermark **không** giải quyết vấn đề — về mặt
pháp lý nó thường bị coi là tình tiết tăng nặng.

Hệ thống có trường `license_status` cho mỗi kênh nguồn (sẽ dùng ở M2/M7). Nguồn ở
trạng thái `unknown` **không bao giờ được luồng tự động xử lý** — đây là chốt an
toàn cố ý, đừng bỏ qua vì tiện.

Ba hướng làm bền: xin phép/mua license từ creator gốc, nội dung có tính biến đổi
thật (bình luận, phân tích), hoặc dùng nguồn có license mở.
# ReupStudio
