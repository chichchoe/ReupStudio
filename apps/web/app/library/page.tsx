"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { BulkActionBar } from "@/components/BulkActionBar";
import { ChannelsTab } from "@/components/ChannelsTab";
import { BulkSkipNotice } from "@/components/BulkSkipNotice";
import { DuyetBanDichTab } from "@/components/DuyetBanDichTab";
import { KhungXem } from "@/components/KhungXem";
import { PasteLinksForm } from "@/components/PasteLinksForm";
import { PendingTranslateTab } from "@/components/PendingTranslateTab";
import { VideoRow } from "@/components/VideoRow";
import { api } from "@/lib/api";
import { STATUS_LABEL, type BulkResult, type VideoStatus } from "@/lib/types";
import { useLibraryMutations } from "@/lib/useLibraryMutations";
import { useReupSocket } from "@/lib/ws";

/** Chờ 300ms sau lần gõ cuối mới bắn request tìm kiếm — tránh gọi API mỗi phím. */
const SEARCH_DEBOUNCE_MS = 300;

type Tab = "all" | "pending" | "duyet" | "kenh";

const TABS: { value: Tab; label: string }[] = [
  { value: "all", label: "Toàn bộ video" },
  { value: "pending", label: "Chờ dịch" },
  //: Chỗ dừng thứ HAI của pipeline: đọc lại bản dịch và nghe thử giọng trước
  //: khi chạy bước xoá chữ cứng — bước nặng nhất, không nên chạy rồi mới biết
  //: bản dịch hỏng.
  { value: "duyet", label: "Chờ duyệt" },
  //: Trang "Nguồn Trung Quốc" cũ có tab này. Gộp vào đây để chỗ thêm video và
  //: chỗ xem kết quả nằm cùng một nơi.
  { value: "kenh", label: "Kênh theo dõi" },
];

function LibraryInner() {
  const params = useSearchParams();
  const router = useRouter();
  const tab: Tab = ((): Tab => {
    const t = params.get("tab");
    return t === "pending" || t === "duyet" || t === "kenh" ? t : "all";
  })();
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

  //: Chỉ giữ ID chứ không giữ cả object: object lấy ra từ danh sách mỗi lần
  //: render, nên khung xem tự cập nhật khi video chạy xong mà không phải đồng
  //: bộ tay.
  const [idDangXem, setIdDangXem] = useState<string | null>(null);
  const dangXem = videos.find((v) => v.id === idDangXem) ?? null;

  // Tự chọn video đầu tiên: mở trang ra là xem được luôn. Cũng chạy khi video
  // đang xem bị xoá hoặc rơi khỏi bộ lọc — nếu không thì khung bên phải trống
  // mà danh sách vẫn đầy, trông như hỏng.
  useEffect(() => {
    if (videos.length > 0 && !dangXem) setIdDangXem(videos[0].id);
  }, [videos, dangXem]);

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
          <h1 className="text-xl font-semibold">Video</h1>
          <p className="mt-0.5 text-[13px] text-muted">
            {tab === "pending"
              ? "Đã nhận dạng xong lời thoại — chọn AI, giọng đọc rồi bấm Dịch."
              : tab === "duyet"
                ? "Đọc lại bản dịch và nghe thử giọng trước khi ghép vào video."
                : tab === "kenh"
                  ? "Kênh nguồn được quét định kỳ để lấy video mới."
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

      {/*
        Ô dán link nằm NGAY ĐẦU trang này thay vì ở một trang riêng: dán xong
        là muốn xem kết quả ngay, tách làm hai trang chỉ thêm một bước đi lại.
        Gấp lại được vì phần lớn thời gian người dùng vào đây để XEM, không
        phải để thêm.
      */}
      <details className="card mb-3" open={videos.length === 0} hidden={tab === "kenh"}>
        <summary className="cursor-pointer list-none text-[13.5px] font-medium marker:content-none">
          <span className="text-accent">＋</span> Thêm video — dán link
          <span className="ml-2 text-[11.5px] font-normal text-muted">
            Douyin, Bilibili, Kuaishou, Xiaohongshu, Weibo, YouTube, TikTok… hầu hết trang video
          </span>
        </summary>
        <div className="mt-3 border-t border-border pt-3">
          <PasteLinksForm />
        </div>
      </details>

      {/* Tab dùng dạng khối liền, KHÁC hẳn dải chip lọc trạng thái ngay bên
          dưới. Trước đây cả hai cùng là chip bo tròn nên nhìn như hai hàng lọc
          ngang hàng, trong khi thực ra một hàng đổi cả trang, một hàng chỉ lọc. */}
      <div className="mb-3 inline-flex rounded-lg border border-border bg-panel p-0.5">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={clsx(
              "rounded-[7px] px-3.5 py-1.5 text-[13px] transition-colors",
              tab === t.value
                ? "bg-accent font-medium text-white"
                : "text-muted hover:bg-panel2 hover:text-fg",
            )}
          >
            {t.label}
            {t.value === "pending" && !!counts?.review && ` · ${counts.review}`}
          </button>
        ))}
      </div>

      {tab === "kenh" ? (
        <ChannelsTab />
      ) : tab === "duyet" ? (
        <DuyetBanDichTab />
      ) : tab === "pending" ? (
        <PendingTranslateTab />
      ) : (
        <>
          {/* Dải chip lọc trạng thái đã bỏ: lúc mới dùng thì gần hết là số 0,
              và cột phải giờ mới là chỗ mắt nhìn. Bộ lọc từ thẻ ở trang Tổng
              quan (`?status=ready`) vẫn chạy — hiện thành một thẻ gỡ được, chứ
              không im lặng lọc mà không nói gì. */}
          {status !== "all" && (
            <button
              className="chip chip-active mb-3"
              onClick={() => setStatus("all")}
              title="Bỏ lọc"
            >
              Đang lọc: {STATUS_LABEL[status as VideoStatus] ?? status} ✕
            </button>
          )}

          {bulkNotice && (
            <BulkSkipNotice result={bulkNotice} onDismiss={() => setBulkNotice(null)} />
          )}

          {isLoading && <p className="text-[13px] text-muted py-8 text-center">Đang tải…</p>}

          {!isLoading && videos.length === 0 && (
            <div className="text-center py-16 text-muted text-[13px]">
              Chưa có video nào khớp bộ lọc.
            </div>
          )}

          {/* Danh sách bên trái, khung xem bên phải. Cột phải rộng cố định vì
              nó chứa video dọc 9:16 — để co giãn thì mỗi lần cửa sổ đổi bề
              rộng, khung phát lại nhảy kích thước. */}
          {videos.length > 0 && (
            <div className="grid grid-cols-[minmax(0,1fr)_380px] items-start gap-4">
              <div>
                {videos.map((video) => (
                  <VideoRow
                    key={video.id}
                    video={video}
                    progress={progress[video.id]}
                    selected={selected.has(video.id)}
                    dangXem={video.id === idDangXem}
                    onToggle={toggle}
                    onChon={setIdDangXem}
                  />
                ))}
              </div>

              <KhungXem
                video={dangXem}
                progress={dangXem ? progress[dangXem.id] : undefined}
                onRetry={retry}
                onDelete={remove}
              />
            </div>
          )}

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
