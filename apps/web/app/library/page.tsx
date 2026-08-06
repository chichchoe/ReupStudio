"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { VideoRow } from "@/components/VideoRow";
import { api } from "@/lib/api";
import { STATUS_LABEL, type VideoStatus } from "@/lib/types";
import { useReupSocket } from "@/lib/ws";

const FILTERS: (VideoStatus | "all")[] = [
  "all",
  "queued",
  "running",
  "review",
  "ready",
  "error",
];

function LibraryInner() {
  const params = useSearchParams();
  const [status, setStatus] = useState<string>(params.get("status") ?? "all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const queryClient = useQueryClient();

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["videos"] });
    queryClient.invalidateQueries({ queryKey: ["counts"] });
  };

  const { progress } = useReupSocket(refresh);

  const { data, isLoading } = useQuery({
    queryKey: ["videos", status, query],
    queryFn: () => api.listVideos({ status, q: query || undefined }),
    refetchInterval: 15_000,
  });
  const { data: counts } = useQuery({ queryKey: ["counts"], queryFn: api.counts });

  const retryMutation = useMutation({
    mutationFn: (id: string) => api.retry(id),
    onSuccess: refresh,
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.remove(id),
    onSuccess: refresh,
  });
  const bulkMutation = useMutation({
    mutationFn: ({ ids, action }: { ids: string[]; action: "approve" | "delete" | "retry" }) =>
      api.bulk(ids, action),
    onSuccess: () => {
      setSelected(new Set());
      refresh();
    },
  });

  const videos = useMemo(() => data?.items ?? [], [data]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div>
      <header className="flex items-start justify-between gap-4 mb-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold">Thư viện</h1>
          <p className="text-[13px] text-muted mt-0.5">
            {data ? `${data.total} video` : "đang tải…"}
          </p>
        </div>
        <input
          className="input w-72"
          placeholder="🔍 Tìm theo tiêu đề hoặc tác giả…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </header>

      <div className="flex gap-2 flex-wrap mb-3">
        {FILTERS.map((key) => (
          <button
            key={key}
            onClick={() => setStatus(key)}
            className={clsx("chip", status === key && "chip-active")}
          >
            {key === "all" ? "Tất cả" : STATUS_LABEL[key as VideoStatus]}
            {counts?.[key] != null && ` · ${counts[key]}`}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-[13px] text-muted py-8 text-center">Đang tải…</p>}

      {!isLoading && videos.length === 0 && (
        <div className="text-center py-16 text-muted text-[13px]">
          Chưa có video nào khớp bộ lọc.
        </div>
      )}

      {videos.map((video) => (
        <VideoRow
          key={video.id}
          video={video}
          progress={progress[video.id]}
          selected={selected.has(video.id)}
          onToggle={toggle}
          onRetry={(id) => retryMutation.mutate(id)}
          onDelete={(id) => deleteMutation.mutate(id)}
        />
      ))}

      {selected.size > 0 && (
        <div className="sticky bottom-0 flex items-center gap-2.5 bg-panel2 border border-accent/30 rounded-xl px-4 py-3 mt-3 shadow-[0_-6px_26px_rgba(0,0,0,0.4)]">
          <span className="text-[13px] font-medium">Đã chọn {selected.size} video</span>
          <button
            className="btn btn-sm"
            onClick={() =>
              bulkMutation.mutate({ ids: [...selected], action: "retry" })
            }
          >
            Xử lý lại
          </button>
          <button
            className="btn btn-sm text-err border-err/35 ml-auto"
            onClick={() => bulkMutation.mutate({ ids: [...selected], action: "delete" })}
          >
            Xoá
          </button>
        </div>
      )}
    </div>
  );
}

export default function LibraryPage() {
  return (
    <Suspense fallback={<p className="text-[13px] text-muted">Đang tải…</p>}>
      <LibraryInner />
    </Suspense>
  );
}
