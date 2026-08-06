/**
 * Client gọi API. KHÔNG gọi fetch trực tiếp trong component — mọi lời gọi đi qua đây.
 */

import type {
  BulkAction,
  BulkResult,
  CreateFromLinksResult,
  JobRun,
  Page,
  Preset,
  PresetKind,
  Subtitle,
  Video,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
const PREFIX = `${BASE}/api/v1`;

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
};

export const WS_URL = `${BASE.replace(/^http/, "ws")}/ws`;
