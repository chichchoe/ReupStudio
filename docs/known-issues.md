# Vấn đề đã biết

Cập nhật sau mỗi buổi test (task `X-01` trong backlog).

## Đang mở

| # | Mô tả | Ảnh hưởng | Chặng sẽ xử lý |
|---|---|---|---|
| 1 | Link rút gọn (`v.douyin.com`) tạo ID tạm; sau khi tải xong chưa cập nhật lại ID thật vào DB | Có thể tải trùng nếu dán cả link rút gọn lẫn link đầy đủ của cùng video | M2 (cùng với chống trùng pHash) |
| 2 | Chưa có proxy — nền tảng TQ có thể chặn IP Việt Nam | Tải lỗi 403 | M2 |
| 3 | Whisper chạy CPU chậm ~5× so với GPU | Video 60s mất vài phút | Không phải lỗi, cần GPU |
| 4 | Font phụ đề mặc định "Be Vietnam Pro" phải cài sẵn trên máy, chưa tự đóng gói. **Cụ thể hoá 2026-08-12:** `apps/worker/Dockerfile` chỉ cài `fonts-dejavu`, không có "Be Vietnam Pro" → trong Docker phụ đề rơi về font mặc định | Chữ hiển thị sai font | Đóng gói font vào image, hoặc đổi `SUB_FONT` |
| 5 | Chưa chống lệch khi video nguồn có timestamp không đều (VBR) | Phụ đề lệch nhẹ ở video dài | M4 |
| 6 | **ffmpeg Homebrew trên máy Mac dev thiếu `libass` và `libfreetype`** → không có filter `subtitles`/`ass`/`drawtext`. Nghĩa là **burn phụ đề và chèn hook KHÔNG chạy được trên máy dev**. Các filter khác (`delogo`, `boxblur`, `overlay`, `crop`, `scale`) đều có. Đường chạy thật KHÔNG bị ảnh hưởng: `apps/worker/Dockerfile` cài ffmpeg từ kho Debian, bản đó có đủ libass + libfreetype | Chạy worker thẳng trên Mac sẽ lỗi ở bước render; chạy trong Docker thì bình thường | Cài lại ffmpeg đầy đủ trên Mac, hoặc luôn chạy worker qua Docker |

## Quyết định phạm vi đã chốt

Ghi lại để người sau (và chính mình sau vài tháng) không phải đoán vì sao thiếu
tính năng, và biết cần gì để mở khoá.

### Q1 · M5 — Đăng bài: TẠM THỜI ĐĂNG TAY, hoãn phần API

**Chốt ngày 2026-08-11.**

Chủ dự án là **cá nhân**, chưa đăng ký được app doanh nghiệp trên các nền tảng.
Nên bước đăng bài **làm bằng tay**: công cụ chuẩn bị sẵn file và nội dung, người
dùng tự tải lên.

Phần này **chưa hoàn thiện, sẽ làm sau** — không phải đã bỏ.

Hệ quả với thiết kế M5:
- Đường chính là **xuất bộ đăng tay**: mỗi nền tảng đích một file đã chuẩn hoá
  đúng kích thước, kèm tiêu đề / mô tả / hashtag sinh sẵn trong giới hạn ký tự
  của nền tảng đó, sao chép được bằng một nút bấm.
- Các adapter API (`publishers/youtube.py`, `tiktok.py`, `facebook.py`,
  `instagram.py`) vẫn xây sau cùng một interface `publishers/base.py`, nằm chờ
  tới khi có quyền. Khi có key thì cắm vào, không phải viết lại luồng.
- `M6` (lịch đăng) vì vậy lên lịch cho việc **nhắc đăng tay**, chưa phải đăng tự
  động. Thuật toán rải lịch, hạn ngạch kênh, khung giờ vàng vẫn xây đầy đủ.

Cần gì để mở khoá phần tự động (kiểm lại chính sách trước khi làm, chúng đổi
thường xuyên):
- **YouTube** — Google Cloud Console mở cho cá nhân; app ở chế độ testing vẫn
  upload được lên kênh của chính mình, hạn mức mặc định ~6 video/ngày.
- **TikTok** — đăng ký cá nhân được, nhưng Content Posting API chưa qua kiểm
  duyệt thì bài đăng bị khoá riêng tư, phải vào app bật công khai bằng tay.
- **Instagram / Facebook** — cần chuyển sang tài khoản Business hoặc Creator
  (miễn phí) và liên kết một Trang Facebook.

**KHÔNG dùng trình duyệt tự động để đăng thay người dùng.** Vi phạm điều khoản
của cả ba nền tảng, rủi ro thật là khoá kênh — đánh đổi tệ cho một thao tác tay
mất nửa phút.

### Q2 · M3 — Hoãn hai task cần GPU và bộ video mẫu thật

**Chốt ngày 2026-08-06.**

- `M3-WK-04` (`detect/hardsub.py`, PaddleOCR) — cần model nặng **và** video có
  phụ đề cứng tiếng Trung thật để đo tiêu chí "≥90% ký tự". Chưa có video mẫu.
- `M3-WK-06` (`inpaint/ai.py`, ProPainter) — cần GPU CUDA. Máy phát triển hiện
  tại là Mac arm64. `docker-compose.yml` cũng đã dự liệu `worker-gpu` chạy trên
  host riêng có GPU.
- `M3-QA-01` — toàn bộ là đo trên bộ 20 video thật, chưa có.

Phần còn lại của M3 vẫn làm, nghiệm thu bằng **video tổng hợp sinh bằng ffmpeg**
(logo giả tĩnh và nhảy 4 góc). Con số đo trên video tổng hợp là **cận trên**, dễ
hơn video thật — đừng đọc như kết quả thực chiến.

Giao diện M3 sẽ hiện chế độ "Xoá bằng AI" **kèm cảnh báo chưa dùng được**, thay
vì để người dùng chọn rồi ngồi chờ một thứ không bao giờ chạy.

### Q3 · M4 — Không áp giới hạn thời lượng

**Chốt ngày 2026-08-11.**

`platform_limits.max_duration_sec` seed bằng `0` cho cả 5 nền tảng, nghĩa là
**không giới hạn**. Chủ dự án tự xem lại video trước khi đăng, không muốn công cụ
tự cắt theo con số phỏng đoán.

Hệ quả: `shortform/split.py` trả đúng một tập, không chia. Thuật toán chia tập
vẫn được xây và test đầy đủ, nằm chờ. Bật giới hạn bất kỳ lúc nào, không cần
deploy:

```bash
curl -X PATCH http://localhost:8000/api/v1/platform-limits/tiktok \
  -H 'Content-Type: application/json' -d '{"max_duration_sec": 180}'
```

## Đã đóng

| # | Mô tả | Cách sửa |
|---|---|---|
| A | File tạm `.x.wav.tmp` khiến FFmpeg không đoán được định dạng đầu ra | `tmp_sibling` giữ phần mở rộng ở cuối: `.x.tmp.wav` |
| B | SQLAlchemy `Enum` lưu `.name` (`QUEUED`) thay vì `.value` (`queued`), lệch với migration | Đổi cột sang `String(32)`, enum chỉ dùng ở tầng Python |
| C | `.gitignore` có dòng `models/` (ý định chặn model weights AI) nuốt luôn `packages/reup_core/src/reup_core/models/` — 4 file ORM chưa từng được git track, clone máy khác là hỏng package | Bỏ dòng `models/`, giữ `*.pt`/`*.bin`; commit `7d41bb2` |

## Bộ video mẫu

Chuẩn bị 20 video và giữ nguyên suốt dự án (xem `05-TEST-VA-VAN-HANH.md`). Ghi kết
quả mỗi lần đổi thuật toán:

| Video | Tải | ASR | Dịch | Render | Thời gian | Ghi chú |
|---|---|---|---|---|---|---|
| _(chưa có)_ | | | | | | |
