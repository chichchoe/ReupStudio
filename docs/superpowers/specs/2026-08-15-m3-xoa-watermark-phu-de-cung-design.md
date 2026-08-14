# M3 — Xoá watermark và phụ đề cứng

Chốt ngày 2026-08-15. Thay thế phần mô tả M3 trong `docs/03-BACKLOG-CONG-VIEC.md`
ở những chỗ mâu thuẫn — backlog viết trước khi có số đo thật.

## Vì sao cần

Ảnh render ngày 2026-08-14 cho thấy phụ đề tiếng Trung gốc **vẫn nằm trong
hình**, đè chồng lên phụ đề tiếng Việt vừa burn. Video ra không dùng được để
đăng. Đây là mảnh thiếu rõ nhất của sản phẩm sau khi M1/M2/M4 đã chạy.

Yêu cầu chủ dự án (2026-08-15): **dò chính xác, xoá chính xác, không mất hình
phía sau**; chấp nhận thêm thư viện nặng; phải nhanh và tối ưu cho máy hiện có.

## Số đo thật — nền của mọi quyết định dưới đây

Đo trên Mac mini M4 Pro 24GB, khung hình thật lấy từ video rednote của chủ dự
án (720×1280).

| Hạng mục | Kết quả |
|---|---|
| PyTorch + Metal (MPS) | chạy được — `torch 2.13` |
| ONNX Runtime | có `CoreMLExecutionProvider` |
| Dò chữ (RapidOCR, ONNX) | **0,11 s/khung** |
| Vá `cv2.inpaint` (TELEA/NS) | 7–9 ms/khung, **nhoè rõ** trên nền có cấu trúc |
| Vá LaMa, cả khung | 4,7 s/khung — không dùng được |
| Vá LaMa, **chỉ vùng cắt** quanh chữ | **0,173 s/khung**, ảnh sạch |

Cắt vùng nhỏ rồi mới đưa vào model là phép tối ưu quyết định: nhanh gấp **27
lần** so với vá cả khung, và chính nó biến M3 từ "không khả thi trên máy này"
thành "khả thi".

### Ba giả định đã bị phép đo bác bỏ

1. **"Phụ đề cứng nằm ở dải dưới khung"** — SAI. Đo được: phụ đề ở **65–71%**
   chiều cao (giữa khung, đè lên người), còn khối chữ tuyên bố của người quay ở
   **2,4–7,2%** trên đỉnh. Mọi phương án "che dải dưới" đều trượt cả hai.

2. **"Chép nền từ khung lân cận không có phụ đề"** — SAI với nội dung hội
   thoại liên tục. Bảy giây liên tiếp được kiểm đều có phụ đề; không tồn tại
   khung sạch để chép.

3. **"Không có GPU NVIDIA thì phải hoãn phần AI"** — SAI. Câu này được lặp lại
   nhiều lần trong quá trình làm việc trước khi kiểm. Metal chạy LaMa tốt.

### Cảnh báo quan trọng nhất từ phép đo

OCR đọc ra vùng chữ `2ama` với tin cậy 0,63 — đó là **hoạ tiết chữ in trên áo
nhân vật**, không phải phụ đề. Xoá thẳng mọi vùng chữ OCR trả về sẽ xoá luôn
hoạ tiết quần áo, biển hiệu, bao bì sản phẩm trong khung.

**Lọc là phần khó nhất của M3, không phải dò.**

## Phạm vi

### Làm

- Dò vùng chữ cứng (phụ đề + chữ overlay của người quay) bằng OCR.
- Lọc để chỉ giữ vùng thật sự cần xoá.
- Dò logo/watermark tĩnh và logo nhảy góc.
- Xoá bằng LaMa trên vùng cắt; `cv2.inpaint` làm phương án dự phòng nhanh.
- Lưu mask vào DB để người dùng sửa tay và để tái tạo lại được.

### Không làm ở chặng này

- **ProPainter / inpaint theo dòng chảy thời gian.** LaMa vá từng khung độc
  lập, nên vùng vá có thể "nhấp nháy" giữa các khung. Chấp nhận ở M3; nếu thực
  tế thấy khó chịu thì đó là việc riêng của chặng sau.
- **Giao diện vẽ mask tay** (`M3-FE-01/02/03` trong backlog). Tách thành mảnh
  riêng, làm sau khi phần dò tự động đã có dữ liệu thật để hiển thị.

## Kiến trúc

Theo đúng luật hai lớp của `CLAUDE.md`: `pipeline/` là hàm thuần, `tasks/` lo
DB và điều phối.

```
pipeline/masking/
├── ocr.py          dò vùng chữ  → list[TextBox]      (gọi RapidOCR)
├── loc.py          LỌC box nào đáng xoá             (hàm THUẦN, test kỹ)
├── logo.py         dò logo tĩnh + logo nhảy góc      (phương sai thời gian)
├── timeline.py     gom box theo thời gian → MaskRegion có time_range
└── vaa.py          vá vùng: LaMa (chính) / cv2 (dự phòng)
```

`loc.py` và `timeline.py` là hàm thuần không gọi mạng, không chạm model — nơi
đặt phần lớn test tự động. `ocr.py` và `vaa.py` bọc model, kiểm bằng script
`try_*.py` trên ảnh thật.

### Luồng

```
video đã tải
   → lấy mẫu khung (2 khung/giây, không phải mọi khung)
   → ocr.py  tìm vùng chữ
   → loc.py  loại vùng không đáng xoá
   → timeline.py  gom thành MaskRegion (vùng + khoảng thời gian)
   → [người dùng xem/sửa]        ← mảnh giao diện, làm sau
   → vaa.py  vá từng khung trong khoảng thời gian của mask
   → burn phụ đề Việt lên bản đã sạch
```

Bước dò chạy **2 khung/giây** chứ không mọi khung: phụ đề tồn tại vài giây, lấy
mẫu dày hơn chỉ tốn thời gian. Bước vá thì **phải chạy mọi khung** trong khoảng
mask, vì nền dưới mask đổi liên tục.

## Quy tắc lọc (phần khó nhất)

Bốn tín hiệu, kết hợp lại thay vì dựa vào một cái:

1. **Độ bền vị trí qua thời gian.** Phụ đề và overlay xuất hiện ở vị trí gần
   như cố định qua nhiều khung liên tiếp. Chữ trên áo di chuyển theo người.
2. **Tin cậy OCR.** Ngưỡng đọc từ cấu hình, không hardcode.
3. **Vùng an toàn.** Chữ nằm trong dải giữa khung (nơi mặt người thường ở) đáng
   ngờ hơn chữ ở dải trên/dưới.
4. **Ngôn ngữ.** Ký tự Hán ở nguồn Trung Quốc đáng xoá hơn chữ Latin — chữ
   Latin thường là logo thương hiệu in trên vật thể.

Mỗi tín hiệu cho một điểm; tổng điểm vượt ngưỡng thì mới xoá. Ngưỡng chỉnh được
qua `platform_limits`-style preset, không hardcode.

**Nguyên tắc khi phân vân: KHÔNG xoá.** Sót một watermark thì người dùng thấy
ngay và sửa tay được; xoá nhầm mặt người hay hoạ tiết áo thì hỏng video mà
không ai biết cho tới khi đăng.

## Dữ liệu

Bảng `mask_regions` (đã có trong `docs/02-DATABASE-VA-API.md`, chưa tạo):

- Toạ độ theo **phần trăm 0–1**, không theo pixel (luật số 2 `CLAUDE.md`).
- `time_range` để mask chỉ áp trong khoảng nó tồn tại.
- `source`: `auto` | `manual` — phân biệt máy dò và người sửa, để lần dò lại
  không đè mất chỉnh tay.
- `confidence` giữ nguyên điểm lọc, phục vụ giao diện xếp hạng vùng đáng ngờ.

## Thư viện thêm

Tất cả đã cài và đo thật trong `.venv`, **chưa khai vào `pyproject.toml`**:

| Thư viện | Dung lượng | Vì sao |
|---|---|---|
| `rapidocr-onnxruntime` | ~15 MB | dò chữ; chạy ONNX, có đường CoreML |
| `torch` | ~2 GB | nền để chạy LaMa trên Metal |
| `simple-lama-inpainting` | nhỏ | LaMa; kéo model `big-lama.pt` ~200 MB về `~/.cache/torch` |
| `Pillow` | nhỏ | phụ thuộc của hai gói trên |

Khai vào nhóm phụ `[ai]` cùng `faster-whisper`, không vào nhóm chạy chính —
worker Docker không cần nếu chỉ chạy M1.

**Lưu ý cài đặt:** Python 3.14 bản python.org thiếu bộ chứng chỉ SSL, nên lần
tải model đầu tiên hỏng với `CERTIFICATE_VERIFY_FAILED`. Cách chạy được:
`SSL_CERT_FILE=$(python -c "import certifi; print(certifi.where())")`. Phải ghi
vào tài liệu vận hành, nếu không người cài lần đầu sẽ mất thời gian đoán.

## Thời gian xử lý — giới hạn phải nói trước

| Thời lượng video | Số khung | Thời gian vá (ước từ 0,173 s/khung) |
|---|---|---|
| 3 phút | ~4.500 | ~13 phút |
| 34 phút | ~50.000 | **~2,4 giờ** |

Video ngắn (đúng mục tiêu của dự án) thì chấp nhận được. Video dài thì không.
Hai hướng giảm, đo trước khi làm:

1. **Bỏ qua khung không đổi.** So sánh vùng dưới mask giữa hai khung liên tiếp;
   giống nhau thì dùng lại kết quả vá cũ.
2. **Hạ độ phân giải vùng vá** rồi phóng lại — nhanh hơn, đổi lại nét kém đi.

Cả hai là **tối ưu**, không phải phần cốt lõi. Làm sau khi đường chính chạy
đúng, và chỉ làm nếu số đo cho thấy đáng.

## Nghiệm thu

Backlog cũ đặt tiêu chí "đúng ≥90% trên 20 video mẫu". **Không đo được** — bộ
20 video mẫu chưa tồn tại. Tiêu chí thay thế, đo được ngay với 3 video đang có:

1. Trên khung hình đã đo: cả hai khối chữ (phụ đề 65–71%, tuyên bố 2,4–7,2%)
   biến mất; hoạ tiết áo và biển hiệu **còn nguyên**.
2. Không vùng nào bị xoá nhầm trong 20 khung lấy mẫu — kiểm bằng mắt qua ảnh
   trước/sau, có script `try_*.py` xuất ảnh ghép.
3. Video 3 phút xử lý xong dưới 20 phút.
4. Người dùng tắt được toàn bộ M3 bằng một cờ trong preset, và khi tắt thì
   pipeline chạy đúng như hiện nay.

Điểm 4 quan trọng: M3 là bước nặng và có rủi ro xoá nhầm. Phải bật/tắt được.

## Thứ tự làm

1. `ocr.py` + `loc.py` + test cho phần lọc — xương sống, và là chỗ dễ sai nhất.
2. `timeline.py` — gom box thành mask có khoảng thời gian.
3. `vaa.py` + script `try_xoa_chu.py` xuất ảnh trước/sau.
4. Bảng `mask_regions` + migration + nối vào pipeline sau bước nhận dạng.
5. `logo.py` — dò watermark. Tách sau vì phụ đề mới là thứ hỏng ảnh rõ nhất.
6. Tối ưu tốc độ, chỉ khi số đo đòi.

## Câu còn treo

- **Nhấp nháy giữa các khung**: LaMa vá độc lập từng khung nên vùng vá có thể
  không liền mạch khi phát. Chưa đo. Phải xem một đoạn 5 giây đã vá rồi mới
  biết có chấp nhận được không — làm ngay ở bước 3.
- **Video dài**: chưa chốt cách xử lý. Có thể chỉ đơn giản là không cho bật M3
  với video quá dài, thay vì cố tối ưu.
