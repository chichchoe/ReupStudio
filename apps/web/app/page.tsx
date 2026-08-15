"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { STATUS_LABEL, type VideoStatus } from "@/lib/types";
import { useReupSocket } from "@/lib/ws";

const CARDS: { key: VideoStatus | "all"; tone: string }[] = [
  { key: "queued", tone: "text-fg" },
  { key: "running", tone: "text-run" },
  { key: "review", tone: "text-warn" },
  { key: "ready", tone: "text-ok" },
  { key: "error", tone: "text-err" },
];

export default function DashboardPage() {
  const queryClient = useQueryClient();

  // Cần biết ID các video đang chạy để subscribe đúng topic `video:<id>` —
  // WS giờ chỉ đẩy progress cho client đã subscribe, không broadcast tràn lan.
  const { data: runningVideos } = useQuery({
    queryKey: ["videos", "running"],
    queryFn: () => api.listVideos({ status: "running", limit: 50 }),
  });
  const runningTopics = useMemo(
    () => (runningVideos?.items ?? []).map((v) => `video:${v.id}`),
    [runningVideos],
  );

  const { connected, progress, queue } = useReupSocket({
    topics: runningTopics,
    onStatusChange: () => {
      queryClient.invalidateQueries({ queryKey: ["counts"] });
      queryClient.invalidateQueries({ queryKey: ["videos", "running"] });
    },
  });

  const { data: counts } = useQuery({ queryKey: ["counts"], queryFn: api.counts });
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });

  const activeJobs = Object.entries(progress);

  // "queued"/"running" ưu tiên số liệu realtime từ topic `queue`; các trạng
  // thái khác lấy từ /videos/counts (làm tươi khi có sự kiện status).
  const cardValue = (key: VideoStatus | "all"): number => {
    if (key === "queued" && queue) return queue.pending;
    if (key === "running" && queue) return queue.active;
    return counts?.[key] ?? 0;
  };

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-xl font-semibold">Tổng quan</h1>
        <p className="text-[13px] text-muted mt-0.5">
          Chặng M1 — dán link Douyin, hệ thống tự dịch và burn phụ đề tiếng Việt
        </p>
      </header>

      <div className="grid grid-cols-5 gap-3 mb-5">
        {CARDS.map(({ key, tone }) => (
          <Link key={key} href={`/library?status=${key}`} className="card hover:border-[#39404F]">
            <div className={`text-2xl font-semibold ${tone}`}>{cardValue(key)}</div>
            <div className="text-xs text-muted mt-0.5">{STATUS_LABEL[key as VideoStatus]}</div>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-[1.35fr_1fr] gap-4">
        <section className="card">
          <h2 className="text-[13.5px] font-semibold mb-3">Đang chạy</h2>
          {activeJobs.length === 0 ? (
            <p className="text-[12.5px] text-muted py-6 text-center">
              Không có job nào đang chạy.{" "}
              <Link href="/library" className="text-accent">
                Thêm video →
              </Link>
            </p>
          ) : (
            activeJobs.map(([videoId, p]) => (
              <div key={videoId} className="flex items-center gap-2.5 py-2 border-b border-border last:border-0">
                <span className="text-[10.5px] text-muted bg-panel2 px-2 py-0.5 rounded">
                  {p.step}
                </span>
                <span className="text-[12.5px] flex-1 truncate font-mono">
                  {videoId.slice(0, 8)}
                </span>
                <span className="w-20 h-[5px] bg-bg rounded-full overflow-hidden">
                  <span
                    className="block h-full bg-run transition-all duration-500"
                    style={{ width: `${p.percent}%` }}
                  />
                </span>
                <span className="text-[11px] text-muted w-8 text-right">{p.percent}%</span>
              </div>
            ))
          )}
        </section>

        <section className="card">
          <h2 className="text-[13.5px] font-semibold mb-3">Tình trạng hệ thống</h2>
          <Row label="API" ok={health?.ok ?? false} />
          <Row label="PostgreSQL" ok={health?.db ?? false} />
          <Row label="Redis" ok={health?.redis ?? false} />
          <Row label="WebSocket" ok={connected} />

          {!health?.ok && (
            <div className="mt-3 text-[12.5px] text-[#E8D4A8] bg-warn/[0.07] border border-warn/25 rounded-lg p-3">
              API chưa chạy. Mở terminal và chạy: <code className="font-mono">make up</code> rồi{" "}
              <code className="font-mono">make api</code>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Row({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-2.5 py-2 border-b border-border last:border-0 text-[12.5px]">
      <span
        className="w-2 h-2 rounded-full"
        style={{ background: ok ? "#2FBF71" : "#E5484D" }}
      />
      {label}
      <span className="ml-auto text-muted text-[11.5px]">{ok ? "hoạt động" : "chưa kết nối"}</span>
    </div>
  );
}
