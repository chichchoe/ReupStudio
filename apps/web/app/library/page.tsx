"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { BulkActionBar } from "@/components/BulkActionBar";
import { BulkSkipNotice } from "@/components/BulkSkipNotice";
import { StatusChips } from "@/components/StatusChips";
import { VideoRow } from "@/components/VideoRow";
import { api } from "@/lib/api";
import type { BulkResult } from "@/lib/types";
import { useLibraryMutations } from "@/lib/useLibraryMutations";
import { useReupSocket } from "@/lib/ws";

/** Chờ 300ms sau lần gõ cuối mới bắn request tìm kiếm — tránh gọi API mỗi phím. */
const SEARCH_DEBOUNCE_MS = 300;

function LibraryInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState<string>(params.get("status") ?? "all");
  const [queryInput, setQueryInput] = useState(params.get("q") ?? "");
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkNotice, setBulkNotice] = useState<BulkResult | null>(null);
  const queryClient = useQueryClient();

  // Debounce ô tìm kiếm, đồng thời đồng bộ vào query string để tải lại trang
  // vẫn giữ từ khoá đang tìm.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(queryInput);
      const next = new URLSearchParams(params.toString());
      if (queryInput) next.set("q", queryInput);
      else next.delete("q");
      router.replace(`?${next.toString()}`, { scroll: false });
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // Chỉ debounce theo giá trị gõ — params/router lấy tại thời điểm chạy timer,
    // đưa vào deps sẽ chạy lại effect mỗi lần URL đổi (kể cả do chính nó gây ra).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryInput]);

  const { data, isLoading } = useQuery({
    queryKey: ["videos", status, query],
    queryFn: () => api.listVideos({ status, q: query || undefined }),
  });
  const { data: counts } = useQuery({ queryKey: ["counts"], queryFn: api.counts });

  const videos = useMemo(() => data?.items ?? [], [data]);

  // Chỉ video đang chạy/chờ mới cần theo dõi tiến trình — subscribe sớm cả
  // "queued" để không lỡ mất progress đầu tiên khi video chuyển sang running.
  const activeTopics = useMemo(
    () =>
      videos
        .filter((v) => v.status === "running" || v.status === "queued")
        .map((v) => `video:${v.id}`),
    [videos],
  );

  const { progress } = useReupSocket({
    topics: activeTopics,
    onStatusChange: () => {
      queryClient.invalidateQueries({ queryKey: ["videos"] });
      queryClient.invalidateQueries({ queryKey: ["counts"] });
    },
  });

  const { retry, remove, bulk, bulkPending } = useLibraryMutations({
    status,
    query,
    onBulkDone: (result) => {
      setSelected(new Set());
      setBulkNotice(result.skipped.length > 0 ? result : null);
    },
  });

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
          value={queryInput}
          onChange={(e) => setQueryInput(e.target.value)}
        />
      </header>

      <StatusChips status={status} counts={counts} onChange={setStatus} />

      {bulkNotice && <BulkSkipNotice result={bulkNotice} onDismiss={() => setBulkNotice(null)} />}

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
          onRetry={retry}
          onDelete={remove}
        />
      ))}

      <BulkActionBar
        selectedCount={selected.size}
        pending={bulkPending}
        onApprove={() => bulk([...selected], "approve")}
        onRetry={() => bulk([...selected], "retry")}
        onDelete={() => bulk([...selected], "delete")}
        onApplyPreset={(presetId) => bulk([...selected], "apply_preset", { preset_id: presetId })}
      />
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
