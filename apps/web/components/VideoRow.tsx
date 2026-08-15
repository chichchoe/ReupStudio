"use client";

import clsx from "clsx";
import { formatDuration, formatRelative, platformLabel } from "@/lib/format";
import { ghiChuVideo } from "@/lib/ghiChuVideo";
import type { Video } from "@/lib/types";
import type { VideoProgress } from "@/lib/ws";
import { StatusDots } from "./StatusDots";

interface Props {
  video: Video;
  progress?: VideoProgress;
  selected: boolean;
  /** Đang là video hiện ở khung xem bên phải. */
  dangXem: boolean;
  onToggle: (id: string) => void;
  onChon: (id: string) => void;
}

const STATUS_TONE: Record<string, string> = {
  error: "text-err",
  review: "text-warn",
  ready: "text-ok",
  posted: "text-ok",
  running: "text-run",
};

/**
 * Một dòng trong danh sách video.
 *
 * Không còn nút Xem thử / Tải / Xoá ở đây: bấm vào dòng là video hiện luôn ở
 * khung bên phải, mọi thao tác nằm cạnh thứ mà nó tác động vào. Ba nút nhân
 * với hai chục dòng chỉ làm danh sách chật mà mỗi lần vẫn chỉ bấm một cái.
 */
export function VideoRow({ video, progress, selected, dangXem, onToggle, onChon }: Props) {
  const title = video.title_vi || video.title_original || video.source_video_id;
  const note = ghiChuVideo(video, progress);

  return (
    <div
      className={clsx(
        "mb-1.5 flex items-center gap-2.5 rounded-xl border bg-panel transition-colors",
        dangXem
          ? "border-accent/60 bg-accent/[0.07]"
          : selected
            ? "border-accent/40"
            : "border-border hover:border-[#39404F]",
      )}
    >
      <button
        onClick={() => onToggle(video.id)}
        aria-label="Chọn video"
        className={clsx(
          "ml-3 flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px]",
          selected ? "border-accent bg-accent text-white" : "border-[#3C4354]",
        )}
      >
        {selected ? "✓" : ""}
      </button>

      {/* Cả phần còn lại của dòng là một nút: vùng bấm rộng, và không lồng nút
          trong nút (ô tích nằm ngoài) nên bàn phím vẫn tab qua đúng thứ tự. */}
      <button
        type="button"
        onClick={() => onChon(video.id)}
        className="flex min-w-0 flex-1 items-center gap-2.5 py-2.5 pr-3 text-left"
      >
        <span className="relative flex h-[52px] w-[38px] shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-[#2E3646] to-[#171B24] text-[13px]">
          {video.status === "ready" || video.status === "posted" ? "▶" : "🎬"}
          <span className="absolute bottom-0.5 right-0.5 rounded bg-black/75 px-1 text-[9px]">
            {formatDuration(video.duration_sec)}
          </span>
        </span>

        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium">{title}</span>
          <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
            <span>{platformLabel(video.source_platform)}</span>
            {video.source_author && (
              <>
                <span className="opacity-40">·</span>
                <span className="truncate">{video.source_author}</span>
              </>
            )}
            <span className="opacity-40">·</span>
            <span>{formatRelative(video.created_at)}</span>
          </span>
          <span className="mt-1 flex items-center gap-2">
            {/* `current_step` vắng mặt khi video chưa chạy bước nào — quy về null
                để `StatusDots` chỉ phải xử lý một dạng "không có bước nào". */}
            <StatusDots status={video.status} currentStep={video.current_step ?? null} />
            <span className={clsx("truncate text-[11px]", STATUS_TONE[video.status] ?? "text-muted")}>
              {note}
            </span>
            {progress && video.status === "running" && (
              <span className="h-[5px] w-16 shrink-0 overflow-hidden rounded-full bg-bg">
                <span
                  className="block h-full bg-run transition-all duration-500"
                  style={{ width: `${progress.percent}%` }}
                />
              </span>
            )}
          </span>
        </span>
      </button>
    </div>
  );
}
