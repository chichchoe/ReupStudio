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
      <aside className="rounded-xl border border-dashed border-border p-8 text-center text-[12.5px] text-muted">
        Bấm <span className="text-fg">▶ Xem thử</span> ở một video bên trái để xem tại đây.
      </aside>
    );
  }

  const ten = video.title_vi || video.title_original || video.source_video_id;
  const xemDuoc = video.status === "ready" || video.status === "posted";
  const note = ghiChuVideo(video, progress);

  return (
    //: Cao hết vùng còn lại rồi chia: phần hình lấy chỗ thừa, khối chữ giữ
    //: đúng chiều nó cần. Trước đây chặn cứng theo vh nên cửa sổ cao bao nhiêu
    //: thì khung phát vẫn bé như nhau.
    <aside className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-panel">
      <div className="flex min-h-0 flex-1 items-center justify-center bg-black">
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
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-[12.5px] text-muted">
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

      {/* Khối chữ giữ càng thấp càng tốt: mỗi dòng ở đây là một dòng hình bị
          mất. Tiêu đề cắt ở 2 dòng — tiêu đề Douyin dài cả đoạn, để nguyên là
          nuốt mất một phần ba khung phát. */}
      <div className="shrink-0 p-3">
        <h2
          className="text-[13px] font-medium leading-snug"
          style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}
          title={ten}
        >
          {ten}
        </h2>
        <p className="mt-1 text-[11.5px] text-muted">
          {platformLabel(video.source_platform)}
          {video.source_author && ` · ${video.source_author}`} · {formatRelative(video.created_at)}
          {" · "}
          {formatDuration(video.duration_sec)}
          {/* Ghi rõ "gốc": `width`/`height` là kích thước video TẢI VỀ, còn thứ
              đang phát là bản đã dựng lại 9:16. Không ghi thì con số ngang
              1280×720 nằm cạnh khung dọc trông như lỗi. */}
          {video.width ? ` · gốc ${video.width}×${video.height}` : ""}
        </p>

        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span
            className={clsx(
              "mr-auto text-[11.5px]",
              video.status === "error" ? "text-err" : xemDuoc ? "text-ok" : "text-muted",
            )}
          >
            {note}
          </span>
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
          <button className="btn btn-sm border-err/35 text-err" onClick={() => onDelete(video.id)}>
            Xoá
          </button>
        </div>
      </div>
    </aside>
  );
}
