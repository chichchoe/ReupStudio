"use client";

/**
 * Editor — tab "Chuẩn hoá video ngắn" (M4-FE-01, task cuối chặng M4).
 *
 * Bảng giới hạn nền tảng là cấu hình toàn cục (không gắn với video nào), nên
 * luôn hiện. Render + danh sách bản đã render gắn với MỘT video cụ thể, cần
 * chọn video trước. Chọn qua query string `?video=<id>` để giữ khi tải lại
 * trang, giống cách trang Thư viện giữ `status`/`q`.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { PlatformLimitsTable } from "@/components/PlatformLimitsTable";
import { RenderPanel } from "@/components/RenderPanel";
import { VariantsList } from "@/components/VariantsList";
import { api } from "@/lib/api";
import { STATUS_LABEL } from "@/lib/types";
import { useReupSocket } from "@/lib/ws";

function EditorInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [videoId, setVideoId] = useState(params.get("video") ?? "");
  const queryClient = useQueryClient();

  const { data: videosPage } = useQuery({
    queryKey: ["videos", "editor-picker"],
    queryFn: () => api.listVideos({ limit: 100 }),
  });
  const videos = useMemo(() => videosPage?.items ?? [], [videosPage]);

  // Chỉ theo dõi tiến trình của video đang chọn — WebSocket sẵn có, KHÔNG polling.
  const { progress } = useReupSocket({
    topics: videoId ? [`video:${videoId}`] : [],
    onStatusChange: () => {
      queryClient.invalidateQueries({ queryKey: ["variants", videoId] });
    },
  });

  const selectVideo = (id: string) => {
    setVideoId(id);
    const next = new URLSearchParams(params.toString());
    if (id) next.set("video", id);
    else next.delete("video");
    router.replace(`?${next.toString()}`, { scroll: false });
  };

  return (
    <div>
      <header className="mb-4">
        <h1 className="text-xl font-semibold">Editor</h1>
        <p className="text-[13px] text-muted mt-0.5">
          Chuẩn hoá cho video ngắn — một bản render cho mỗi nền tảng đích.
        </p>
      </header>

      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <span className="text-[12.5px] text-muted">Video:</span>
        <select
          className="input py-1.5 max-w-md"
          value={videoId}
          onChange={(e) => selectVideo(e.target.value)}
        >
          <option value="">— Chọn video —</option>
          {videos.map((v) => (
            <option key={v.id} value={v.id}>
              {v.title_vi || v.title_original || v.source_video_id} · {STATUS_LABEL[v.status]}
            </option>
          ))}
        </select>
      </div>

      <div className="flex gap-2 mb-4">
        <span className="inline-flex items-center bg-accent/15 border border-accent/40 text-fg rounded-full px-3 py-1 text-[12.5px] font-medium">
          Chuẩn hoá video ngắn
        </span>
      </div>

      <div className="flex flex-col gap-4">
        <PlatformLimitsTable />

        {videoId ? (
          <>
            <RenderPanel videoId={videoId} progress={progress[videoId]} />
            <VariantsList videoId={videoId} />
          </>
        ) : (
          <div className="card text-[12.5px] text-muted">
            Chọn một video ở trên để render và xem danh sách bản đã chuẩn hoá.
          </div>
        )}
      </div>
    </div>
  );
}

export default function EditorPage() {
  return (
    <Suspense fallback={<p className="text-[13px] text-muted">Đang tải…</p>}>
      <EditorInner />
    </Suspense>
  );
}
