"use client";

import clsx from "clsx";
import { api } from "@/lib/api";
import { formatDuration, formatRelative, platformLabel } from "@/lib/format";
import { STATUS_LABEL, STEP_LABEL, type Video } from "@/lib/types";
import type { VideoProgress } from "@/lib/ws";
import { StatusDots } from "./StatusDots";

interface Props {
  video: Video;
  progress?: VideoProgress;
  selected: boolean;
  onToggle: (id: string) => void;
  onRetry: (id: string) => void;
  onDelete: (id: string) => void;
}

const STATUS_TONE: Record<string, string> = {
  error: "text-err",
  review: "text-warn",
  ready: "text-ok",
  posted: "text-ok",
  running: "text-run",
};

export function VideoRow({ video, progress, selected, onToggle, onRetry, onDelete }: Props) {
  const title = video.title_vi || video.title_original || video.source_video_id;
  const note = buildNote(video, progress);

  return (
    <div
      className={clsx(
        "flex items-center gap-3 bg-panel border rounded-xl p-3 mb-2 transition-colors",
        selected ? "border-accent/55 bg-accent/5" : "border-border hover:border-[#39404F]",
      )}
    >
      <button
        onClick={() => onToggle(video.id)}
        aria-label="Chọn video"
        className={clsx(
          "w-4 h-4 shrink-0 rounded border flex items-center justify-center text-[10px]",
          selected ? "bg-accent border-accent text-white" : "border-[#3C4354]",
        )}
      >
        {selected ? "✓" : ""}
      </button>

      <div className="w-11 h-[60px] shrink-0 rounded-lg bg-gradient-to-br from-[#2E3646] to-[#171B24] relative flex items-center justify-center text-xl">
        🎬
        <span className="absolute bottom-0.5 right-0.5 bg-black/75 text-[9.5px] px-1 rounded">
          {formatDuration(video.duration_sec)}
        </span>
      </div>

      <div className="flex-1 min-w-0">
        <div className="text-[13.5px] font-medium truncate">{title}</div>
        <div className="text-[11.5px] text-muted flex gap-2 items-center flex-wrap">
          <span>{platformLabel(video.source_platform)}</span>
          {video.source_author && (
            <>
              <span className="opacity-40">·</span>
              <span>{video.source_author}</span>
            </>
          )}
          <span className="opacity-40">·</span>
          <span>{formatRelative(video.created_at)}</span>
          {video.width && (
            <>
              <span className="opacity-40">·</span>
              <span>
                {video.width}×{video.height}
              </span>
            </>
          )}
        </div>

        <div className="flex items-center gap-2 mt-1.5">
          {/* `current_step` vắng mặt khi video chưa chạy bước nào — quy về null
              để `StatusDots` chỉ phải xử lý một dạng "không có bước nào". */}
          <StatusDots status={video.status} currentStep={video.current_step ?? null} />
          <span className={clsx("text-[11px]", STATUS_TONE[video.status] ?? "text-muted")}>
            {note}
          </span>
          {progress && video.status === "running" && (
            <span className="w-20 h-[5px] bg-bg rounded-full overflow-hidden">
              <span
                className="block h-full bg-run transition-all duration-500"
                style={{ width: `${progress.percent}%` }}
              />
            </span>
          )}
        </div>
      </div>

      <div className="flex gap-1.5 shrink-0">
        {video.status === "ready" && (
          <a className="btn btn-sm" href={api.fileUrl(video.id)} download>
            ⬇ Tải file
          </a>
        )}
        {video.status === "error" && (
          <button className="btn btn-sm" onClick={() => onRetry(video.id)}>
            Thử lại
          </button>
        )}
        <button className="btn btn-sm text-err border-err/35" onClick={() => onDelete(video.id)}>
          Xoá
        </button>
      </div>
    </div>
  );
}

/** Nhãn tiếng Việt cho lý do trùng — khớp `reason` ghi ở `tasks/video.py:_mark_duplicate`. */
const DUPLICATE_REASON_LABEL: Record<string, string> = {
  md5: "md5",
  phash: "pHash",
};

function buildNote(video: Video, progress?: VideoProgress): string {
  if (video.status === "error") return video.error_message ?? "Lỗi không rõ";
  if (video.status === "running") {
    const step = progress?.step ?? video.current_step;
    const percent = progress?.percent;
    const label = step ? STEP_LABEL[step] : "Đang xử lý";
    return percent != null ? `${label}… ${percent}%` : `${label}…`;
  }
  if (video.status === "ready") return "Đã render xong — tải về xem thử";
  if (video.status === "skipped") {
    const duplicateOf = video.flags?.duplicate_of;
    if (typeof duplicateOf === "string" && duplicateOf) {
      const reasonRaw = video.flags?.duplicate_reason;
      const reason =
        typeof reasonRaw === "string" ? DUPLICATE_REASON_LABEL[reasonRaw] ?? reasonRaw : null;
      const ma = duplicateOf.slice(0, 8);
      return reason
        ? `Trùng với video đã có (${reason}) — #${ma}`
        : `Trùng với video đã có — #${ma}`;
    }
  }
  return STATUS_LABEL[video.status] ?? video.status;
}
