# Vấn đề đã biết

Cập nhật sau mỗi buổi test (task `X-01` trong backlog).

## Đang mở

| # | Mô tả | Ảnh hưởng | Chặng sẽ xử lý |
|---|---|---|---|
| 1 | Link rút gọn (`v.douyin.com`) tạo ID tạm; sau khi tải xong chưa cập nhật lại ID thật vào DB | Có thể tải trùng nếu dán cả link rút gọn lẫn link đầy đủ của cùng video | M2 (cùng với chống trùng pHash) |
| 2 | Chưa có proxy — nền tảng TQ có thể chặn IP Việt Nam | Tải lỗi 403 | M2 |
| 3 | Whisper chạy CPU chậm ~5× so với GPU | Video 60s mất vài phút | Không phải lỗi, cần GPU |
| 4 | Font phụ đề mặc định "Be Vietnam Pro" phải cài sẵn trên máy, chưa tự đóng gói | Chữ hiển thị sai font | M2 |
| 5 | Chưa chống lệch khi video nguồn có timestamp không đều (VBR) | Phụ đề lệch nhẹ ở video dài | M4 |

## Đã đóng

| # | Mô tả | Cách sửa |
|---|---|---|
| A | File tạm `.x.wav.tmp` khiến FFmpeg không đoán được định dạng đầu ra | `tmp_sibling` giữ phần mở rộng ở cuối: `.x.tmp.wav` |
| B | SQLAlchemy `Enum` lưu `.name` (`QUEUED`) thay vì `.value` (`queued`), lệch với migration | Đổi cột sang `String(32)`, enum chỉ dùng ở tầng Python |

## Bộ video mẫu

Chuẩn bị 20 video và giữ nguyên suốt dự án (xem `05-TEST-VA-VAN-HANH.md`). Ghi kết
quả mỗi lần đổi thuật toán:

| Video | Tải | ASR | Dịch | Render | Thời gian | Ghi chú |
|---|---|---|---|---|---|---|
| _(chưa có)_ | | | | | | |
