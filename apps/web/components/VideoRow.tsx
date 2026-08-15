"use client";

import clsx from "clsx";
import { api } from "@/lib/api";
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
  /** Video này đang chạy trong khung xem — nút đổi thành ⏸. */
  dangPhat: boolean;
  onToggle: (id: string) => void;
  /**
   * Bấm ▶ — đưa video sang khung xem bên phải, hoặc dừng/chạy tiếp nếu nó đã ở
   * đó. CHỈ nút này mở xem; bấm chỗ khác trên dòng không đổi gì, để lúc đang
   * xem dở mà lỡ tay chạm danh sách thì video không nhảy sang cái khác.
   */
  onXemThu: (id: string) => void;
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

/** Một dòng trong danh sách video. */
export function VideoRow({
  video,
  progress,
  selected,
  dangXem,
  dangPhat,
  onToggle,
  onXemThu,
  onRetry,
  onDelete,
}: Props) {
  const title = video.title_vi || video.title_original || video.source_video_id;
  const note = ghiChuVideo(video, progress);
  //: Chỉ xem được khi đã có file ra. `posted` cũng có file — video đã đăng vẫn
  //: cần xem lại được.
  const xemDuoc = video.status === "ready" || video.status === "posted";
  //: Ba trạng thái, ba chữ khác nhau: chưa mở · đang chạy · mở rồi mà đang
  //: dừng. "Xem tiếp" quan trọng nhất — nó nói cho biết bấm vào sẽ chạy tiếp
  //: chứ không phải xem lại từ đầu.
  const dangChay = dangXem && dangPhat;
  const nhanXem = !dangXem ? "▶ Xem thử" : dangPhat ? "⏸ Dừng" : "▶ Xem tiếp";

  return (
    <div
      className={clsx(
        "mb-1.5 flex items-center gap-2.5 rounded-xl border bg-panel p-2.5 transition-colors",
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
          "flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px]",
          selected ? "border-accent bg-accent text-white" : "border-[#3C4354]",
        )}
      >
        {selected ? "✓" : ""}
      </button>

      {/* Bấm vào ảnh đại diện để xem — chưa render xong thì không có gì để xem,
          và một nút bấm được nhưng không làm gì còn tệ hơn không có nút. */}
      <button
        type="button"
        disabled={!xemDuoc}
        onClick={() => onXemThu(video.id)}
        aria-label={xemDuoc ? nhanXem : "Chưa render xong"}
        className={clsx(
          "group relative flex h-[52px] w-[38px] shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-[#2E3646] to-[#171B24] text-[13px]",
          xemDuoc && "hover:brightness-125",
        )}
      >
        {xemDuoc ? (
          <span className="text-white/90 group-hover:text-white">{dangChay ? "⏸" : "▶"}</span>
        ) : (
          "🎬"
        )}
        <span className="absolute bottom-0.5 right-0.5 rounded bg-black/75 px-1 text-[9px]">
          {formatDuration(video.duration_sec)}
        </span>
      </button>

      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium">{title}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
          <span>{platformLabel(video.source_platform)}</span>
          {video.source_author && (
            <>
              <span className="opacity-40">·</span>
              <span className="truncate">{video.source_author}</span>
            </>
          )}
          <span className="opacity-40">·</span>
          <span>{formatRelative(video.created_at)}</span>
        </div>
        <div className="mt-1 flex items-center gap-2">
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
        </div>
      </div>

      <div className="flex shrink-0 gap-1.5">
        {xemDuoc && (
          <>
            <button
              className={clsx("btn btn-sm", dangXem && "btn-primary")}
              onClick={() => onXemThu(video.id)}
            >
              {nhanXem}
            </button>
            <a className="btn btn-sm" href={api.fileUrl(video.id)} download>
              ⬇ Tải
            </a>
          </>
        )}
        {video.status === "error" && (
          <button className="btn btn-sm" onClick={() => onRetry(video.id)}>
            Thử lại
          </button>
        )}
        <button className="btn btn-sm border-err/35 text-err" onClick={() => onDelete(video.id)}>
          Xoá
        </button>
      </div>
    </div>
  );
}
