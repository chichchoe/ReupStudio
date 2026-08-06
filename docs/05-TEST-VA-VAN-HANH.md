# Test & Vận hành

---

# PHẦN 1 — CHIẾN LƯỢC TEST

Dự án này 70% là xử lý media và gọi API bên ngoài — hai thứ khó test tự động. Đừng cố đạt 80% coverage, sẽ lãng phí. Hãy test đúng chỗ đáng test.

## Tầng 1 — Test tự động (pytest)

Chỉ cho **logic thuần, không I/O**. Đây là chỗ lỗi âm thầm và khó phát hiện bằng mắt.

| Cần test | Vì sao | Ca biên phải có |
|---|---|---|
| Chuẩn hoá phụ đề | Sai là chữ tràn màn hình mọi video | Câu 200 ký tự · khung 0.2s · 2 khung chồng thời gian · text rỗng |
| Chia tập theo giới hạn | Sai là cắt giữa câu thoại | Video vừa đúng giới hạn · dài gấp 3 · không có khoảng lặng nào |
| Rải lịch đăng | Sai là vi phạm hạn ngạch, kênh bị phạt | Hết suất · 1 kênh duy nhất · min_gap lớn hơn cả ngày |
| Tính hạn ngạch | Sai là đăng quá số lượng an toàn | Đã đăng đủ · qua nửa đêm · kênh đang pause |
| Chuyển đổi toạ độ mask | Sai là mask lệch ở mọi độ phân giải | 540p ↔ 1080p ↔ 4K · mask sát mép |
| Parser metadata downloader | Nền tảng đổi format là hỏng ngầm | Fixture JSON thật của 5 nền tảng |
| Đồng bộ thời lượng TTS | Sai là giọng đè lên nhau | Giọng dài gấp đôi · ngắn một nửa · câu 0.3s |

```python
# apps/worker/tests/test_subtitle_format.py
def test_cau_dai_bi_cat_thanh_hai_dong():
    cue = Cue(0, 4.0, "Ba năm qua thứ tôi chờ đợi không phải là lời xin lỗi của anh mà là ngày tôi tỉnh ra")
    out = format_cues([cue])
    assert all(len(line) <= 42 for c in out for line in c.text.split("\n"))
    assert all(c.text.count("\n") <= 1 for c in out)
```

**Mục tiêu: ~40 test.** Chạy trong 5 giây. Nhiều hơn nữa là đang test nhầm chỗ.

## Tầng 2 — Script kiểm tay (`scripts/`)

Cho phần media. Mắt người là công cụ kiểm tốt nhất ở đây.

```bash
python scripts/try_download.py "https://v.douyin.com/xxx"
python scripts/try_detect.py media/raw/douyin/123/video.mp4 --out preview.png
python scripts/try_render.py 123 --start 10 --duration 5
python scripts/try_publish.py 123 --channel test-tiktok --dry-run
```

`try_detect.py` phải **xuất ảnh có vẽ khung mask đè lên** — nhìn 1 giây là biết đúng sai, nhanh hơn đọc toạ độ.

## Tầng 3 — Bộ video mẫu chuẩn

Chuẩn bị **20 video** và giữ nguyên suốt dự án. Mỗi lần đổi thuật toán, chạy lại cả bộ và so kết quả.

| Nhóm | Số lượng | Đặc điểm cần có |
|---|---|---|
| Douyin logo động | 4 | Logo nhảy 4 góc, có chuỗi ID |
| Có phụ đề cứng | 4 | 1 dòng, 2 dòng, có viền, nền đen |
| Nền phức tạp | 3 | Cảnh động, nhiều chi tiết sau logo — thử thách inpaint |
| Không lời thoại | 2 | Chỉ nhạc — kiểm nhánh xử lý riêng |
| Video ngang | 3 | Test crop 9:16 |
| Video dài | 2 | >5 phút — test chia tập |
| Chữ trong cảnh | 2 | Biển hiệu, chữ trên áo — không được xoá nhầm |

Ghi kết quả vào bảng, cập nhật mỗi lần đổi thuật toán:

```markdown
| Video | Dò logo | Dò sub | Inpaint | Thời gian | Ghi chú |
|-------|---------|--------|---------|-----------|---------|
| d01   | ✅ 94%  | ✅ 88% | ✅      | 42s       |         |
| d02   | ⚠️ 61%  | ✅ 91% | ⚠️ mờ   | 51s       | nền chuyển động nhanh |
```

## Tầng 4 — Test chịu tải

Trước khi bật luồng tự động (M7), phải chạy:

- **50 video liên tục** — kiểm rò rỉ bộ nhớ, file tạm dồn, VRAM không giải phóng
- **Ngắt mạng giữa upload** — phải resume được
- **Kill worker giữa chừng** — job phải retry, không mất dữ liệu
- **Ổ đĩa đầy** — phải báo lỗi rõ ràng, không làm hỏng DB
- **API nền tảng trả 429** — phải backoff, không spam

## Tầng 5 — Kiểm trước khi đăng (QC tự động trong pipeline)

Chạy trên mọi bản render, chặn đăng nếu fail:

```python
CHECKS = [
    ("resolution",   lambda v: v.width >= 720 and v.height >= 1280),
    ("duration",     lambda v: v.duration <= limits.max_duration_sec),
    ("audio_exists", lambda v: v.has_audio and v.audio_rms > SILENCE_THRESHOLD),
    ("not_black",    lambda v: v.mean_brightness > 8),
    ("av_sync",      lambda v: abs(v.av_drift_ms) < 100),
    ("no_logo",      lambda v: not detect_residual_logo(v)),
    ("no_cn_text",   lambda v: not detect_chinese_text(v)),
    ("file_size",    lambda v: 1_000_000 < v.size < 500_000_000),
]
```

Bước này rẻ (vài giây) và cứu bạn khỏi đăng nhầm video hỏng lên kênh thật.

---

# PHẦN 2 — VẬN HÀNH

## Triển khai

### Giai đoạn đầu — chạy trên máy mình

Đủ dùng cho tới khi vượt ~50 video/ngày.

```
Máy cá nhân (có GPU)
├── docker compose: postgres, redis, api, web, worker-cpu
└── worker-gpu chạy trực tiếp trên host (đỡ đau đầu CUDA trong Docker)
```

Cần: máy bật liên tục (hoặc chấp nhận lịch đăng trượt), IP tĩnh không bắt buộc.

### Giai đoạn sau — tách máy

```
VPS rẻ (2 vCPU, 4GB)          Máy có GPU tại nhà
├── postgres                   └── worker-gpu (asr, vision)
├── redis                          kết nối qua VPN hoặc Tailscale
├── api
├── web
└── worker-cpu, beat
```

Lý do tách: VPS chạy 24/7 đảm bảo lịch đăng đúng giờ; GPU đắt trên cloud nên giữ ở nhà.

## Sao lưu

| Cái gì | Tần suất | Cách |
|---|---|---|
| PostgreSQL | Hằng ngày | `pg_dump` → file nén, giữ 14 bản |
| `.env` + token | Khi thay đổi | Lưu vào password manager, KHÔNG vào Git |
| Preset & cấu hình | Hằng tuần | Export JSON qua API `/settings/export` |
| File render đã đăng | Không cần | Đã có trên nền tảng rồi |

Test khôi phục **một lần** ngay ở M2. Backup chưa từng khôi phục thử thì coi như không có.

## Giám sát

Không cần Prometheus/Grafana cho quy mô này. Chỉ cần:

1. **Trang Tổng quan** hiển thị: job đang chạy, lỗi 24h qua, dung lượng ổ, chi phí tháng
2. **Telegram bot** báo: job fail 3 lần liên tiếp · Content ID claim · token sắp hết hạn · ổ đĩa <10% · vượt hạn mức chi tiêu
3. **Báo cáo hằng ngày 22:00**: số video xử lý, số đăng, số lỗi, chi phí ngày

## Sự cố hay gặp và cách xử

| Triệu chứng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| Downloader lỗi 403 hàng loạt | Nền tảng TQ đổi API hoặc chặn IP | Cập nhật yt-dlp trước; nếu vẫn lỗi thì đổi proxy; nếu vẫn thì phải sửa downloader |
| Whisper chậm bất thường | Rơi về CPU do CUDA lỗi | Kiểm `nvidia-smi`, kiểm `WHISPER_DEVICE`, restart worker-gpu |
| Video render ra đen | Filter FFmpeg sai thứ tự | Xem lệnh trong `job_runs.log`, chạy tay lệnh đó |
| Audio lệch dần theo thời gian | Đổi tốc độ mà không đổi timestamp | Kiểm `atempo` và `setpts` phải đi cùng nhau |
| Upload TikTok fail 401 | Token hết hạn, refresh fail | Kết nối lại kênh; kiểm cron refresh token |
| Job kẹt ở "running" mãi | Worker chết giữa chừng | Celery `visibility_timeout`; thêm task dọn job quá hạn |
| Ổ đĩa đầy đột ngột | File tạm không được xoá khi job fail | Dọn `media/work/`; thêm cleanup vào `finally` |
| VRAM đầy sau vài chục video | Model không giải phóng | Chạy inpaint/whisper qua subprocess riêng, không import chung tiến trình |
| Video bị gỡ / kênh bị strike | Vấn đề bản quyền | Dừng luồng ngay, rà `license_status` của nguồn, xem mục dưới |

## Quy trình khi bị Content ID claim hoặc strike

Không phải việc kỹ thuật, nhưng phải có quy trình sẵn:

1. **Dừng ngay** luồng tự động liên quan tới kênh đó (hệ thống tự làm nếu bật `auto_pause_on_claim`)
2. **Xác định nguồn** gây claim — tra `videos.source_channel_id` của bài bị claim
3. **Đánh dấu nguồn** đó `license_status = unknown` và tắt kênh nguồn
4. **Rà soát** các video khác cùng nguồn đã đăng, cân nhắc gỡ chủ động
5. **Quyết định**: xin phép creator gốc, hay bỏ hẳn nguồn đó
6. **Ghi lại** vào `copyright_claims` để không lặp lại

Với strike (nặng hơn claim): dừng toàn bộ hoạt động của kênh đó tối thiểu 2 tuần, không đăng gì thêm cho tới khi strike hết hiệu lực.

## Kiểm tra định kỳ

| Việc | Tần suất |
|---|---|
| Cập nhật yt-dlp | Hằng tuần |
| Chạy smoke test downloader 5 nền tảng | Hằng ngày (tự động) |
| Rà `platform_limits` so với chính sách thật của nền tảng | Hằng quý |
| Xem lại `job_runs` tìm bước chậm bất thường | Hằng tháng |
| Kiểm chi phí API so với hạn mức | Hằng tuần |
| Rà `license_status` các nguồn đang chạy | Hằng tháng |
| Test khôi phục backup | Hằng quý |

---

# PHẦN 3 — CHỈ SỐ CẦN THEO DÕI

## Chỉ số kỹ thuật

| Chỉ số | Ngưỡng tốt | Ngưỡng báo động |
|---|---|---|
| Tỷ lệ job thành công | >95% | <85% |
| Thời gian xử lý / video 60s (không AI inpaint) | <3 phút | >8 phút |
| Thời gian xử lý / video 60s (có AI inpaint) | <12 phút | >25 phút |
| Tỷ lệ dò watermark đúng tự động | >85% | <70% |
| Tỷ lệ video cần sửa tay | <15% | >30% |
| Tỷ lệ upload thành công lần đầu | >90% | <75% |
| Chi phí / video | <$0.50 | >$1.00 |

Nếu **tỷ lệ cần sửa tay >30%**, hệ thống đang không tiết kiệm thời gian cho bạn — dừng thêm tính năng, đi sửa phần dò tự động.

## Chỉ số nội dung

| Chỉ số | Ý nghĩa |
|---|---|
| View trung bình theo nguồn | Nguồn nào đáng lấy tiếp |
| Tỷ lệ xem hết 3 giây đầu | Hook có hiệu quả không |
| Tỷ lệ xem hết video | Chất lượng dịch/lồng tiếng |
| Follower tăng / video | Kênh có đang lớn không |
| Số claim / 100 video | Rủi ro bản quyền đang ở mức nào |

Chỉ số cuối cùng là quan trọng nhất. Nếu **số claim/100 video >5**, mô hình nội dung đang có vấn đề — không phải vấn đề kỹ thuật mà là vấn đề nguồn. Xử lý bằng cách đổi nguồn hoặc xin phép, không phải bằng cách tăng cường độ chống trùng.
