/**
 * Kiểu dữ liệu cho frontend.
 *
 * File này KHÔNG khai lại thứ backend đã khai (luật số 7 CLAUDE.md). Mọi kiểu
 * mô tả dữ liệu API đều dẫn xuất từ `lib/types.gen.ts` — file sinh tự động:
 *
 *     pnpm types      # đọc http://localhost:8000/openapi.json
 *
 * Ở đây chỉ còn ba loại nội dung:
 *
 * 1. Bí danh đặt tên gọn cho kiểu sinh ra (`Video` thay cho `VideoOut`).
 * 2. Thứ OpenAPI không mô tả được: sự kiện WebSocket, kiểu generic `Page<T>`.
 * 3. Nhãn hiển thị tiếng Việt — thuộc về giao diện, không thuộc về API.
 *
 * Chạy lại `pnpm types` mỗi khi đổi schema backend. Nếu một union ở đây sinh ra
 * `string` thay vì tập giá trị, đó là dấu hiệu schema backend đang khai `str`
 * thay vì enum — sửa ở backend, đừng gõ tay lại ở đây.
 */

import type { components } from "./types.gen";

type S = components["schemas"];

// --------------------------------------------------------------------------
// Dẫn xuất thẳng từ OpenAPI
// --------------------------------------------------------------------------

export type VideoStatus = S["VideoStatus"];
export type PipelineStep = S["PipelineStep"];
export type Video = S["VideoOut"];
export type VideoDetail = S["VideoDetail"];
export type JobRun = S["JobRunOut"];
export type SubtitleCue = S["SubtitleCue"];
export type Subtitle = S["SubtitleOut"];
export type CreateFromLinksResult = S["CreateFromLinksResult"];
export type PresetKind = S["PresetKind"];
export type Preset = S["PresetOut"];
export type LicenseStatus = S["LicenseStatus"];
export type SourceChannel = S["SourceChannelOut"];
export type SourceChannelCreate = S["SourceChannelCreate"];
export type SourceChannelUpdate = S["SourceChannelUpdate"];
export type ResolveChannelResult = S["ResolveChannelResult"];
export type SafeArea = S["SafeArea"];
export type PlatformLimit = S["PlatformLimitOut"];
export type PlatformLimitUpdate = S["PlatformLimitUpdate"];
export type RenderVariant = S["RenderVariantOut"];
export type BulkSkip = S["BulkSkip"];
export type LlmModels = S["LlmModelsOut"];
export type LlmUsage = S["LlmUsageOut"];

/** Response `202` của các endpoint chạy nền — chỉ trả `task_id`, không chờ. */
export type RenderAccepted = S["TaskAccepted"];

/** Nền tảng ĐĂNG đích (`Platform` ở `reup_core/enums.py`), khác nền tảng nguồn. */
export type TargetPlatform = S["Platform"];

/** Tên hành động của `POST /videos/bulk`, tách ra từ body để dùng riêng. */
export type BulkAction = S["BulkAction"]["action"];

/**
 * Response của `POST /videos/bulk` — `skipped` LUÔN kèm lý do, không được bỏ
 * qua khi hiển thị: video bị bỏ qua âm thầm khiến người dùng tưởng cả lô đã
 * duyệt xong.
 */
export type BulkResult = S["BulkResult"];

// --------------------------------------------------------------------------
// Thứ OpenAPI không mô tả được
// --------------------------------------------------------------------------

/**
 * Trang kết quả. OpenAPI sinh ra một schema RIÊNG cho mỗi kiểu phần tử
 * (`Page_VideoOut_`, …) nên không dùng lại được dưới dạng generic. Hình dạng
 * khớp `Page_VideoOut_` — đổi bên backend thì phải đổi ở đây.
 */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
}

/**
 * Sự kiện đẩy xuống qua WebSocket. KHÔNG nằm trong OpenAPI — FastAPI không mô
 * tả kênh WebSocket — nên đây là chỗ duy nhất mô tả chúng. Phải khớp tay với
 * `apps/api/src/ws/manager.py`.
 */
export type WsEvent =
  | { type: "hello"; clients: number }
  | { type: "progress"; video_id: string; step: PipelineStep; percent: number; note?: string }
  | {
      type: "status";
      video_id: string;
      status: VideoStatus;
      step: PipelineStep | null;
      error?: string;
    }
  | { type: "queue"; active: number; pending: number }
  | { type: "alert"; level: string; title: string; detail?: string };

// --------------------------------------------------------------------------
// Hằng số và nhãn hiển thị — thuộc giao diện, không thuộc API
// --------------------------------------------------------------------------

/**
 * Các bước chạy trong chuỗi xử lý, theo đúng thứ tự hiển thị trên thanh tiến
 * trình. Phải khớp `M1_STEPS` ở `reup_core/enums.py` — thiếu bước nào thì thanh
 * tiến trình đứng im trong lúc bước đó chạy, và người dùng tưởng máy treo.
 *
 * `detect` và `inpaint` (xoá chữ cứng) chạy hàng chục phút trên video dài, nên
 * bỏ sót chúng ở đây là bỏ sót đúng quãng chờ lâu nhất.
 */
export const M1_STEPS: PipelineStep[] = [
  "download",
  "probe",
  "transcribe",
  "translate",
  "format_sub",
  "detect",
  "inpaint",
  "tts",
  "render",
];

/**
 * Nhãn cho MỌI bước backend có thể trả về, kể cả bước chưa dùng tới. Thiếu một
 * khoá là lỗi biên dịch — đó là chủ ý: thêm bước mới ở backend thì buộc phải
 * đặt tên tiếng Việt cho nó, thay vì để giao diện hiện ra mã thô.
 */
export const STEP_LABEL: Record<PipelineStep, string> = {
  download: "Tải",
  probe: "Đọc thông số",
  transcribe: "Nhận dạng",
  translate: "Dịch",
  format_sub: "Chuẩn hoá sub",
  detect: "Dò watermark",
  inpaint: "Xoá watermark",
  // M4-FE-01: task render nhiều bản dùng bước "shortform" (PipelineStep.SHORTFORM
  // ở backend), KHÔNG phải "render" — hai task chạy nối tiếp, dùng chung "render"
  // sẽ khiến thanh tiến trình tụt về 0% rồi leo lại (xem docstring
  // apps/worker/src/tasks/video.py::render_variants_task).
  shortform: "Chuẩn hoá video ngắn",
  tts: "Lồng tiếng",
  render: "Render",
  qc: "Kiểm tra",
  upload: "Đăng",
};

export const STATUS_LABEL: Record<VideoStatus, string> = {
  queued: "Chờ xử lý",
  running: "Đang chạy",
  review: "Chờ dịch",
  ready: "Sẵn sàng",
  scheduled: "Đã xếp lịch",
  posted: "Đã đăng",
  error: "Lỗi",
  skipped: "Bỏ qua",
};

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

/** Nhãn tiếng Việt cho nền tảng đích, dùng ở bảng giới hạn và chọn nền tảng render. */
export const TARGET_PLATFORM_LABEL: Record<TargetPlatform, string> = {
  tiktok: "TikTok",
  youtube: "YouTube Shorts",
  facebook: "Facebook Reels",
  instagram: "Instagram Reels",
  zalo: "Zalo",
};
