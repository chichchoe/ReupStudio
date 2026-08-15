/**
 * Client gọi API. KHÔNG gọi fetch trực tiếp trong component — mọi lời gọi đi qua đây.
 */

import type { components } from "./types.gen";
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
  CauHinh,
  TtsOptions,
  TuyChonDich,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
const PREFIX = `${BASE}/api/v1`;

/**
 * Kiểu của ba endpoint mới SINH TỪ OpenAPI (`npm run types` → `types.gen.ts`),
 * không gõ tay — luật số 7 CLAUDE.md. Lúc dựng giao diện, endpoint chưa lên nên
 * phải khai tạm; nay đã có thật thì lấy thẳng từ schema để hai bên không bao
 * giờ lệch nhau nữa (đã lệch một lần: tên trường tiếng Việt vs tiếng Anh).
 *
 * `lib/types.ts` còn lại vẫn là bản gõ tay tạm cho M1 — chuyển nốt sang bản
 * sinh là việc riêng, không gộp vào đây.
 */
type Schemas = components["schemas"];

/** Trần bằng 0 nghĩa là KHÔNG giới hạn, không phải "đã hết hạn mức". */
export type LlmUsage = Schemas["LlmUsageOut"];

/** Chỉ nhóm `translate` được đổ vào ô chọn model dịch. */
export type LlmModels = Schemas["LlmModelsOut"];

/** Response `202` — nhận `task_id` ngay, không chờ dịch xong. */
export type TranslateAccepted = Schemas["TaskAccepted"];

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

  /** Giọng đọc chọn được, nhóm theo nhà cung cấp, kèm đánh đổi hạn mức. */
  ttsOptions: () => request<TtsOptions[]>("/videos/tts-options"),

  /**
   * Trả `202` ngay — bước dịch chạy qua Celery, tiến trình theo dõi bằng WebSocket.
   *
   * `xoaChuCung` và giọng đọc gửi kèm ngay tại đây chứ không qua một lời gọi
   * riêng: worker nhận task gần như tức thì, tách làm hai lời gọi thì nó có thể
   * đọc phải cấu hình cũ.
   */
  translateVideo: (id: string, tuyChon: TuyChonDich) =>
    request<TranslateAccepted>(`/videos/${id}/translate`, {
      method: "POST",
      body: JSON.stringify({
        llm_model: tuyChon.llmModel,
        xoa_chu_cung: tuyChon.xoaChuCung,
        tts_provider: tuyChon.ttsProvider,
        giong_doc: tuyChon.giongDoc,
        tts_model: tuyChon.ttsModel ?? null,
      }),
    }),

  /** Duyệt bản dịch và giọng đọc — cho chạy tiếp chặng xoá chữ cứng và render. */
  approveDub: (id: string) =>
    request<TranslateAccepted>(`/videos/${id}/approve-dub`, { method: "POST" }),

  /** Cấu hình ứng dụng. Bí mật LUÔN về dạng che — không bao giờ có giá trị thật. */
  cauHinh: () => request<CauHinh>("/settings"),

  /**
   * Lưu cấu hình. Chỉ gửi những khoá thật sự đổi.
   *
   * Ô bí mật để trống nghĩa là GIỮ NGUYÊN, không phải xoá — giao diện không
   * bao giờ nhận được giá trị thật nên nó không thể gửi lại cái đang có.
   */
  luuCauHinh: (giaTri: Record<string, string>) =>
    request<CauHinh>("/settings", {
      method: "PUT",
      body: JSON.stringify({ gia_tri: giaTri }),
    }),

  sinhKhoaMaHoa: () =>
    request<{ khoa: string; huong_dan: string }>("/settings/sinh-khoa-ma-hoa", {
      method: "POST",
    }),

  /** URL dải tiếng Việt để nghe thử trong thẻ `<audio>`. */
  voiceTrackUrl: (id: string) => `${PREFIX}/videos/${id}/voice-track`,

  variantFileUrl: (variantId: string) => `${PREFIX}/variants/${variantId}/file`,
};

export const WS_URL = `${BASE.replace(/^http/, "ws")}/ws`;
