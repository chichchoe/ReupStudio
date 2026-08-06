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
  | "render";

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
