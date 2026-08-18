"use client";

import clsx from "clsx";
import { api } from "@/lib/api";
import { formatDuration, formatRelative, platformLabel } from "@/lib/format";
import { ghiChuVideo } from "@/lib/ghiChuVideo";
import { TARGET_PLATFORM_LABEL, type TargetPlatform, type Video } from "@/lib/types";
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
  //: `flags.da_dang` là {nền tảng: ngày đánh dấu} — sổ ghi tay cho tới khi
  //: chặng đăng tự động (M5) có thật.
  const daDangMap = (video.flags?.da_dang ?? {}) as Record<string, string>;
  const daDang = Object.keys(daDangMap);
  const note = ghiChuVideo(video, progress);
  //: Chỉ xem được khi đã có file ra. `posted` cũng có file — video đã đăng vẫn
  //: cần xem lại được.
  const xemDuoc = video.status === "ready" || video.status === "posted";
  //: Ba trạng thái, ba chữ khác nhau: chưa mở · đang chạy · mở rồi mà đang
  //: dừng. "Xem tiếp" quan trọng nhất — nó nói cho biết bấm vào sẽ chạy tiếp
  //: chứ không phải xem lại từ đầu.
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

      {/* Ô ảnh đại diện chỉ để chỗ và ghi thời lượng — không có icon, không bấm
          được. Chỗ phát là nút "▶ Xem thử" bên phải; hai nút cùng làm một việc
          trên một dòng chỉ khiến phải đoán xem chúng khác nhau chỗ nào. */}
      <div className="relative flex h-[52px] w-[38px] shrink-0 items-end justify-end rounded-lg bg-gradient-to-br from-[#2E3646] to-[#171B24]">
        <span className="m-0.5 rounded bg-black/75 px-1 text-[9px]">
          {formatDuration(video.duration_sec)}
        </span>
      </div>

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

        {/* Nền tảng đã đăng — đánh dấu tay, vì chặng đăng tự động (M5) chưa có.
            Hiện ngay trên dòng để trả lời được "cái này còn thiếu nơi nào"
            mà không phải mở từng video ra xem. */}
        {daDang.length > 0 && (
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {daDang.map((ma) => (
              <span
                key={ma}
                className="rounded bg-ok/15 px-1.5 py-px text-[10.5px] text-ok"
                title={`Đánh dấu đã đăng ngày ${daDangMap[ma]}`}
              >
                {TARGET_PLATFORM_LABEL[ma as TargetPlatform] ?? ma}
              </span>
            ))}
          </div>
        )}
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
