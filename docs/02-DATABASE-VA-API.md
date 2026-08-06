# Database & Hợp đồng API

Làm file này **xong trước khi viết bất kỳ dòng code nghiệp vụ nào**. Schema sai ở tuần 2 nghĩa là viết lại ở tuần 8.

---

# PHẦN 1 — DATABASE

## Sơ đồ quan hệ

```
source_channels ──┐
                  ├──► videos ──┬──► subtitles
pipelines ────────┘             ├──► mask_regions
     │                          ├──► render_variants ──► scheduled_posts ──► post_logs
     └──► pipeline_targets      └──► job_runs
                  │
publish_channels ─┘──► channel_quotas
                  └──► platform_limits

presets           app_settings          cost_logs
```

## Enum dùng chung

Đặt trong `packages/shared` và mirror sang Python + TypeScript.

```python
class VideoStatus(str, Enum):
    QUEUED    = "queued"       # chờ xử lý
    RUNNING   = "running"      # đang chạy pipeline
    REVIEW    = "review"       # cần người duyệt
    READY     = "ready"        # đã render, chờ xếp lịch/đăng
    SCHEDULED = "scheduled"    # đã có lịch
    POSTED    = "posted"       # đã đăng ít nhất 1 nơi
    ERROR     = "error"
    SKIPPED   = "skipped"      # bị lọc bỏ

class PipelineStep(str, Enum):
    DOWNLOAD   = "download"
    PROBE      = "probe"
    TRANSCRIBE = "transcribe"
    TRANSLATE  = "translate"
    DETECT     = "detect"
    INPAINT    = "inpaint"
    SHORTFORM  = "shortform"
    TTS        = "tts"
    RENDER     = "render"
    QC         = "qc"
    UPLOAD     = "upload"

class Platform(str, Enum):          # nền tảng đăng (VN)
    TIKTOK    = "tiktok"
    YOUTUBE   = "youtube"           # Shorts
    FACEBOOK  = "facebook"          # Reels
    INSTAGRAM = "instagram"         # Reels
    ZALO      = "zalo"

class SourcePlatform(str, Enum):
    DOUYIN      = "douyin"
    BILIBILI    = "bilibili"
    KUAISHOU    = "kuaishou"
    XIAOHONGSHU = "xiaohongshu"
    WEIBO       = "weibo"

class LicenseStatus(str, Enum):
    UNKNOWN   = "unknown"       # chưa xác định — CHẶN luồng tự động
    PERMITTED = "permitted"     # đã xin phép creator
    LICENSED  = "licensed"      # có hợp đồng/mua license
    OPEN      = "open"          # nguồn CC / public domain
    OWN       = "own"           # nội dung của chính mình
```

## Bảng

### `source_channels` — kênh nguồn Trung Quốc

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | uuid PK | |
| platform | enum SourcePlatform | |
| external_id | text | ID kênh trên nền tảng |
| handle | text | `@小甜剧场` |
| display_name | text | |
| url | text | |
| scan_interval_min | int | 15 / 60 / 360 / 1440 |
| last_scanned_at | timestamptz null | |
| last_seen_video_id | text null | mốc để không quét lại |
| filter_preset_id | uuid FK null | |
| process_preset_id | uuid FK null | |
| **license_status** | enum LicenseStatus | mặc định `unknown` |
| **license_note** | text null | link email xin phép, số hợp đồng |
| enabled | bool | |
| created_at / updated_at | timestamptz | |

**UNIQUE (platform, external_id)**

### `videos`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | uuid PK | |
| source_channel_id | uuid FK null | null nếu dán link tay |
| pipeline_id | uuid FK null | |
| source_platform | enum | |
| source_video_id | text | ID gốc trên nền tảng |
| source_url | text | |
| source_author | text | để ghi credit |
| title_original | text | |
| desc_original | text null | |
| title_vi | text null | |
| desc_vi | text null | |
| hashtags_vi | text[] null | |
| duration_sec | numeric | |
| width / height | int | |
| fps | numeric | |
| has_speech | bool null | |
| view_count_source | bigint null | |
| md5 | text null | chống trùng |
| phash | text null | chống trùng ảnh |
| status | enum VideoStatus | |
| current_step | enum PipelineStep null | |
| error_message | text null | |
| flags | jsonb | `{"sensitive": false, "low_confidence": true}` |
| raw_path | text null | |
| work_dir | text null | |
| created_at / updated_at | timestamptz | |

**INDEX**: `(status)`, `(source_channel_id, created_at)`, `(md5)`, `(phash)`
**UNIQUE (source_platform, source_video_id)**

### `subtitles`

| Cột | Kiểu |
|---|---|
| id | uuid PK |
| video_id | uuid FK |
| lang | text (`zh` / `vi`) |
| source | text (`asr` / `ocr` / `manual` / `translated`) |
| cues | jsonb — `[{i, start, end, text}]` |
| edited_by_user | bool |
| created_at | timestamptz |

Lưu cả mảng trong 1 JSONB thay vì mỗi dòng phụ đề một row — đơn giản hơn nhiều, và không bao giờ cần query từng dòng.

### `mask_regions`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | uuid PK | |
| video_id | uuid FK | |
| kind | text | `watermark` / `hardsub` / `banner` / `custom` |
| label | text | "Logo Douyin" |
| mode | text | `cover` / `blur` / `inpaint_fast` / `inpaint_ai` / `crop` |
| confidence | numeric null | 0–1, từ dò tự động |
| feather_px | int | mở rộng viền |
| **keyframes** | jsonb | `[{t: 0.0, x: .62, y: .05, w: .34, h: .05}, …]` toạ độ **phần trăm** |
| time_ranges | jsonb | `[[0.0, 4.2], [8.1, 12.0]]` giây |
| enabled | bool | |

### `render_variants` — mỗi nền tảng một bản

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | uuid PK | |
| video_id | uuid FK | |
| target_platform | enum Platform | |
| part_index | int | 1 nếu không chia tập |
| part_total | int | |
| out_path | text null | |
| duration_sec | numeric null | |
| width / height | int null | |
| file_size | bigint null | |
| config_snapshot | jsonb | preset đã dùng — để tái tạo lại đúng bản này |
| qc_passed | bool null | |
| qc_report | jsonb null | `{"logo_residual": false, "av_drift_ms": 42}` |
| created_at | timestamptz | |

### `publish_channels` — kênh Việt Nam

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | uuid PK | |
| platform | enum Platform | |
| external_id | text | channel/account id |
| display_name | text | |
| avatar_url | text null | |
| follower_count | int null | |
| **access_token_enc** | bytea | mã hoá bằng Fernet, KHÔNG lưu plaintext |
| **refresh_token_enc** | bytea null | |
| token_expires_at | timestamptz null | |
| proxy_id | uuid FK null | |
| group_name | text null | "Drama ngắn" |
| daily_quota | int | mặc định 3 |
| allowed_hours | jsonb | `{"from": "08:00", "to": "22:00"}` |
| post_template | jsonb | `{title, desc, hashtags, privacy, category}` |
| process_preset_id | uuid FK null | |
| paused | bool | tự bật true khi có claim |
| paused_reason | text null | |
| created_at / updated_at | timestamptz | |

### `platform_limits` — chỉnh được từ UI

| Cột | Kiểu |
|---|---|
| platform | enum Platform PK |
| max_duration_sec | int |
| max_title_len | int |
| max_desc_len | int |
| max_hashtags | int |
| safe_daily_posts | int |
| aspect_ratios | text[] |
| notes | text null |
| updated_at | timestamptz |

> Seed giá trị ban đầu nhưng **để người dùng chỉnh** — nền tảng đổi giới hạn thường xuyên.

### `pipelines` — luồng tự động

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | uuid PK | |
| name | text | |
| source_channel_ids | uuid[] | |
| filter_config | jsonb | thời lượng, view, tỷ lệ, ngày đăng |
| process_preset_id | uuid FK | |
| schedule_config | jsonb | `{per_day: 3, min_gap_h: 4, hours: [...], prefer_golden: true}` |
| require_approval | bool | |
| auto_pause_on_claim | bool | |
| enabled | bool | |
| stats | jsonb | cache số liệu để không phải đếm mỗi lần |
| created_at | timestamptz | |

### `pipeline_targets`

| pipeline_id | publish_channel_id | priority |
|---|---|---|

### `scheduled_posts`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | uuid PK | |
| render_variant_id | uuid FK | |
| publish_channel_id | uuid FK | |
| scheduled_at | timestamptz | |
| status | text | `pending` / `posting` / `posted` / `failed` / `cancelled` |
| attempt_count | int | |
| external_post_id | text null | |
| external_url | text null | |
| error_message | text null | |
| posted_at | timestamptz null | |

**INDEX** `(status, scheduled_at)` — beat quét bảng này mỗi phút.

### `post_metrics`

| scheduled_post_id | fetched_at | views | likes | comments | shares | watch_time_sec | followers_gained |

Lưu theo chuỗi thời gian (nhiều dòng cho một bài) để vẽ biểu đồ tăng trưởng.

### `job_runs` — nhật ký từng bước

| Cột | Kiểu |
|---|---|
| id | uuid PK |
| video_id | uuid FK |
| step | enum PipelineStep |
| status | text (`running`/`success`/`failed`) |
| celery_task_id | text |
| started_at / finished_at | timestamptz |
| duration_sec | numeric |
| log | text |
| meta | jsonb (`{gpu: true, model: "large-v3"}`) |

Đây là bảng quan trọng nhất khi debug. Đừng bỏ.

### `cost_logs`

| video_id | service | unit | quantity | cost_usd | created_at |

`service`: `llm_translate`, `tts`, `gpu_inpaint`, `bandwidth`.

### `presets`

| id | kind (`filter`/`process`/`antidup`/`subtitle`) | name | config jsonb | is_default |

### `app_settings`

Bảng key-value đơn giản: `key text PK`, `value jsonb`.

### `copyright_claims`

| id | publish_channel_id | scheduled_post_id null | claim_type | detected_at | resolved | source_video_id |

Dùng để tự động chặn lấy tiếp từ nguồn đã gây claim.

---

## Migration đầu tiên nên tạo gì

Chỉ tạo: `videos`, `job_runs`, `subtitles`. Đủ cho M1. Các bảng còn lại thêm dần theo chặng — đừng tạo hết ngay, bạn sẽ đổi thiết kế.

---

# PHẦN 2 — API

Tiền tố `/api/v1`. Trả JSON. Lỗi theo format thống nhất:

```json
{ "error": { "code": "VIDEO_NOT_FOUND", "message": "…", "detail": {} } }
```

## Videos

```
GET    /videos                     ?status=&source_channel_id=&q=&page=&limit=
GET    /videos/{id}
POST   /videos/from-links          { urls: string[], filter_preset_id?, process_preset_id?, target_channel_ids?[] }
                                   → 202 { created: 3, skipped_duplicate: 1, video_ids: [...] }
PATCH  /videos/{id}                { title_vi?, desc_vi?, hashtags_vi?, status? }
DELETE /videos/{id}                ?delete_files=true
POST   /videos/{id}/retry          { from_step?: PipelineStep }
POST   /videos/{id}/approve
POST   /videos/bulk                { ids: [], action: "approve"|"delete"|"apply_preset"|"assign_channels", payload: {} }
```

## Subtitles

```
GET    /videos/{id}/subtitles                 ?lang=vi
PUT    /videos/{id}/subtitles/{lang}          { cues: [...] }        # lưu bản sửa tay
POST   /videos/{id}/subtitles/retranslate     { tone?, glossary_id? }
```

## Mask & detect

```
GET    /videos/{id}/masks
POST   /videos/{id}/masks                     { kind, mode, keyframes, time_ranges }
PATCH  /masks/{mask_id}
DELETE /masks/{mask_id}
POST   /videos/{id}/detect                    { kind: "watermark"|"hardsub" }  → 202 task_id
POST   /videos/{id}/preview                   { start_sec, duration_sec: 5 }   → 202 task_id
```

## Render & variants

```
GET    /videos/{id}/variants
POST   /videos/{id}/render                    { target_platforms: [], preset_overrides?: {} } → 202
GET    /variants/{id}/file                    # stream file
```

## Source channels

```
GET    /source-channels
POST   /source-channels                       { url, scan_interval_min, filter_preset_id, process_preset_id, license_status }
PATCH  /source-channels/{id}
DELETE /source-channels/{id}
POST   /source-channels/{id}/scan-now         → 202
POST   /source-channels/resolve               { url } → { platform, handle, display_name, follower_count, sample_videos: [] }
```

`resolve` dùng cho wizard: dán link xong hiện ngay thông tin kênh trước khi lưu.

## Search nguồn

```
GET    /source/search                         ?q=&platform=&min_views=&duration_min=&duration_max=&sort=
POST   /source/import                         { items: [{platform, video_id}], process_preset_id, target_channel_ids }
```

## Publish channels

```
GET    /channels
GET    /channels/{platform}/oauth-url         → { url, state }
GET    /channels/oauth-callback                # redirect từ nền tảng
POST   /channels/{id}/refresh-token
PATCH  /channels/{id}                         { display_name?, daily_quota?, allowed_hours?, post_template?, paused? }
DELETE /channels/{id}
GET    /channels/{id}/quota-today             → { used: 2, limit: 3, next_slot: "2026-08-06T19:30:00+07:00" }
```

## Pipelines

```
GET    /pipelines
POST   /pipelines                             { name, source_channel_ids, filter_config, process_preset_id,
                                                target_channel_ids, schedule_config, require_approval }
PATCH  /pipelines/{id}                        { enabled? , ... }
DELETE /pipelines/{id}
GET    /pipelines/{id}/stats                  ?days=30
POST   /pipelines/{id}/run-now                → 202
```

## Schedule

```
GET    /schedule                              ?from=&to=&channel_id=
POST   /schedule                              { render_variant_id, publish_channel_id, scheduled_at }
POST   /schedule/bulk                         { video_ids: [], channel_ids: [], strategy: "golden"|"even"|"now",
                                                start_at?, per_day?, min_gap_hours? }
                                              → { created: 15, conflicts: [] }
POST   /schedule/auto-distribute              { days_ahead: 7, prefer_golden: true, hours: {...} }
PATCH  /schedule/{id}                         { scheduled_at? }         # kéo thả đổi giờ
DELETE /schedule/{id}
POST   /schedule/{id}/post-now                → 202
```

## Platform limits & presets & settings

```
GET    /platform-limits
PATCH  /platform-limits/{platform}
GET    /presets                               ?kind=
POST   /presets
PATCH  /presets/{id}
GET    /settings
PATCH  /settings                              { key: value, ... }
POST   /settings/test-connection              { service: "llm"|"tts"|"ffmpeg" }
```

## Stats

```
GET    /stats/overview                        ?days=30
GET    /stats/by-platform                     ?days=30
GET    /stats/by-source                       ?days=30
GET    /stats/by-preset                       ?days=30
GET    /stats/costs                           ?days=30
GET    /stats/golden-hours                    → [{hour: 20, score: 100}, ...]
```

## Jobs & realtime

```
GET    /jobs/active                           → danh sách job đang chạy
GET    /videos/{id}/job-runs
POST   /jobs/{celery_task_id}/cancel

WS     /ws
```

### Sự kiện WebSocket

Client gửi `{"subscribe": ["video:abc-123", "queue"]}`.

Server đẩy:

```json
{"type":"progress","video_id":"abc","step":"render","percent":68}
{"type":"status","video_id":"abc","status":"ready","step":null}
{"type":"queue","active":4,"pending":12}
{"type":"alert","level":"error","title":"Content ID claim","channel_id":"..."}
{"type":"post","scheduled_post_id":"...","status":"posted","url":"https://..."}
```

---

## Quy ước API

1. **Mọi việc chạy lâu trả `202` + `task_id`**, không bao giờ chờ trong request.
2. **Phân trang mặc định 50**, trả `{items, total, page, limit}`.
3. **Không trả token** trong bất kỳ response nào, kể cả dạng đã che.
4. **Xoá là soft delete** với `videos` (thêm `deleted_at`), hard delete với file trên đĩa theo cờ riêng.
5. **Idempotency**: `POST /videos/from-links` với cùng URL trả về video cũ, không tạo mới.
6. Timestamp luôn ISO 8601 **có timezone**, lưu UTC, hiển thị theo `Asia/Ho_Chi_Minh`.
