/**
 * Client gọi API. KHÔNG gọi fetch trực tiếp trong component — mọi lời gọi đi qua đây.
 */

import type {
  BulkAction,
  BulkResult,
  CreateFromLinksResult,
  JobRun,
  Page,
  PlatformLimit,
  PlatformLimitUpdate,
  Preset,
  PresetKind,
  RenderAccepted,
  RenderVariant,
  ResolveChannelResult,
  SourceChannel,
  SourceChannelCreate,
  SourceChannelUpdate,
  Subtitle,
  Video,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
const PREFIX = `${BASE}/api/v1`;

/**
 * Các kiểu dưới đây TẠM KHAI TAY vì endpoint `/llm/*` và `/videos/{id}/translate`
 * chưa lên lúc viết phần giao diện này. Sinh lại từ OpenAPI (`npm run types`) và
 * xoá phần khai tay khi endpoint đã có thật — CLAUDE.md cấm gõ tay interface
 * trùng backend về lâu dài.
 */
export interface LlmModels {
  /** Model dùng cho bước dịch — chỉ danh sách này được đổ vào dropdown chọn model. */
  translate: string[];
  tts: string[];
}

/**
 * Số liệu hạn mức LLM. Trần bằng 0 nghĩa là KHÔNG giới hạn (không phải "hết
 * hạn mức") — khi đó giao diện chỉ hiện số đã dùng, không hiện phần "/trần" và
 * không bao giờ cảnh báo.
 *
 * Tên trường khớp đúng `GET /api/v1/llm/usage` — đã đối chiếu với API chạy thật.
 * Dùng tiếng Anh cho đồng nhất với mọi endpoint sẵn có của dự án
 * (`skipped_duplicate`, `duplicate_ids`, `source_platform`...).
 */
export interface LlmUsage {
  requests_last_min: number;
  requests_last_day: number;
  tokens_last_day: number;
  cost_usd_this_month: number;
  max_requests_per_min: number;
  max_requests_per_day: number;
  monthly_budget_usd: number;
}

/** Response `202` của `POST /videos/{id}/translate` — nhận task_id ngay, không chờ dịch xong. */
export interface TranslateAccepted {
  task_id: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${PREFIX}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });

  if (!res.ok) {
    let code = "UNKNOWN";
    let message = `Lỗi ${res.status}`;
    try {
      const body = await res.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? body?.detail ?? message;
    } catch {
      /* body không phải JSON */
    }
    throw new ApiError(message, code, res.status);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () =>
    request<{ ok: boolean; db: boolean; redis: boolean; version: string }>("/health"),

  listVideos: (params: { status?: string; q?: string; page?: number; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.status && params.status !== "all") qs.set("status", params.status);
    if (params.q) qs.set("q", params.q);
    qs.set("page", String(params.page ?? 1));
    qs.set("limit", String(params.limit ?? 50));
    return request<Page<Video>>(`/videos?${qs}`);
  },

  counts: () => request<Record<string, number>>("/videos/counts"),

  getVideo: (id: string) => request<Video>(`/videos/${id}`),

  createFromLinks: (urls: string[], processConfig: Record<string, unknown> = {}) =>
    request<CreateFromLinksResult>("/videos/from-links", {
      method: "POST",
      body: JSON.stringify({ urls, process_config: processConfig, autostart: true }),
    }),

  retry: (id: string, fromStep?: string) =>
    request<{ task_id: string | null; message: string }>(
      `/videos/${id}/retry${fromStep ? `?from_step=${fromStep}` : ""}`,
      { method: "POST" },
    ),

  approve: (id: string) => request<Video>(`/videos/${id}/approve`, { method: "POST" }),

  remove: (id: string) => request<void>(`/videos/${id}`, { method: "DELETE" }),

  bulk: (ids: string[], action: BulkAction, payload: Record<string, unknown> = {}) =>
    request<BulkResult>("/videos/bulk", {
      method: "POST",
      body: JSON.stringify({ ids, action, payload }),
    }),

  subtitles: (id: string, lang?: string) =>
    request<Subtitle[]>(`/videos/${id}/subtitles${lang ? `?lang=${lang}` : ""}`),

  jobRuns: (id: string) => request<JobRun[]>(`/videos/${id}/job-runs`),

  fileUrl: (id: string) => `${PREFIX}/videos/${id}/file`,

  listPresets: (kind?: PresetKind) =>
    request<Preset[]>(`/presets${kind ? `?kind=${kind}` : ""}`),

  listSourceChannels: () => request<SourceChannel[]>("/source-channels"),

  /** Chỉ phân tích chuỗi URL, KHÔNG gọi mạng — xem docstring `ResolveChannelResult`. */
  resolveSourceChannel: (url: string) =>
    request<ResolveChannelResult>("/source-channels/resolve", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  createSourceChannel: (body: SourceChannelCreate) =>
    request<SourceChannel>("/source-channels", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateSourceChannel: (id: string, body: SourceChannelUpdate) =>
    request<SourceChannel>(`/source-channels/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteSourceChannel: (id: string) =>
    request<void>(`/source-channels/${id}`, { method: "DELETE" }),

  // M4-FE-01: giới hạn nền tảng + render nhiều bản + variant.
  listPlatformLimits: () => request<PlatformLimit[]>("/platform-limits"),

  updatePlatformLimit: (platform: string, body: PlatformLimitUpdate) =>
    request<PlatformLimit>(`/platform-limits/${platform}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  renderVideo: (id: string, targetPlatforms: string[], presetOverrides: Record<string, unknown> = {}) =>
    request<RenderAccepted>(`/videos/${id}/render`, {
      method: "POST",
      body: JSON.stringify({ target_platforms: targetPlatforms, preset_overrides: presetOverrides }),
    }),

  listVariants: (id: string) => request<RenderVariant[]>(`/videos/${id}/variants`),

  // Tab "Chờ dịch": chọn model AI rồi bấm dịch cho video đang ở trạng thái `review`.
  llmModels: () => request<LlmModels>("/llm/models"),

  llmUsage: () => request<LlmUsage>("/llm/usage"),

  /** Trả `202` ngay — bước dịch chạy qua Celery, tiến trình theo dõi bằng WebSocket. */
  translateVideo: (id: string, llmModel: string) =>
    request<TranslateAccepted>(`/videos/${id}/translate`, {
      method: "POST",
      body: JSON.stringify({ llm_model: llmModel }),
    }),

  variantFileUrl: (variantId: string) => `${PREFIX}/variants/${variantId}/file`,
};

export const WS_URL = `${BASE.replace(/^http/, "ws")}/ws`;
