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

/** Sự kiện đẩy xuống qua WebSocket. */
export type WsEvent =
  | { type: "hello"; clients: number }
  | { type: "progress"; video_id: string; step: PipelineStep; percent: number; note?: string }
  | { type: "status"; video_id: string; status: VideoStatus; step: PipelineStep | null; error?: string }
  | { type: "queue"; active: number; pending: number }
  | { type: "alert"; level: string; title: string; detail?: string };
