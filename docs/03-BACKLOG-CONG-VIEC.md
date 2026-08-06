# Backlog công việc

**Đơn vị ước tính: "phiên"** = một buổi làm việc tập trung 2–3 giờ với AI hỗ trợ.

Mã task: `{chặng}-{lớp}-{số}`. Lớp: `INF` hạ tầng · `BE` backend · `WK` worker · `FE` frontend · `QA` kiểm thử.

Quy ước trạng thái khi làm: `[ ]` chưa làm · `[~]` đang làm · `[x]` xong.

---

# M0 — Nền móng (3–5 ngày)

Mục tiêu: `docker compose up` chạy, API sống, FE hiện được sidebar, Celery nhận được task.

| Mã | Việc | Phụ thuộc | Ước tính | Xong khi |
|---|---|---|---|---|
| `M0-INF-01` | Khởi tạo monorepo, `.gitignore`, `.env.example`, copy `CLAUDE.md` vào gốc | — | 0.5 | `git log` có commit đầu, `media/` không bị track |
| `M0-INF-02` | `docker-compose.yml`: postgres 16 + redis 7 | INF-01 | 0.5 | `psql` và `redis-cli` kết nối được từ host |
| `M0-BE-01` | FastAPI skeleton: `main.py`, `config.py` (pydantic-settings), `/health` | INF-02 | 1 | `curl localhost:8000/health` → `{"ok":true,"db":true,"redis":true}` |
| `M0-BE-02` | SQLAlchemy 2.0 + Alembic, migration tạo bảng `videos`, `job_runs`, `subtitles` | BE-01 | 1 | `alembic upgrade head` chạy sạch, `\dt` thấy 3 bảng |
| `M0-WK-01` | Celery app, 4 queue (`download`,`media`,`gpu`,`upload`), task `ping` | INF-02 | 1 | Gọi `ping.delay()` từ shell, worker log ra "pong" |
| `M0-BE-03` | WebSocket `/ws` + Redis pub/sub bridge, gửi được message thử | BE-01 | 1 | Mở `wscat`, publish vào Redis, thấy message ở client |
| `M0-FE-01` | Next.js 15 + Tailwind + shadcn, layout + sidebar + routing 8 trang rỗng | INF-01 | 1.5 | Bấm sidebar chuyển trang, giao diện giống mockup |
| `M0-FE-02` | `lib/api.ts` + sinh type từ OpenAPI + hook `useWebSocket` | BE-01, BE-03, FE-01 | 1 | Trang Tổng quan hiện được `/health`, WS hiện "connected" |
| `M0-INF-03` | Dockerfile cho api + worker + web, compose chạy full | tất cả trên | 1 | `docker compose up` một lệnh chạy hết |

**Không làm ở M0:** authentication, phân quyền, CI/CD, test tự động. Bạn dùng một mình trên máy mình.

---

# M1 — Lát cắt dọc đầu tiên (1–1.5 tuần)

Mục tiêu: **dán 1 link Douyin → nhận về file mp4 có phụ đề tiếng Việt xem được.** Xấu cũng được.

| Mã | Việc | Phụ thuộc | Ước tính | Xong khi |
|---|---|---|---|---|
| `M1-WK-01` | `paths.py` — mọi đường dẫn file tập trung một chỗ | M0-WK-01 | 0.5 | Không có `os.path.join` nào ngoài file này |
| `M1-WK-02` | `downloaders/base.py` + `douyin.py` qua yt-dlp, lấy no-watermark nếu có | WK-01 | 1.5 | Tải được 5/5 link mẫu, có metadata gốc |
| `M1-WK-03` | `ffmpeg/probe.py` — đọc duration, w/h, fps, có audio không | WK-01 | 0.5 | Trả đúng thông tin cho cả video dọc và ngang |
| `M1-WK-04` | `pipeline/transcribe.py` — faster-whisper large-v3, output cues chuẩn | WK-03 | 1.5 | Video 60s ra SRT tiếng Trung, timestamp lệch <0.3s |
| `M1-WK-05` | `pipeline/translate.py` — LLM dịch cả đoạn, giữ số dòng, có glossary | WK-04 | 1.5 | 5 video: số dòng vào = số dòng ra, không dòng rỗng |
| `M1-WK-06` | `pipeline/subtitle_format.py` — chuẩn hoá ≤2 dòng, ≤42 ký tự, gộp khung ngắn | WK-05 | 1 | Test tự động cho 6 trường hợp biên |
| `M1-WK-07` | `pipeline/render.py` — burn sub bằng FFmpeg, font Việt có dấu | WK-06 | 1.5 | Chữ đủ dấu, không tràn viền, đọc rõ trên nền sáng và tối |
| `M1-WK-08` | Task Celery `process_video` nối chain 6 bước, ghi `job_runs` | WK-02…07 | 1 | Một lệnh chạy hết, job_runs có 6 dòng |
| `M1-BE-01` | `POST /videos/from-links` + `GET /videos` + `GET /videos/{id}` | M0-BE-02 | 1 | Dán link → tạo record → trigger Celery |
| `M1-FE-01` | Trang Nguồn: ô dán link, gọi API, hiện danh sách đang tải | M1-BE-01 | 1 | Dán link, thấy video xuất hiện ở Thư viện |
| `M1-FE-02` | Trang Thư viện: bảng video, 6 chấm trạng thái, nút tải file kết quả | M1-BE-01 | 1.5 | Bấm tải → mở được mp4 có sub tiếng Việt |
| `M1-QA-01` | Chạy tay 10 video mẫu đủ loại, ghi lại lỗi vào `docs/known-issues.md` | tất cả | 1 | Có danh sách vấn đề thật để làm M2 |

> 🎉 **Cột mốc:** hết M1 bạn đã có công cụ dịch video Trung → Việt tự động. Chưa đăng được, nhưng đã dùng được.

### Chi tiết `M1-WK-05` — Dịch bằng LLM

Đây là task dễ làm sai nhất. Ba điểm bắt buộc:

1. **Gửi cả đoạn, không gửi từng dòng.** Gửi 20–30 cue một lần kèm chỉ số, yêu cầu trả về JSON có đúng chỉ số đó. Dịch từng dòng rời rạc cho ra bản dịch không có ngữ cảnh, rất tệ với phim.
2. **Kiểm tra số lượng trả về.** Nếu LLM trả thiếu/thừa dòng thì retry với nhiệt độ thấp hơn; retry 2 lần vẫn sai thì dịch từng dòng làm fallback.
3. **Glossary ép cứng.** Tên riêng, xưng hô (总裁 → "tổng tài") phải nằm trong prompt, không để LLM tự quyết mỗi lần một kiểu.

```python
# Hình dung interface, không phải code hoàn chỉnh
def translate_cues(cues: list[Cue], tone: str, glossary: dict[str,str]) -> list[Cue]:
    for batch in chunk(cues, 25):
        out = llm_translate_batch(batch, tone, glossary)
        assert len(out) == len(batch), "LLM trả sai số dòng"
```

---

# M2 — Hàng đợi & giao diện thật (1 tuần)

| Mã | Việc | Phụ thuộc | Ước tính | Xong khi |
|---|---|---|---|---|
| `M2-WK-01` | `progress.py` — publish % lên Redis từ mọi bước | M1-WK-08 | 1 | Mỗi bước bắn ít nhất 5 mốc % |
| `M2-BE-01` | WS broadcast tiến trình theo `video_id` + kênh `queue` | M2-WK-01 | 1 | 2 tab trình duyệt cùng thấy % cập nhật |
| `M2-FE-01` | Thanh tiến trình realtime ở Thư viện + Tổng quan | M2-BE-01 | 1 | Không có polling nào trong Network tab |
| `M2-BE-02` | Retry theo bước: `POST /videos/{id}/retry?from_step=` | M1-WK-08 | 1 | Retry từ `translate` không tải lại video |
| `M2-BE-03` | Bulk action: approve / delete / apply_preset / assign_channels | M1-BE-01 | 1 | Chọn 10 video, một lệnh áp hết |
| `M2-FE-02` | Chọn nhiều + thanh hành động hàng loạt + lọc chip + tìm kiếm | M2-BE-03 | 1.5 | Giống mockup, lọc và tìm chạy đúng |
| `M2-BE-04` | Bảng `presets` + CRUD + seed 4 preset mặc định | M0-BE-02 | 1 | Đổi preset không cần sửa code |
| `M2-BE-05` | Bảng `source_channels` có `license_status`, CRUD, `/resolve` | M0-BE-02 | 1.5 | Dán link kênh → hiện tên, follower, video mẫu |
| `M2-WK-02` | Chống trùng: md5 + pHash, bỏ qua video đã có | M1-WK-02 | 1 | Tải lại link cũ → trả về video cũ, không tạo mới |
| `M2-FE-03` | Trang Nguồn tab "Kênh theo dõi" + modal thêm kênh có chọn license | M2-BE-05 | 1 | Thêm được kênh, thấy trong bảng |
| `M2-QA-01` | Chạy 30 video liên tục, kiểm rò rỉ bộ nhớ và file tạm | tất cả | 1 | RAM không tăng dần, `media/work` không phình vô hạn |

---

# M3 — Xoá watermark & phụ đề cứng (1.5–2 tuần)

Chặng khó nhất. Làm chế độ nhanh trước, AI sau.

| Mã | Việc | Phụ thuộc | Ước tính | Xong khi |
|---|---|---|---|---|
| `M3-WK-01` | `detect/static_logo.py` — phương sai theo thời gian trên 48 khung | M1-WK-03 | 2 | Tìm đúng logo tĩnh ≥90% trong 20 video mẫu |
| `M3-WK-02` | `detect/template.py` — thư viện logo mẫu 5 nền tảng + matchTemplate | WK-01 | 1.5 | Phân biệt được logo Douyin/Bilibili/Kuaishou |
| `M3-WK-03` | `detect/douyin_dynamic.py` — bám logo động 4 góc, sinh timeline | WK-02 | 2 | Không sót khung nào có logo, sai vị trí <5px |
| `M3-WK-04` | `detect/hardsub.py` — PaddleOCR text detection vùng dưới, gom theo thời gian | M1-WK-03 | 2 | Nhận đúng ≥90% ký tự trên phụ đề nét |
| `M3-WK-05` | `inpaint/fast.py` — FFmpeg delogo + OpenCV inpaint, mask động | WK-03, WK-04 | 1.5 | Render 60s trong ≤90s, không sót viền |
| `M3-WK-06` | `inpaint/ai.py` — ProPainter subprocess, timeout, fallback về fast | WK-05 | 2 | Không thấy dấu vết khi phát tốc độ thường |
| `M3-WK-07` | `qc/residual_check.py` — kiểm sót logo/chữ trên bản output | WK-06 | 1 | Bắt được ≥95% ca xử lý thất bại |
| `M3-BE-01` | CRUD `mask_regions` + `POST /videos/{id}/detect` + `/preview` | M0-BE-02 | 1.5 | Dò xong trả mask kèm confidence |
| `M3-FE-01` | `MaskCanvas` — vẽ/kéo/resize mask trên canvas, toạ độ % | M3-BE-01 | 2.5 | Vẽ mượt trên 1080p, lưu đúng tỷ lệ |
| `M3-FE-02` | `MaskTimeline` — thanh thời gian mask, chỉnh khoảng áp dụng | M3-FE-01 | 1.5 | Kéo hai đầu đổi được time_range |
| `M3-FE-03` | Panel thuộc tính mask + preset theo nguồn + so sánh trước/sau | M3-FE-01 | 1.5 | Đổi mode → xem trước 5s thấy khác biệt |
| `M3-QA-01` | Bộ 20 video mẫu đủ loại nền, đo tỷ lệ dò đúng và thời gian xử lý | tất cả | 1.5 | Có bảng số liệu thật để quyết bật/tắt AI inpaint |

### Chi tiết `M3-WK-01` — Dò logo tĩnh

Ý tưởng: pixel thuộc logo gần như không đổi suốt video, pixel thuộc cảnh thì đổi liên tục.

```
1. Trích 48 khung rải đều           → mảng (48, H, W)
2. Chuyển xám, tính std theo trục thời gian → ảnh (H, W)
3. Ngưỡng: std < ngưỡng → ứng viên
4. Morphology: dilate rồi erode để nối vùng rời
5. Lọc: bỏ vùng >15% khung, <0.1% khung, ưu tiên vùng trong 4 góc
6. Đối chiếu template → tăng confidence
```

Điểm dễ sai: video có cảnh tĩnh dài (phỏng vấn, nền trơn) sẽ cho vùng std thấp rất lớn. Bước 5 lọc theo diện tích và vị trí là bắt buộc.

### Chi tiết `M3-WK-06` — Inpaint AI

- Chạy **subprocess riêng**, không import vào tiến trình worker — model chiếm VRAM và không giải phóng sạch.
- Đặt **timeout cứng** (ví dụ 20× thời lượng video). Quá thì kill và fallback về `inpaint_fast`.
- Xử lý theo **cụm khung** (chunk 30–60 khung) để không tràn VRAM với video dài.
- Đo và log thời gian vào `job_runs.meta` — bạn cần số liệu này để quyết định có dùng nổi không.

---

# M4 — Chuẩn hoá video ngắn (1 tuần)

| Mã | Việc | Phụ thuộc | Ước tính | Xong khi |
|---|---|---|---|---|
| `M4-BE-01` | Bảng `platform_limits` + seed + CRUD, UI chỉnh được | M0-BE-02 | 1 | Đổi giới hạn không cần deploy |
| `M4-WK-01` | `shortform/reframe.py` — ngang → dọc: crop bám chủ thể / nền blur | M1-WK-03 | 2 | Chủ thể không bị cắt mất đầu trong 15/20 mẫu |
| `M4-WK-02` | `shortform/safe_area.py` — đẩy phụ đề khỏi vùng UI từng nền tảng | M4-BE-01 | 1 | Sub không nằm dưới caption TikTok |
| `M4-WK-03` | `shortform/hook.py` — chèn text hook 3s đầu, cắt đoạn mở đầu chậm | M1-WK-07 | 1.5 | Hook hiện đúng 0–3s, không đè sub |
| `M4-WK-04` | `shortform/split.py` — chia tập theo `max_duration_sec`, cắt ở khoảng lặng | M4-BE-01 | 1.5 | Video 4 phút → 3 tập Shorts, không cắt giữa câu |
| `M4-WK-05` | `render.py` sinh nhiều `render_variants` theo nền tảng đích | M4-WK-01…04 | 1.5 | 1 video → 3 file đúng chuẩn 3 nền tảng |
| `M4-BE-02` | API `/videos/{id}/render` nhận nhiều target, trả variants | M4-WK-05 | 1 | Gọi 1 lần render đủ 3 bản |
| `M4-FE-01` | Tab "Chuẩn hoá video ngắn" trong Editor + bảng giới hạn + preview vùng an toàn | M4-BE-01 | 2 | Giống mockup, đổi giá trị lưu được |
| `M4-QA-01` | Đối chiếu file output với giới hạn thật của từng nền tảng | tất cả | 1 | Upload thử tay 1 file mỗi nền tảng, không bị từ chối |

---

# M5 — Đăng lên nền tảng VN (1.5–2 tuần)

Chặng có nhiều rủi ro ngoài tầm kiểm soát (duyệt app). Bắt đầu xin quyền từ M0.

| Mã | Việc | Phụ thuộc | Ước tính | Xong khi |
|---|---|---|---|---|
| `M5-BE-01` | Bảng `publish_channels`, mã hoá token bằng Fernet | M0-BE-02 | 1.5 | Token không đọc được trong DB dump |
| `M5-BE-02` | OAuth flow chung: `/oauth-url` + `/oauth-callback` + refresh tự động | M5-BE-01 | 2 | Kết nối được 1 kênh YouTube thật |
| `M5-WK-01` | `publishers/base.py` — interface chung: `upload(variant, channel, meta)` | M5-BE-01 | 1 | Thêm nền tảng mới chỉ cần 1 file |
| `M5-WK-02` | `publishers/youtube.py` — resumable upload, set title/desc/tag/privacy | M5-WK-01 | 2 | Đăng thật 1 Short lên kênh test |
| `M5-WK-03` | `publishers/tiktok.py` — Content Posting API | M5-WK-01 | 2 | Đăng thật 1 video lên tài khoản test |
| `M5-WK-04` | `publishers/facebook.py` + `instagram.py` — Graph API Reels | M5-WK-01 | 2 | Đăng thật lên Page và IG business |
| `M5-WK-05` | Retry + resume khi mất mạng, giới hạn băng thông | M5-WK-02 | 1.5 | Ngắt mạng 30s giữa chừng vẫn xong |
| `M5-BE-03` | Template đăng bài theo kênh (biến `{tiêu_đề}`, `{tác_giả_gốc}`…) | M5-BE-01 | 1 | Đổi template áp ngay cho bài chưa đăng |
| `M5-FE-01` | Trang Kênh: lưới thẻ, modal kết nối, trạng thái token | M5-BE-02 | 1.5 | Kết nối kênh mới từ UI, thấy avatar và follower |
| `M5-FE-02` | Tab "Đăng bài" trong Editor: tiêu đề, mô tả, hashtag, chọn kênh, thumbnail | M5-BE-03 | 1.5 | Bấm đăng → video lên thật |
| `M5-BE-04` | Sinh tiêu đề/mô tả/hashtag bằng LLM, 5 phương án | M1-WK-05 | 1 | Không vượt giới hạn ký tự nền tảng |
| `M5-QA-01` | Đăng thật 10 video lên 4 nền tảng, ghi lại mọi lỗi API | tất cả | 1.5 | Có bảng mã lỗi và cách xử lý |

> 🎉 **Cột mốc:** hết M5 hệ thống đã dùng được thật — lấy video Trung Quốc về, xử lý, đăng lên TikTok/Shorts bằng tay qua giao diện.

---

# M6 — Lịch đăng & hạn ngạch (1 tuần)

| Mã | Việc | Phụ thuộc | Ước tính | Xong khi |
|---|---|---|---|---|
| `M6-BE-01` | Bảng `scheduled_posts` + CRUD + kiểm tra xung đột hạn ngạch | M5-BE-01 | 1.5 | Không cho vượt `daily_quota` |
| `M6-WK-01` | Celery beat quét `scheduled_posts` mỗi phút, đẩy job upload | M6-BE-01 | 1 | Bài đăng đúng ±2 phút so với giờ hẹn |
| `M6-BE-02` | Thuật toán rải tự động: khung giờ vàng, giãn cách tối thiểu, đa kênh | M6-BE-01 | 2 | 15 video rải vào 5 ngày, không vi phạm ràng buộc |
| `M6-BE-03` | `GET /stats/golden-hours` tính từ `post_metrics` thật | M6-BE-01 | 1 | Có dữ liệu thì dùng, chưa có thì dùng mặc định |
| `M6-FE-01` | `CalendarGrid` tuần/tháng, kéo thả đổi giờ | M6-BE-01 | 2 | Kéo thả gọi PATCH, cập nhật lạc quan |
| `M6-FE-02` | Modal rải tự động + danh sách chờ xếp lịch | M6-BE-02 | 1.5 | Bấm rải → lịch điền đầy, có toast báo |
| `M6-QA-01` | Test hạn ngạch: cố tình xếp vượt, kiểm hệ thống chặn đúng | tất cả | 1 | Không có cách nào lách qua UI |

### Chi tiết `M6-BE-02` — Thuật toán rải tự động

```
Input:  danh sách video sẵn sàng, danh sách kênh, cấu hình lịch
Output: danh sách (variant, channel, thời điểm)

1. Sinh tập suất trống cho mỗi kênh trong N ngày tới:
     với mỗi ngày, với mỗi giờ trong allowed_hours:
        nếu chưa đủ daily_quota và cách bài gần nhất ≥ min_gap → là suất trống
2. Chấm điểm mỗi suất: giờ vàng +10, giờ thường +0, quá muộn -5
3. Sắp video theo điểm dự đoán (view nguồn, hiệu quả kênh nguồn) giảm dần
4. Ghép tham lam: video điểm cao nhất → suất điểm cao nhất còn trống
5. Ràng buộc chéo: cùng một video lên 2 kênh phải cách ≥6h
6. Trả về kèm danh sách xung đột không xếp được
```

Viết hàm này **thuần** (không chạm DB) rồi test bằng dữ liệu giả — đây là chỗ dễ sai logic nhất và dễ test nhất.

---

# M7 — Luồng tự động (1–1.5 tuần)

| Mã | Việc | Phụ thuộc | Ước tính | Xong khi |
|---|---|---|---|---|
| `M7-BE-01` | Bảng `pipelines` + `pipeline_targets` + CRUD | M2-BE-05, M5-BE-01 | 1.5 | Tạo được luồng từ API |
| `M7-WK-01` | `scan_source_channel` — quét kênh mới, lọc, chặn nguồn `license_status=unknown` | M2-BE-05 | 2 | Nguồn chưa có quyền không bao giờ vào hàng đợi |
| `M7-WK-02` | Celery beat lịch quét theo `scan_interval_min` từng kênh | M7-WK-01 | 1 | Kênh chu kỳ 6h được quét đúng 6h/lần |
| `M7-WK-03` | Nối chain: quét → xử lý → render → auto_schedule | M6-BE-02, M7-WK-01 | 1.5 | Không cần thao tác tay nào từ lúc có video mới |
| `M7-BE-02` | Cơ chế duyệt: `require_approval` chặn ở trạng thái REVIEW | M7-BE-01 | 1 | Bật/tắt đổi hành vi ngay |
| `M7-FE-01` | Trang "Luồng tự động": danh sách, sơ đồ luồng, bật/tắt, số liệu | M7-BE-01 | 2 | Giống mockup |
| `M7-FE-02` | Wizard 6 bước tạo luồng | M7-BE-01 | 2.5 | Tạo luồng hoàn chỉnh không rời modal |
| `M7-QA-01` | Chạy 1 luồng thật 48 giờ liên tục, không can thiệp | tất cả | 1 | Có video tự đăng lên đúng lịch, log sạch |

> 🎉 **Cột mốc:** hết M7 bạn chỉ cần thêm kênh nguồn một lần, phần còn lại tự chạy.

---

# M8 — Lồng tiếng, chống trùng, thống kê (2 tuần)

| Mã | Việc | Phụ thuộc | Ước tính | Xong khi |
|---|---|---|---|---|
| `M8-WK-01` | `tts/base.py` + ElevenLabs + FPT.AI, fallback khi hết hạn mức | M1-WK-06 | 2 | Hết quota nhà A tự chuyển nhà B |
| `M8-WK-02` | Đồng bộ TTS với timeline: nén/giãn, cảnh báo lệch >25% | M8-WK-01 | 2 | Không đoạn nào đè lên câu sau |
| `M8-WK-03` | Demucs tách vocal, ducking nhạc nền | M8-WK-01 | 1.5 | Không nghe thấy giọng Trung sót lại |
| `M8-WK-04` | Cache TTS theo câu, sửa 1 câu chỉ sinh lại câu đó | M8-WK-01 | 1 | Sửa 1 dòng không tốn tiền cho cả video |
| `M8-WK-05` | `antidup.py` — 12 kỹ thuật, preset, ngẫu nhiên hoá tham số | M4-WK-05 | 2 | 2 video cùng nguồn ra pHash khác nhau |
| `M8-FE-01` | Tab Âm thanh + tab Chống trùng trong Editor | M8-WK-01, WK-05 | 2 | Giống mockup |
| `M8-BE-01` | Thu số liệu: YouTube Analytics + TikTok API, chạy hằng ngày | M5-BE-02 | 2 | `post_metrics` có dữ liệu sau 24h |
| `M8-BE-02` | Endpoint thống kê: theo nền tảng / nguồn / preset / chi phí | M8-BE-01 | 1.5 | Số khớp với dashboard nền tảng ±5% |
| `M8-FE-02` | Trang Thống kê đầy đủ | M8-BE-02 | 2 | Giống mockup |
| `M8-BE-03` | Phát hiện claim/strike, tự pause kênh, báo Telegram | M5-BE-02 | 1.5 | Claim phát hiện trong ≤6h, kênh dừng ngay |
| `M8-BE-04` | `cost_logs` + hạn mức chi tiêu cứng, dừng luồng khi vượt | M1-WK-05 | 1 | Vượt $200 → mọi pipeline tự tắt |
| `M8-INF-01` | Dọn file tự động, cảnh báo dung lượng, backup DB | M0-INF-02 | 1 | File thô >14 ngày tự xoá |

---

# Việc làm xuyên suốt (không thuộc chặng nào)

| Mã | Việc | Khi nào |
|---|---|---|
| `X-01` | Cập nhật `docs/known-issues.md` sau mỗi buổi test | Liên tục |
| `X-02` | Smoke test downloader chạy hằng ngày (nền tảng TQ hay đổi API) | Từ M2 |
| `X-03` | Ghi lại thời gian xử lý thật vào `job_runs` và xem định kỳ | Từ M1 |
| `X-04` | Rà soát `license_status` các nguồn đang dùng | Hằng tháng |
| `X-05` | Cập nhật `platform_limits` khi nền tảng đổi chính sách | Hằng quý |

---

# Prompt mẫu cho từng loại task

### Task backend đơn giản

> Làm task **M1-BE-01** trong `docs/03-BACKLOG-CONG-VIEC.md`.
> Đọc trước: `CLAUDE.md`, phần "Videos" trong `docs/02-DATABASE-VA-API.md`.
> Chỉ tạo/sửa: `apps/api/src/routers/videos.py`, `apps/api/src/schemas/video.py`, `apps/api/src/services/video_service.py`.
> Không sửa model, không tự thêm thư viện.
> Xong thì cho tôi lệnh curl để test từng endpoint.

### Task xử lý media (rủi ro cao)

> Làm task **M3-WK-01**. Đọc `CLAUDE.md` và mục "Chi tiết M3-WK-01".
> Trước khi viết code, mô tả cho tôi thuật toán bằng lời và liệt kê 3 trường hợp nó sẽ sai. Đợi tôi duyệt rồi mới viết.
> Viết hàm thuần trong `apps/worker/src/pipeline/detect/static_logo.py`, không phụ thuộc Celery, không chạm DB.
> Kèm script `scripts/try_detect.py` để tôi chạy thử trên 1 file mp4 và xem mask vẽ đè lên ảnh.

### Task frontend

> Làm task **M3-FE-01**. Đọc `CLAUDE.md`.
> Tham khảo giao diện trong `docs/mockup-web-app-v2.html` — giữ đúng hệ màu và bố cục, nhưng viết lại bằng React + Tailwind theo quy ước dự án.
> Component đặt ở `apps/web/components/editor/MaskCanvas.tsx`.
> Toạ độ mask lưu theo phần trăm (0–1), không theo pixel.
> Không gọi API trực tiếp trong component — dùng hook trong `lib/api.ts`.

### Khi cần sửa lỗi

> Video `abc-123` bị lệch audio 400ms sau khi lồng tiếng.
> Đọc `apps/worker/src/pipeline/tts.py` và `job_runs` của video này.
> Đừng sửa gì vội — trước tiên nêu 3 giả thuyết nguyên nhân, xếp theo khả năng, và cho tôi biết cần xem log/dữ liệu gì để xác nhận.

### Khi refactor

> Đọc `apps/worker/src/pipeline/render.py`.
> File này đang 400 dòng và trộn lẫn dựng lệnh FFmpeg với logic chọn preset.
> Đề xuất cách tách, nêu ưu nhược từng cách. Chưa viết code.

---

# Bảng tổng hợp khối lượng

| Chặng | Số task | Tổng phiên | Ước tính tuần (15–20h/tuần) |
|---|---|---|---|
| M0 | 9 | 8.5 | 0.7 |
| M1 | 12 | 14.5 | 1.2 |
| M2 | 11 | 12 | 1.0 |
| M3 | 13 | 22 | 1.8 |
| M4 | 9 | 12.5 | 1.0 |
| M5 | 13 | 21 | 1.8 |
| M6 | 7 | 10 | 0.8 |
| M7 | 8 | 13.5 | 1.1 |
| M8 | 12 | 20 | 1.7 |
| **Tổng** | **94** | **134** | **≈ 11 tuần** |

Cộng thêm 20–30% cho việc phát sinh, debug và học công nghệ mới → **thực tế khoảng 13–15 tuần**.
