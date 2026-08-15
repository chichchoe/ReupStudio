"use client";

import clsx from "clsx";
import { api } from "@/lib/api";
import { formatDuration, formatRelative, platformLabel } from "@/lib/format";
import { ghiChuVideo } from "@/lib/ghiChuVideo";
import type { Video } from "@/lib/types";
import type { VideoProgress } from "@/lib/ws";

/**
 * Khung xem cố định bên phải danh sách.
 *
 * Vì sao không dùng hộp thoại: duyệt video là việc lặp — xem một cái, thấy
 * phụ đề lệch, sang cái tiếp theo. Hộp thoại bắt đóng rồi mở lại từng lần và
 * che mất chỗ mình đang đứng trong danh sách. Khung cố định cho bấm dòng nào
 * là xem ngay dòng đó.
 *
 * Endpoint `/videos/{id}/file` trả `FileResponse` nên hỗ trợ range request —
 * thẻ `<video>` tua được mà không phải tải hết vài trăm MB.
 */
interface Props {
  video: Video | null;
  progress?: VideoProgress;
  onRetry: (id: string) => void;
  onDelete: (id: string) => void;
}

export function KhungXem({ video, progress, onRetry, onDelete }: Props) {
  if (!video) {
    return (
      <aside className="sticky top-0 rounded-xl border border-dashed border-border p-6 text-center text-[12.5px] text-muted">
        Bấm một video bên trái để xem tại đây.
      </aside>
    );
  }

  const ten = video.title_vi || video.title_original || video.source_video_id;
  const xemDuoc = video.status === "ready" || video.status === "posted";
  const note = ghiChuVideo(video, progress);

  return (
    <aside className="sticky top-0 overflow-hidden rounded-xl border border-border bg-panel">
      <div className="flex items-center justify-center bg-black">
        {xemDuoc ? (
          /* eslint-disable-next-line jsx-a11y/media-has-caption --
             Phụ đề đã BURN vào hình, không có track riêng để gắn. */
          <video
            //: `key` bắt React dựng thẻ mới khi đổi video. Nếu chỉ đổi `src`,
            //: trình duyệt giữ nguyên vị trí đang tua của video trước.
            key={video.id}
            src={api.fileUrl(video.id)}
            controls
            autoPlay
            //: Chặn theo chiều cao cửa sổ để cả thẻ — video, tên, nút Tải/Xoá —
            //: nằm gọn trong một màn. Khung dính mà cao hơn màn thì dính vô ích.
            className="max-h-[46vh] max-w-full"
          />
        ) : (
          <div className="flex h-52 w-full flex-col items-center justify-center gap-2 text-[12.5px] text-muted">
            <span className="text-2xl opacity-50">🎬</span>
            {video.status === "running" ? "Đang xử lý — xong là xem được ngay" : "Chưa có bản dựng"}
            {progress && video.status === "running" && (
              <span className="h-[5px] w-40 overflow-hidden rounded-full bg-bg">
                <span
                  className="block h-full bg-run transition-all duration-500"
                  style={{ width: `${progress.percent}%` }}
                />
              </span>
            )}
          </div>
        )}
      </div>

      <div className="p-3.5">
        <h2 className="text-[13.5px] font-medium leading-snug">{ten}</h2>
        <p className="mt-1 text-[11.5px] text-muted">
          {platformLabel(video.source_platform)}
          {video.source_author && ` · ${video.source_author}`} · {formatRelative(video.created_at)}
        </p>
        <p className="mt-0.5 text-[11.5px] text-muted">
          {formatDuration(video.duration_sec)}
          {/* Ghi rõ "gốc": `width`/`height` là kích thước video TẢI VỀ, còn thứ
              đang phát là bản đã dựng lại 9:16. Không ghi thì con số ngang
              1280×720 nằm cạnh khung dọc trông như lỗi. */}
          {video.width ? ` · gốc ${video.width}×${video.height}` : ""}
        </p>

        <p
          className={clsx(
            "mt-2 text-[12px]",
            video.status === "error" ? "text-err" : xemDuoc ? "text-ok" : "text-muted",
          )}
        >
          {note}
        </p>

        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-border pt-3">
          {xemDuoc && (
            <a className="btn btn-sm" href={api.fileUrl(video.id)} download>
              ⬇ Tải file
            </a>
          )}
          {video.status === "error" && (
            <button className="btn btn-sm" onClick={() => onRetry(video.id)}>
              Thử lại
            </button>
          )}
          <button
            className="btn btn-sm ml-auto border-err/35 text-err"
            onClick={() => onDelete(video.id)}
          >
            Xoá
          </button>
        </div>
      </div>
    </aside>
  );
}
