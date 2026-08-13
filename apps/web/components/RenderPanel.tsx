"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { TARGET_PLATFORM_LABEL } from "@/lib/types";
import type { VideoProgress } from "@/lib/ws";

interface Props {
  videoId: string;
  /** Tiến trình realtime của video này, đọc từ `useReupSocket` ở trang cha — KHÔNG polling. */
  progress?: VideoProgress;
}

/**
 * Chọn nền tảng đích rồi bấm render. Gọi `POST /videos/{id}/render`, nhận
 * `202` ngay (không chờ render xong) rồi theo dõi tiến trình qua tiến trình
 * WebSocket đã subscribe sẵn ở trang cha — bước render nhiều bản dùng
 * `step: "shortform"`, không phải `"render"`.
 */
export function RenderPanel({ videoId, progress }: Props) {
  const { data: limits } = useQuery({
    queryKey: ["platform-limits"],
    queryFn: api.listPlatformLimits,
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const isRendering = progress?.step === "shortform";

  const mutation = useMutation({
    mutationFn: () => api.renderVideo(videoId, [...selected]),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["variants", videoId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Render thất bại"),
  });

  const toggle = (platform: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(platform)) next.delete(platform);
      else next.add(platform);
      return next;
    });
  };

  return (
    <div className="card">
      <div className="text-[13px] font-medium mb-2.5">Chọn nền tảng đích rồi render</div>

      <div className="flex gap-2 flex-wrap mb-3">
        {limits?.map((limit) => (
          <label
            key={limit.platform}
            className="flex items-center gap-1.5 bg-panel2 border border-border rounded-lg px-2.5 py-1.5 text-[12.5px] cursor-pointer"
          >
            <input
              type="checkbox"
              checked={selected.has(limit.platform)}
              onChange={() => toggle(limit.platform)}
            />
            {TARGET_PLATFORM_LABEL[limit.platform as keyof typeof TARGET_PLATFORM_LABEL] ??
              limit.platform}
          </label>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <button
          className="btn btn-primary btn-sm"
          disabled={selected.size === 0 || mutation.isPending || isRendering}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? "Đang gửi…" : "⚡ Render"}
        </button>

        {isRendering && (
          <div className="flex items-center gap-2 text-[12px] text-muted">
            <span className="w-28 h-[6px] bg-bg rounded-full overflow-hidden">
              <span
                className="block h-full bg-run transition-all duration-500"
                style={{ width: `${progress?.percent ?? 0}%` }}
              />
            </span>
            <span>Đang chuẩn hoá… {progress?.percent ?? 0}%</span>
          </div>
        )}

        {!isRendering && mutation.isSuccess && (
          <span className="text-[12px] text-ok">Đã đưa vào hàng đợi render.</span>
        )}
      </div>

      {error && <p className="text-[12px] text-err mt-2">{error}</p>}
    </div>
  );
}
