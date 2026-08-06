# ReupStudio — Kế hoạch triển khai

Bộ tài liệu để bạn (làm một mình, có AI hỗ trợ code) xây dựng ứng dụng từ con số 0 tới bản chạy được thật.

---

## Đọc theo thứ tự nào

| File | Khi nào đọc | Dùng để làm gì |
|---|---|---|
| `00-README-KE-HOACH.md` | Đầu tiên | Hiểu lộ trình, cách làm việc với AI |
| `01-KIEN-TRUC-VA-STACK.md` | Trước khi gõ dòng code đầu | Chốt stack, cấu trúc repo, luồng dữ liệu |
| `02-DATABASE-VA-API.md` | Ngay sau kiến trúc | Schema DB + hợp đồng API — làm trước mọi thứ khác |
| `03-BACKLOG-CONG-VIEC.md` | Hằng ngày | Danh sách task có mã, thứ tự làm, tiêu chí xong |
| `04-CLAUDE.md` | Copy vào gốc repo | Quy ước để AI viết code đúng chuẩn dự án |
| `05-TEST-VA-VAN-HANH.md` | Từ chặng M3 trở đi | Test, đo lường, triển khai, xử lý sự cố |

---

## Nguyên tắc lớn nhất

> **Xây theo chiều dọc, không theo chiều ngang.**

Đừng làm xong toàn bộ backend rồi mới làm frontend. Với mỗi chặng, làm **một lát cắt hoàn chỉnh** chạy được từ giao diện tới database tới file thật trên đĩa. Chặng M1 phải cho ra một video tiếng Việt xem được — dù xấu. Có thứ chạy được sớm quan trọng hơn có kiến trúc đẹp.

Ba lý do:

1. Bạn sẽ phát hiện sai lầm thiết kế ở tuần 2 thay vì tuần 10.
2. Bạn có động lực — nhìn thấy video đầu tiên tự dịch xong là cảm giác khác hẳn.
3. AI viết code tốt hơn nhiều khi có ngữ cảnh chạy thật để đối chiếu, thay vì viết mù theo spec.

---

## Lộ trình 9 chặng

Ước tính cho **một người làm bán thời gian (~15–20 giờ/tuần) có AI hỗ trợ**. Nếu làm toàn thời gian, chia đôi thời gian.

| Chặng | Tên | Kết quả cụ thể phải đạt | Thời gian |
|---|---|---|---|
| **M0** | Nền móng | `docker compose up` chạy được, DB có bảng, API trả `/health`, FE hiện trang trắng có sidebar | 3–5 ngày |
| **M1** | Lát cắt dọc đầu tiên | Dán 1 link Douyin → tải → Whisper → dịch → burn sub → xem được file mp4 tiếng Việt | 1–1.5 tuần |
| **M2** | Hàng đợi & giao diện thật | Celery worker chạy nền, trạng thái realtime qua WebSocket, Thư viện hiển thị đúng 6 bước | 1 tuần |
| **M3** | Xoá watermark & sub cứng | Dò tự động Douyin logo + sub, inpaint, so sánh trước/sau | 1.5–2 tuần |
| **M4** | Chuẩn hoá video ngắn | Crop 9:16, vùng an toàn UI, hook 3s, chia tập theo giới hạn nền tảng | 1 tuần |
| **M5** | Đăng lên nền tảng VN | OAuth + upload thật lên TikTok và YouTube Shorts, có retry | 1.5–2 tuần |
| **M6** | Lịch đăng & hạn ngạch | Calendar, rải tự động, hạn ngạch/kênh, khung giờ vàng | 1 tuần |
| **M7** | Luồng tự động | Watcher quét kênh nguồn → chạy hết pipeline → xếp lịch, không cần thao tác | 1–1.5 tuần |
| **M8** | Lồng tiếng, chống trùng, thống kê | TTS, tách nhạc nền, preset chống trùng, analytics, cảnh báo claim | 2 tuần |

**Tổng: khoảng 11–14 tuần.** Bản dùng được thật (đăng được video lên TikTok tự động) là hết **M5**, khoảng tuần thứ 7–8.

---

## Cách làm việc với AI cho hiệu quả

### 1. Luôn cho AI đọc `CLAUDE.md` trước

File `04-CLAUDE.md` trong bộ này là để copy vào gốc repo với tên `CLAUDE.md`. Nó chứa quy ước thư mục, cách đặt tên, mẫu code chuẩn. Không có nó, AI sẽ tự bịa ra kiến trúc khác nhau mỗi lần.

### 2. Mỗi phiên làm việc = một task có mã

Đừng nói "làm module download đi". Hãy nói:

> Làm task **BE-A1** trong `03-BACKLOG-CONG-VIEC.md`. Đọc `CLAUDE.md` và `02-DATABASE-VA-API.md` trước. Chỉ làm đúng phạm vi task này, không sửa file ngoài danh sách.

Task nhỏ → AI ít lạc đề, bạn dễ review, dễ quay lui khi hỏng.

### 3. Bắt AI viết test trước cho phần logic thuần

Với hàm xử lý dữ liệu (chia phụ đề, tính hạn ngạch, sinh lịch đăng), yêu cầu viết test trước rồi mới viết code. Với phần I/O nặng (FFmpeg, gọi API nền tảng) thì bỏ qua test tự động, kiểm tay bằng file thật.

### 4. Commit sau mỗi task

Một task = một commit = một thứ chạy được. Khi AI làm hỏng, `git reset` một bước là về trạng thái sạch.

```
feat(download): BE-A1 tải video Douyin qua yt-dlp
fix(render): sửa lệch audio 200ms khi đổi tốc độ
```

### 5. Đừng để AI tự chọn thư viện

Danh sách thư viện đã chốt trong `01-KIEN-TRUC-VA-STACK.md`. Nếu AI đề xuất thư viện khác, hỏi lý do trước khi đồng ý — thường là nó không biết lựa chọn đã có.

### 6. Ba câu hỏi trước khi nhận code AI viết

- Nếu API nền tảng trả lỗi giữa chừng, code này xử lý thế nào?
- File tạm sinh ra ở đâu, ai xoá?
- Chạy với 200 video thì có gì vỡ không?

Ba câu này bắt được 80% lỗi AI hay mắc trong dự án xử lý media.

---

## Rủi ro cần biết trước, không phải sau

| Rủi ro | Khi nào bùng | Chuẩn bị từ bây giờ |
|---|---|---|
| Douyin/Bilibili đổi API chống crawl | Bất cứ lúc nào, vài tháng một lần | Tách hẳn lớp `downloader/`, mỗi nền tảng một file, có test smoke chạy hằng ngày |
| Inpaint AI quá chậm, không dùng nổi | Chặng M3 | Làm chế độ nhanh (blur/delogo) trước, AI sau; đo thời gian thật trên video 60s rồi mới quyết |
| TikTok API duyệt app lâu hoặc từ chối | Chặng M5 | Nộp đơn xin quyền **ngay từ chặng M0**, đừng đợi tới lúc cần |
| Chi phí API vượt dự kiến | Chặng M8 | Đặt hạn mức cứng trong code từ M1, log chi phí mỗi job |
| Bản quyền — kênh bị gỡ video/khoá | Ngay khi đăng bài đầu tiên | Xem mục dưới |

---

## Về bản quyền — đọc trước khi viết dòng code đầu tiên

Đây là rủi ro lớn nhất của dự án và nó không nằm ở kỹ thuật.

Reup video của creator Trung Quốc mà không có phép có thể dẫn tới: video bị gỡ, kênh bị strike, mất quyền kiếm tiền, và trong trường hợp xấu là trách nhiệm pháp lý. Xoá watermark không giải quyết vấn đề — về mặt pháp lý nó thường bị coi là tình tiết tăng nặng vì cố ý xoá thông tin quản lý quyền.

Ba hướng làm cho kênh sống được lâu:

1. **Xin phép / mua license từ creator gốc.** Nhiều creator Douyin sẵn sàng cho phép đổi lấy credit hoặc phí nhỏ. Đây là cách bền nhất và cũng là cách duy nhất bật kiếm tiền an toàn.
2. **Nội dung có tính biến đổi thật.** Không phải chỉ dịch — mà là bình luận, phân tích, phản ứng, so sánh văn hoá. Phần bạn thêm vào phải là phần chính.
3. **Nguồn có license mở.** Video CC, tư liệu công cộng, nội dung được phép tái sử dụng.

Đề xuất thực tế: **xây tính năng "Quản lý license"** ngay từ M2 — mỗi kênh nguồn có trường ghi tình trạng cho phép (đã xin phép / có hợp đồng / chưa xin), và chặn luồng tự động với nguồn chưa có quyền. Việc này tốn 2 giờ code nhưng cứu bạn khỏi mất cả hệ thống kênh sau này.

Đây là thông tin tham khảo, không phải tư vấn pháp lý. Nếu định làm quy mô lớn hoặc kiếm tiền từ nó, nên hỏi luật sư sở hữu trí tuệ một buổi.

---

## Checklist trước khi bắt đầu M0

- [ ] Cài Docker Desktop, Python 3.12, Node 22, FFmpeg 7, Git
- [ ] Có GPU NVIDIA ≥8GB VRAM (cho Whisper local + inpaint AI) — nếu không, dùng API và bỏ inpaint AI
- [ ] Tạo repo Git, bật `.gitignore` cho `media/`, `.env`, `__pycache__`
- [ ] Đăng ký khoá API: LLM dịch thuật, TTS (để sau cũng được)
- [ ] **Nộp đơn xin quyền TikTok Content Posting API và Google Cloud (YouTube Data API)** — duyệt lâu, làm sớm
- [ ] Chuẩn bị 5–10 video Douyin mẫu để test (đủ loại: có sub cứng, không sub, logo tĩnh, logo động)
- [ ] Copy `04-CLAUDE.md` vào gốc repo với tên `CLAUDE.md`
