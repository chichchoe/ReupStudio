# Thiết kế: duyệt bản dịch trên video, và lồng tiếng bằng Fish Speech tại máy

Ngày 2026-08-20. Thay cho hai chỗ đang yếu: duyệt bản dịch mà không thấy hình,
và lồng tiếng phụ thuộc hoàn toàn vào dịch vụ ngoài.

## Vấn đề

Pipeline dừng hai lần, cả hai đều ở trạng thái `review`, phân biệt bằng cờ
`cho_duyet_ban_dich`:

| Chỗ dừng | Đang có | Thiếu |
|---|---|---|
| Chờ dịch | tiêu đề, số câu, chọn model/giọng | không xem được video, không đọc được bản gốc — bấm Dịch mù |
| Chờ duyệt | bảng đối chiếu, sửa tay, nghe dải tiếng | không có hình; **bảng đối chiếu ghép sai câu** |

Chỗ dừng thứ hai tồn tại để chặn trước bước nặng nhất (xoá chữ cứng rồi
render, video một tiếng mất hàng tiếng). Nó chỉ làm được việc đó nếu người
duyệt thật sự phán đoán được bản dịch đúng hay sai — mà đọc chữ không đủ.

---

# Phần A — Duyệt bản dịch trên video

## A1. Sửa trước: bảng đối chiếu đang ghép sai câu

`pipeline/subtitle_format.py::format_cues` vừa gộp câu ngắn
(`merge_short_cues`) vừa tách câu dài (`split_long_cues`), rồi đánh số lại từ 0:

```python
timed = enforce_timing(wrapped, opts)
return [Cue(index, c.start, c.end, c.text) for index, c in enumerate(timed)]
```

Nên sau bước chuẩn hoá, `vi[i]` không còn là bản dịch của `zh[i]`.
`DuyetBanDichTab.tsx` vẫn ghép theo chỉ số.

**Đo trên DB thật ngày 2026-08-20**: 8/10 video có số câu hai bên khác nhau
(118↔127, 90↔80, 111↔104…). Ví dụ video `bbba9781`, quanh giây 105–110:

| Bản dịch | Câu Trung bảng đang ghép | Câu Trung ĐÚNG (theo thời gian) |
|---|---|---|
| Alo, hôm nay thế nào rồi? | 好嘞 | 喂 今天还怎么样啊 |
| Chỗ tôi có hai tên bịt mặt. | 一样 | 我两个蒙面的 |
| Dạ dày tôi yếu, lấy cái này đi. | 一样 | 我要这个肠胃不好上 |

Lệch 7 giây, nội dung không liên quan.

**Cách sửa: ghép theo giao nhau thời gian.** Với mỗi câu Việt `[start, end)`,
lấy mọi câu Trung có `zh.start < vi.end AND zh.end > vi.start`, nối bằng `/`.

Đã thử trên chính dữ liệu trên: đúng toàn bộ. Câu Việt gộp từ hai câu Trung
thì hiện cả hai (`来 / 好嘞`) — đúng hơn cách ghép 1-1, vốn giấu mất một câu.

Không thêm trường vào `Cue`, không migration, chạy được ngay trên dữ liệu cũ.
Hàm thuần trong `pipeline/cues.py`, test trực tiếp.

## A2. API mới

```
GET  /videos/{id}/preview      -> proxy.mp4, FileResponse (range request)
GET  /videos/{id}/doi-chieu    -> [{ i, start, end, vi, zh, sua_tay }]
POST /videos/{id}/retranslate  -> 202 { model?, provider?, chi_so?: int[] }
```

**`preview`** trả `paths.proxy_path(id)`, rơi về `paths.raw_video(...)` nếu
thiếu. Tách khỏi `/file` chứ không dùng chung: `/file` mang nghĩa "bản render
cuối", trộn hai thứ vào một đường là mở cửa cho lỗi xem nhầm bản.

Đã kiểm ngày 2026-08-20: `build_proxy` chạy trong bước PROBE
(`tasks/video.py:415`) nên proxy có mặt từ lúc video vào tab Chờ dịch. 10/10
thư mục `media/work/*` đều có `proxy.mp4`, kích thước **304×540 (đã 9:16)**,
6–22 MB — đủ nhỏ để phát thẳng trong trình duyệt.

**`doi-chieu`** trả sẵn cặp câu đã ghép đúng theo A1, để React không phải tự
ghép. Thay cho việc gọi `/subtitles` rồi ghép ở client.

**`retranslate`** không có `chi_so` = dịch lại toàn bộ; có `chi_so` = chỉ
những câu đó. Router chỉ validate rồi gọi service; service kiểm trạng thái
`review` (giống `sua_ban_dich`) rồi `task_bridge.dich_lai(...)`.

`task_bridge` thêm `DICH_LAI = "reup.dich_lai"` và hàm gửi task. **Bắt buộc
truyền `queue="media"`** — app Celery của API không mang `task_routes` của
worker, thiếu nó là task rơi vào hàng không ai nghe, API vẫn trả 202 và không
bao giờ có gì xảy ra (đã ghi trong docstring `doc_lai_sau_khi_sua`).

## A3. Giữ câu đã sửa tay

Dịch lại toàn bộ **không được ghi đè câu người dùng đã sửa**. Đánh dấu bằng
khoá `sua_tay: true` trong từng dict cue (cột `cues` là JSON — không migration).

- `video_service.sua_ban_dich` đặt `sua_tay` cho câu vừa sửa.
- Task dịch lại đọc lại dòng cũ trước khi ghi, giữ nguyên cue có `sua_tay`.
- `Cue.from_dict` chỉ đọc `i/start/end/text` nên dataclass không phải đổi;
  việc gộp diễn ra ở tầng ghi DB trong worker, không lọt vào `pipeline/`.

Sau khi dịch lại, đi đúng đường `doc_lai_sau_khi_sua` đã có: cơ chế vân tay
(`_van_tay_cau`, `tasks/video.py:578`) tự bỏ qua câu chưa đổi chữ và chỉ gọi
nhà cung cấp giọng cho câu mới.

## A4. `KhungDoiChieu.tsx` — dùng cho cả hai chỗ dừng

Bên trái khung video, bên phải bảng câu. Bấm dòng nào nhảy tới đúng giây đó;
câu đang phát được tô sáng và bảng tự cuộn theo.

| | Chờ dịch | Chờ duyệt |
|---|---|---|
| phụ đề nổi trên hình | tiếng Trung | tiếng Việt |
| dải tiếng | không | `loitieng.wav`, khoá đồng bộ, video tắt tiếng |
| sửa chữ | không | có, đổi chữ là overlay đổi ngay |
| dịch lại | không | tích câu → dịch lại; hoặc dịch lại toàn bộ |

**Đồng bộ tiếng**: `<video muted>` + `<audio>` chạy song song. Đã kiểm:
`loitieng.wav` dài **đúng bằng** video (253,7s ↔ 253,7s, 150,4s ↔ 150,4s) và
cùng mốc 0 — nên chỉ cần nắn lại khi lệch quá 0,15s ở `timeupdate`, cộng với
bám theo `play`/`pause`/`seeked`.

**Vùng an toàn**: phủ dải `platform_limits` lên khung để thấy phụ đề có đụng
vùng UI nền tảng không, dùng lại cách vẽ của `SafeAreaPreview.tsx`. **Chỉ vẽ
khi khung hình xấp xỉ 9:16** — nguồn ngang sẽ được đổi khung ở bước sau, vẽ
dải lên bản ngang là chỉ sai chỗ.

Overlay HTML tự vẽ, không dùng `<track>` WebVTT: cần tô sáng đồng bộ với bảng,
cần thấy ngay chữ đang gõ khi chưa lưu, và cần vẽ vùng an toàn — `<track>`
không làm được cả ba.

## A5. Test phần A

Tự động:
- ghép zh↔vi theo giao thời gian: câu tách, câu gộp, câu không có cặp, biên chạm nhau
- `retranslate` giữ nguyên cue `sua_tay` khi dịch lại toàn bộ
- `retranslate` với `chi_so` chỉ đụng đúng những câu đó
- đổi giây → chỉ số câu đang phát (hàm thuần, tách khỏi React)
- `preview` rơi về raw khi thiếu proxy

Không tự động (kiểm tay): chất lượng đồng bộ tiếng/hình trên trình duyệt thật.

---

# Phần B — Lồng tiếng bằng Fish Speech S2-Pro tại máy

## B1. Đo đạc quyết định thiết kế (2026-08-20, Mac mini M4 Pro 24GB)

Chạy **cùng 20 câu tiếng Việt** lấy từ video `ce91541b` trong DB, **cùng một
giọng mẫu** (Edge Hoài My, 6,6 giây):

| | PyTorch + MPS (bf16) | MLX int8 |
|---|---|---|
| token/giây | 0,64 | **10,6** |
| RTF | ~33–46 | **1,98** |
| nạp model | 4+ phút | **1 giây** |
| RAM đỉnh | swap 12,3 GB (thrash) | **3,9 GB** |
| kết quả | dừng giữa chừng | 20/20 câu |

**Vì sao PyTorch hỏng**: fish-speech mặc định `torch.bfloat16`
(`tools/server/model_manager.py`), mà MPS hỗ trợ bfloat16 rất kém
(pytorch#141864). Cộng `PYTORCH_ENABLE_MPS_FALLBACK=1`, các op không hỗ trợ
rơi về CPU **âm thầm** — mỗi token đi GPU→CPU→GPU. Đối chiếu: PR #461 của
chính fish-speech đo được 3,28 token/giây trên **MacBook Air M1**, tức máy yếu
hơn nhiều vẫn nhanh gấp 5 lần đường PyTorch trên M4 Pro. Đó là hỏng, không
phải chậm.

**Chốt: dùng MLX, không dùng PyTorch.**

- thư viện: [`mlx-speech`](https://github.com/appautomaton/mlx-speech) (cần **Python 3.13**)
- trọng số: `appautomaton/fishaudio-s2-pro-8bit-mlx` — 4,6 GB int8

Quy ra việc thật: clip 60 giây lời thoại mất **2 phút**; video nguồn 34 phút
(~20 phút lời thoại) mất **40 phút**.

## B2. Kiến trúc: subprocess theo lô, KHÔNG phải server

Nạp model chỉ mất **1 giây**, nên không cần server HTTP thường trú như dự tính
ban đầu — bỏ luôn việc quản cổng, health check, vòng đời tiến trình.

```
worker (venv chính, không có torch/mlx)
  └─ tts/fish_mlx.py  ── subprocess ──►  venv riêng python 3.13 + mlx-speech
                         (có timeout)     đọc JSON lô câu → ghi wav → thoát
```

Đúng luật CLAUDE.md: *"Gọi model AI trực tiếp trong tiến trình worker chính là
cấm — dùng subprocess riêng, có timeout"*. venv worker giữ nguyên, không nhiễm
mlx.

**Một subprocess cho MỘT lô câu của MỘT video**, không phải mỗi câu một lần:
nạp 1 giây × 672 câu là 11 phút phí. Nạp một lần, đọc hết lô, thoát.

Chạy **một lô một lúc** (`concurrency 1` trên queue `gpu`): một model trên một
GPU, chạy song song chỉ tranh nhau bộ nhớ.

Vẫn dùng lại cơ chế vân tay `_van_tay_cau` — câu chưa đổi chữ thì không đọc lại.

## B3. Giọng đọc là ĐOẠN MẪU, không phải tên giọng

Fish S2-Pro **không có trường `voice`**. Giọng đến từ `reference_audio` +
`reference_text` — nhân bản theo ngữ cảnh, không huấn luyện.

Hai hệ quả bắt buộc:

1. **Không đưa mẫu thì mỗi câu ra một người khác** — video 672 câu thành 672
   giọng. Mọi lời gọi trong một video phải dùng đúng một đoạn mẫu.
2. **Chất lượng đầu ra không vượt được chất lượng đoạn mẫu.** Đo ngày
   2026-08-20 đã dính đúng bẫy này: mẫu dùng là đầu ra của Edge TTS, tức bắt
   model chép lại một giọng máy — chép cả cái đều đều của nó, cộng hao hụt khi
   clone. Người dùng nghe và không ưng, đúng như phải thế.

Thêm nữa: tham số sinh (`_DEFAULT_TEMPERATURE = 0.8`, `_DEFAULT_TOP_P = 0.8`,
`_DEFAULT_TOP_K = 30` trong `mlx_speech.generation.fish_s2_pro`) **không mở ra
ngoài API**. Nên **đoạn mẫu là cần gạt chất lượng duy nhất** — toàn bộ việc
làm giọng hay nằm ở Phần C, không nằm ở chỉnh tham số.

Quản lý mẫu: xem **Phần C — Thư viện giọng**.

## B4. Edge vẫn là đường lui, và phải nói ra khi dùng tới

`tts/fish_mlx.py` triển khai đúng `TTSProvider` sẵn có nên `pipeline/` và
`tasks/` không phải đổi. Rơi về Edge khi: subprocess chết, quá timeout, hoặc
hỏng liên tiếp quá `SO_LAN_HONG_LIEN_TIEP_THI_DUNG`.

Rơi về Edge thì **ghi lại vào `process_config`** là video này thật sự đọc bằng
gì, và hiện trên giao diện. Âm thầm đổi giọng mà không nói là kiểu hỏng tệ
nhất — người dùng duyệt bản dịch, nghe giọng Edge, tưởng đó là Fish.

## B5. Giấy phép — phải hiện trên giao diện

Trọng số S2-Pro theo **Fish Audio Research License**: nghiên cứu và phi thương
mại thì miễn phí, **thương mại phải mua phép riêng** (business@fish.audio).
Kênh có bật kiếm tiền là nằm ngoài phạm vi giấy phép này.

Ô chọn nhà cung cấp ghi rõ nhãn **"chạy tại máy · phi thương mại"** cạnh
`fish_mlx`, giống cách các nhà cung cấp khác đã ghi đánh đổi trong
`tts/base.py::NHA_CUNG_CAP`. Bản `fish-audio/s2-pro` qua OpenRouter (đã chạy)
là đường có phép thương mại và giữ nguyên.

## B6. Test phần B

Tự động (không cần model):
- `fish_mlx` gọi subprocess đúng tham số, phân tích đúng kết quả trả về
- subprocess chết / quá timeout / trả file rỗng → rơi về Edge và GHI LẠI việc đó
- vân tay bỏ qua câu chưa đổi chữ
- gom lô: N câu → một lần gọi, không phải N lần

Kiểm tay, `scripts/try_fish_mlx.py`: đọc thật một lô câu, in giây/câu và RTF,
xuất wav để nghe. Bắt buộc nghe bằng tai — theo bài học đã ghi trong
`docs/known-issues.md`: lỗi nặng của dự án này đều lọt qua test và chỉ lộ ra
khi xem/nghe bản thật.

---

# Phần C — Thư viện giọng (Cấu hình → Giọng đọc)

Một chỗ duy nhất quản mọi giọng: giọng dựng sẵn của Edge/Gemini/OpenRouter
LẪN giọng clone của Fish. Chọn giọng xong hệ thống tự biết gọi nhà cung cấp
nào — người dùng không phải chọn ba tầng (nhà cung cấp → model → giọng) như
hiện nay.

## C1. Vì sao gộp

Hiện `videos.py::tts_options` trả về ba nhóm, mỗi nhóm một danh sách giọng
cứng, và giao diện bắt chọn tuần tự ba ô. Thêm giọng clone vào khuôn đó là
thêm tầng thứ tư. Gộp lại thì thêm giọng chỉ là thêm một dòng trong bảng.

## C2. Bảng `giong_doc`

Cần migration Alembic (`0012_giong_doc`).

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | uuid | |
| `ten` | str | tên người dùng đặt: "Giọng tôi", "Chị Lan thuê" |
| `nha_cung_cap` | str | `edge` / `gemini` / `openrouter` / `fish_mlx` |
| `ma_giong` | str/null | mã giọng dựng sẵn (`vi-VN-HoaiMyNeural`); null với giọng clone |
| `model` | str/null | model TTS đi kèm, nếu nhà cung cấp cần |
| `ngon_ngu` | str | `vi` |
| `nguon` | str | `dung_san` / `tu_thu` / `cat_tu_file` / `thue_doc` / `tam_tu_may` |
| `mau_text` | text/null | phần chữ của đoạn mẫu, giọng clone mới có |
| `co_ma_hoa` | bool | đã encode xong `reference_codes` chưa |
| `mac_dinh` | bool | giọng dùng khi video không chọn riêng |
| `ghi_chu` | text/null | |
| `created_at` | ts | |

Giọng dựng sẵn được nạp seed một lần từ danh sách đang hardcode trong
`video_service.cac_giong_doc`, để bảng là nguồn sự thật duy nhất.

File theo `paths.py` (thêm hàm mới, không ghép path chỗ khác):

```
media/giong/<giong_id>/mau.wav     đoạn mẫu đã chuẩn hoá
media/giong/<giong_id>/mau.txt     phần chữ
media/giong/<giong_id>/codes.npz   reference_codes đã encode
media/giong/<giong_id>/nghe-thu.wav  câu đọc thử
```

## C3. Bốn nguồn giọng, một luồng

Cả bốn nguồn người dùng đã chốt đều đổ về cùng một đường xử lý — chỉ khác chỗ
lấy file vào:

| Nguồn | Cách lấy vào |
|---|---|
| `tu_thu` | tải lên file thu bằng điện thoại/micro |
| `cat_tu_file` | tải lên audio/video, chọn mốc bắt đầu–kết thúc, cắt bằng ffmpeg |
| `thue_doc` | tải lên file người đọc gửi — giống `tu_thu` |
| `tam_tu_may` | dựng bằng Edge ngay tại chỗ, đánh dấu rõ **"giọng tạm"** |

Từ đó trở đi chung một đường:

```
file vào
  ↓ ffmpeg: mono 44,1kHz, cắt im lặng đầu/cuối, cân âm lượng, cắt còn ≤ 15s
  ↓ Whisper CÓ SẴN: transcribe(mau.wav, language="vi")   ← faster-whisper đã cài,
  ↓                                                        không thêm phụ thuộc
  ↓ người dùng sửa lại chữ cho khớp từng chữ
  ↓ CỔNG CHẤT LƯỢNG (xem C4) — cảnh báo, không chặn
  ↓ encode_reference() → codes.npz         (chỉ với fish_mlx)
  ↓ đọc thử CÂU CỐ ĐỊNH → nghe-thu.wav
  ↓ người dùng nghe → Lưu hoặc Bỏ
```

Câu đọc thử **cố định cho mọi giọng** — có thế mới so được các giọng với nhau
sòng phẳng. Đặt hằng số `CAU_NGHE_THU` một chỗ, không rải rác.

Encode một lần rồi lưu `codes.npz`: `mlx-speech` cho
`encode_reference(audio, text) -> PreparedReference(reference_codes,
reference_text)` và `synthesize(text, reference_audio=<PreparedReference>)`.
Nhờ vậy lồng tiếng cả video không phải mã hoá lại đoạn mẫu ở từng câu — đúng
chỗ benchmark ngày 2026-08-20 đã làm phí và khiến RTF 1,98 bị đo bi quan.

## C4. Cổng chất lượng khi thêm giọng

Đo được bằng số, nên phải đo — mẫu tồi thì mọi video về sau đều tồi:

| Kiểm | Ngưỡng | Báo gì |
|---|---|---|
| độ dài | < 7s hoặc > 15s | "ngắn quá không đủ đặc trưng" / "dài quá phí, cắt bớt" |
| đỉnh | ≥ 0,99 | "bị vỡ tiếng, thu lại nhỏ hơn" |
| RMS | < 0,02 | "quá nhỏ, gần như im lặng" |
| tỉ lệ im lặng | > 40% | "phần lớn là im lặng, cắt lại" |
| số kênh / tần số | khác mono 44,1k | tự chuẩn hoá, không hỏi |

**Cảnh báo chứ không chặn** — người dùng có thể cố tình dùng mẫu lạ. Nhưng
phải nói ra trước khi lưu, không để họ phát hiện sau khi lồng tiếng cả video.

## C5. API

```
GET    /api/v1/giong-doc                 danh sách, kèm cờ sẵn sàng
POST   /api/v1/giong-doc                 202, tạo giọng mới (multipart: file + tên + nguồn)
GET    /api/v1/giong-doc/{id}/nghe-thu   file wav đọc thử
PATCH  /api/v1/giong-doc/{id}            đổi tên, ghi chú, đặt mặc định
DELETE /api/v1/giong-doc/{id}            xoá (chặn nếu là giọng dựng sẵn)
POST   /api/v1/giong-doc/{id}/doc-lai    dựng lại câu đọc thử
```

`POST` trả **202** rồi chạy Celery: chuẩn hoá + Whisper + encode + đọc thử
mất vài chục giây — quá 2 giây nên không được chờ trong request (luật số 1
CLAUDE.md).

`tts_options` cũ giữ lại nhưng đọc từ bảng `giong_doc`, để không phá giao diện
đang chạy trong lúc chuyển.

## C6. Giao diện

Thêm mục **"Giọng đọc"** vào trang Cấu hình, đúng khuôn mục "Nhà cung cấp AI"
đã có: thêm `const MUC_GIONG = "Giọng đọc"` và một nhánh
`{dangXem === MUC_GIONG && <ThuVienGiong />}` trong
`apps/web/app/settings/page.tsx`.

`ThuVienGiong.tsx` — danh sách thẻ, mỗi thẻ một giọng:

```
┌────────────────────────────────────────────────┐
│ ● Giọng tôi          tự thu · Fish · 12,4s     │
│   ▶ nghe thử    [đặt mặc định] [sửa] [xoá]     │
├────────────────────────────────────────────────┤
│   Hoài My            dựng sẵn · Edge           │
│   ▶ nghe thử    [đặt mặc định]                 │
├────────────────────────────────────────────────┤
│   Chị Lan            thuê đọc · Fish · đang xử lý…│
└────────────────────────────────────────────────┘
                                  [+ Thêm giọng]
```

Mọi thẻ dùng **cùng một câu** đọc thử nên bấm lần lượt là so được ngay.

Ô chọn giọng ở tab Chờ dịch rút từ ba ô xuống **một ô** đọc bảng `giong_doc`.

## C7. Test phần C

Tự động:
- cổng chất lượng: từng ngưỡng một, và mẫu tốt thì không cảnh báo gì
- chuẩn hoá audio ra đúng mono 44,1kHz và ≤ 15s
- xoá giọng đang là mặc định → phải chuyển mặc định sang giọng khác, không để rỗng
- không xoá được giọng dựng sẵn
- `giong_doc` → tham số gọi đúng nhà cung cấp tương ứng (bốn nhà, bốn dạng)

Kiểm tay, `scripts/try_them_giong.py`: thêm một giọng từ file thật, in kết quả
cổng chất lượng, xuất file đọc thử để **nghe bằng tai**.

# Ngoài phạm vi vòng này

- **Tự động** tách giọng nhân vật ra khỏi nhạc nền của video gốc rồi lấy làm
  mẫu. Khác với `cat_tu_file` ở C3 — cái đó là người dùng tự chọn mốc thời
  gian trên một file sạch; cái này cần tách nguồn âm, và vướng cả
  `license_status` của kênh nguồn.
- Chỉnh mốc thời gian phụ đề bằng tay ở màn duyệt — chỉ sửa chữ, đúng như
  `video_service.sua_ban_dich` đang chốt.
- Sửa phụ đề tiếng Trung trước khi dịch (đã hỏi, chốt: chỉ xem).
- Bản MLX 4-bit (`majentik/fishaudio-s2-pro-MLX-4bit`) — nhanh hơn nữa nhưng
  chất lượng chưa đo; để dành khi cần.
