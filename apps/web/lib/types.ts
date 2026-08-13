/**
 * Kiểu dữ liệu tạm dùng cho M1.
 *
 * Khi API ổn định, sinh lại từ OpenAPI thay vì gõ tay:
 *   npm run types      → lib/types.gen.ts
 */

export type VideoStatus =
  | "queued"
  | "running"
  | "review"
  | "ready"
  | "scheduled"
  | "posted"
  | "error"
  | "skipped";

export type PipelineStep =
  | "download"
  | "probe"
  | "transcribe"
  | "translate"
  | "format_sub"
  | "render"
  // M4-FE-01: task render nhiều bản dùng bước "shortform" (PipelineStep.SHORTFORM
  // ở backend), KHÔNG phải "render" — hai task chạy nối tiếp, dùng chung "render"
  // sẽ khiến thanh tiến trình tụt về 0% rồi leo lại (xem docstring
  // apps/worker/src/tasks/video.py::render_variants_task).
  | "shortform";

export const M1_STEPS: PipelineStep[] = [
  "download",
  "probe",
  "transcribe",
  "translate",
  "format_sub",
  "render",
];

export const STEP_LABEL: Record<PipelineStep, string> = {
  download: "Tải",
  probe: "Đọc thông số",
  transcribe: "Nhận dạng",
  translate: "Dịch",
  format_sub: "Chuẩn hoá sub",
  render: "Render",
  shortform: "Chuẩn hoá video ngắn",
};

export const STATUS_LABEL: Record<VideoStatus, string> = {
  queued: "Chờ xử lý",
  running: "Đang chạy",
  review: "Chờ duyệt",
  ready: "Sẵn sàng",
  scheduled: "Đã xếp lịch",
  posted: "Đã đăng",
  error: "Lỗi",
  skipped: "Bỏ qua",
};

export interface Video {
  id: string;
  source_platform: string;
  source_video_id: string;
  source_url: string;
  source_author: string | null;
  title_original: string | null;
  title_vi: string | null;
  duration_sec: number | null;
  width: number | null;
  height: number | null;
  status: VideoStatus;
  current_step: PipelineStep | null;
  error_message: string | null;
  flags: Record<string, unknown>;
  out_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
}

export interface JobRun {
  step: PipelineStep;
  status: "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  duration_sec: number | null;
  log: string | null;
  meta: Record<string, unknown>;
}

export interface SubtitleCue {
  i: number;
  start: number;
  end: number;
  text: string;
}

export interface Subtitle {
  lang: string;
  source: string;
  edited_by_user: boolean;
  cues: SubtitleCue[];
}

export interface CreateFromLinksResult {
  created: number;
  skipped_duplicate: number;
  invalid: string[];
  video_ids: string[];
}

export type PresetKind = "filter" | "process" | "antidup" | "subtitle";

export interface Preset {
  id: string;
  kind: PresetKind;
  name: string;
  config: Record<string, unknown>;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

/** Khớp `Literal[...]` của `BulkAction.action` ở backend (`schemas/video.py`). */
export type BulkAction = "approve" | "delete" | "retry" | "apply_preset" | "assign_channels";

export interface BulkSkip {
  id: string;
  reason: string;
}

/** Response của `POST /videos/bulk` — `skipped` LUÔN kèm lý do, không được bỏ qua khi hiển thị. */
export interface BulkResult {
  affected: number;
  action: string;
  skipped: BulkSkip[];
}

/** Khớp `LicenseStatus` (StrEnum) ở `reup_core/enums.py`. */
export type LicenseStatus = "unknown" | "permitted" | "licensed" | "open" | "own";

/**
 * Nhãn tiếng Việt cho tình trạng bản quyền. `unknown` là chốt an toàn pháp lý —
 * backend chặn xử lý tự động cho kênh này, giao diện phải hiển thị rõ, không
 * làm mờ nhạt đi (xem `LicenseStatusBadge`).
 */
export const LICENSE_STATUS_LABEL: Record<LicenseStatus, string> = {
  unknown: "Chưa rõ",
  permitted: "Đã xin phép",
  licensed: "Có hợp đồng",
  open: "Nguồn mở",
  own: "Của mình",
};

/** Khớp `SourceChannelOut` ở `schemas/source_channel.py`. */
export interface SourceChannel {
  id: string;
  platform: string;
  external_id: string;
  handle: string | null;
  display_name: string | null;
  url: string;
  scan_interval_min: number;
  last_scanned_at: string | null;
  last_seen_video_id: string | null;
  filter_preset_id: string | null;
  process_preset_id: string | null;
  license_status: LicenseStatus;
  license_note: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

/** Khớp `SourceChannelCreate` ở `schemas/source_channel.py`. */
export interface SourceChannelCreate {
  platform: string;
  external_id: string;
  url: string;
  handle?: string | null;
  display_name?: string | null;
  scan_interval_min?: number;
  filter_preset_id?: string | null;
  process_preset_id?: string | null;
  license_status?: LicenseStatus;
  license_note?: string | null;
  enabled?: boolean;
}

/** Khớp `SourceChannelUpdate` ở `schemas/source_channel.py` — mọi trường tuỳ chọn. */
export interface SourceChannelUpdate {
  handle?: string | null;
  display_name?: string | null;
  scan_interval_min?: number;
  last_seen_video_id?: string | null;
  filter_preset_id?: string | null;
  process_preset_id?: string | null;
  license_status?: LicenseStatus;
  license_note?: string | null;
  enabled?: boolean;
}

/**
 * Khớp `ResolveChannelResult` ở `schemas/source_channel.py`. `display_name`,
 * `follower_count`, `sample_videos` LUÔN null/rỗng ở M2 — endpoint chỉ phân
 * tích chuỗi URL, không gọi mạng. Đừng thiết kế UI dựa trên các trường này.
 */
export interface ResolveChannelResult {
  platform: string;
  external_id: string;
  handle: string | null;
  url: string;
  display_name: string | null;
  follower_count: number | null;
  sample_videos: string[];
  needs_scan: boolean;
}

/** Sự kiện đẩy xuống qua WebSocket. */
export type WsEvent =
  | { type: "hello"; clients: number }
  | { type: "progress"; video_id: string; step: PipelineStep; percent: number; note?: string }
  | { type: "status"; video_id: string; status: VideoStatus; step: PipelineStep | null; error?: string }
  | { type: "queue"; active: number; pending: number }
  | { type: "alert"; level: string; title: string; detail?: string };

/** Khớp giá trị enum `Platform` ở `reup_core/enums.py` — nền tảng đăng đích. */
export type TargetPlatform = "tiktok" | "youtube" | "facebook" | "instagram" | "zalo";

/** Nhãn tiếng Việt cho nền tảng đích, dùng ở bảng giới hạn và chọn nền tảng render. */
export const TARGET_PLATFORM_LABEL: Record<TargetPlatform, string> = {
  tiktok: "TikTok",
  youtube: "YouTube Shorts",
  facebook: "Facebook Reels",
  instagram: "Instagram Reels",
  zalo: "Zalo",
};

/**
 * Vùng an toàn cho phụ đề, toạ độ PHẦN TRĂM 0–1 (không phải pixel — luật số 2
 * CLAUDE.md). Mỗi khoá là tỉ lệ khung hình bị chắn tính từ cạnh tương ứng.
 */
export interface SafeArea {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

/** Khớp `PlatformLimitOut` ở `schemas/platform_limit.py`. */
export interface PlatformLimit {
  platform: string;
  /** 0 = KHÔNG giới hạn thời lượng (không phải dữ liệu thiếu). */
  max_duration_sec: number;
  max_title_len: number;
  max_desc_len: number;
  max_hashtags: number;
  safe_daily_posts: number;
  aspect_ratios: string[];
  safe_area: SafeArea;
  notes: string | null;
  updated_at: string;
}

/** Khớp `PlatformLimitUpdate` ở `schemas/platform_limit.py` — mọi trường tuỳ chọn. */
export interface PlatformLimitUpdate {
  max_duration_sec?: number;
  max_title_len?: number;
  max_desc_len?: number;
  max_hashtags?: number;
  safe_daily_posts?: number;
  aspect_ratios?: string[];
  safe_area?: SafeArea;
  notes?: string | null;
}

/** Khớp `TaskAccepted` (`schemas/common.py`) — response `202` của `POST /videos/{id}/render`. */
export interface RenderAccepted {
  task_id: string | null;
  message: string;
}

/** Khớp `RenderVariantOut` ở `schemas/render.py`. */
export interface RenderVariant {
  id: string;
  video_id: string;
  target_platform: string;
  part_index: number;
  part_total: number;
  out_path: string | null;
  duration_sec: number | null;
  width: number | null;
  height: number | null;
  file_size: number | null;
  qc_passed: boolean | null;
}
