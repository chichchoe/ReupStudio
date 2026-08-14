"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { BulkActionBar } from "@/components/BulkActionBar";
import { BulkSkipNotice } from "@/components/BulkSkipNotice";
import { PendingTranslateTab } from "@/components/PendingTranslateTab";
import { StatusChips } from "@/components/StatusChips";
import { VideoRow } from "@/components/VideoRow";
import { api } from "@/lib/api";
import type { BulkResult } from "@/lib/types";
import { useLibraryMutations } from "@/lib/useLibraryMutations";
import { useReupSocket } from "@/lib/ws";

/** Chờ 300ms sau lần gõ cuối mới bắn request tìm kiếm — tránh gọi API mỗi phím. */
const SEARCH_DEBOUNCE_MS = 300;

type Tab = "all" | "pending";

const TABS: { value: Tab; label: string }[] = [
  { value: "all", label: "Toàn bộ video" },
  { value: "pending", label: "Chờ dịch" },
];

function LibraryInner() {
  const params = useSearchParams();
  const router = useRouter();
  const tab: Tab = params.get("tab") === "pending" ? "pending" : "all";
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

  // Đồng bộ tab vào query string (`?tab=pending`) để tải lại trang vẫn đúng tab,
  // giống cách trang Nguồn làm.
  const setTab = (next: Tab) => {
    const qs = new URLSearchParams(params.toString());
    if (next === "all") qs.delete("tab");
    else qs.set("tab", next);
    router.replace(`?${qs.toString()}`, { scroll: false });
  };

  // Vẫn chạy cả khi đang ở tab "Chờ dịch": danh sách này nuôi các topic
  // WebSocket bên dưới, nhờ đó video vừa nhận dạng xong sẽ tự rơi vào danh sách
  // chờ dịch mà không cần polling.
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
            {tab === "pending"
              ? "Video đã nhận dạng xong lời thoại — chọn model AI rồi bấm Dịch."
              : data
                ? `${data.total} video`
                : "đang tải…"}
          </p>
        </div>
        {/* Ô tìm kiếm chỉ lọc danh sách đầy đủ, tab chờ dịch không dùng đến. */}
        {tab === "all" && (
          <input
            className="input w-72"
            placeholder="🔍 Tìm theo tiêu đề hoặc tác giả…"
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
          />
        )}
      </header>

      <div className="flex gap-2 mb-3">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={clsx("chip", tab === t.value && "chip-active")}
          >
            {t.label}
            {t.value === "pending" && counts?.review != null && ` · ${counts.review}`}
          </button>
        ))}
      </div>

      {tab === "pending" ? (
        <PendingTranslateTab />
      ) : (
        <>
          <StatusChips status={status} counts={counts} onChange={setStatus} />

          {bulkNotice && (
            <BulkSkipNotice result={bulkNotice} onDismiss={() => setBulkNotice(null)} />
          )}

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
            onApplyPreset={(presetId) =>
              bulk([...selected], "apply_preset", { preset_id: presetId })
            }
          />
        </>
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
