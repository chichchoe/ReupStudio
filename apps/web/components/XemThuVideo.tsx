"use client";

import { useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { Video } from "@/lib/types";

/**
 * Xem thử bản render ngay trong trang.
 *
 * Vì sao cần: trước đây muốn kiểm một bản dựng phải bấm "Tải file", đợi tải
 * xong, mở bằng trình xem của máy. Với video một tiếng thì đó là vài trăm MB
 * chỉ để liếc xem phụ đề có đúng chỗ không.
 *
 * Endpoint `/videos/{id}/file` trả `FileResponse` nên hỗ trợ range request —
 * thẻ `<video>` tua được mà không phải tải hết.
 */
interface Props {
  video: Video;
  onDong: () => void;
}

export function XemThuVideo({ video, onDong }: Props) {
  const hopRef = useRef<HTMLDivElement>(null);

  // Esc để đóng: người dùng đang xem video thì tay không ở chuột.
  useEffect(() => {
    const nghe = (e: KeyboardEvent) => {
      if (e.key === "Escape") onDong();
    };
    window.addEventListener("keydown", nghe);
    return () => window.removeEventListener("keydown", nghe);
  }, [onDong]);

  const ten = video.title_vi || video.title_original || video.source_video_id;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-6"
      onClick={(e) => {
        // Bấm ra ngoài khung để đóng — nhưng bấm TRÚNG khung thì không, nếu
        // không thì mỗi lần chạm thanh tua là video tắt.
        if (!hopRef.current?.contains(e.target as Node)) onDong();
      }}
    >
      <div
        ref={hopRef}
        className="flex max-h-full w-fit min-w-[26rem] max-w-3xl flex-col overflow-hidden rounded-xl border border-border bg-panel"
      >
        <div className="flex items-center gap-3 border-b border-border px-4 py-2.5">
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13.5px] font-medium">{ten}</div>
            {/* Ghi rõ "gốc": `width`/`height` là kích thước video TẢI VỀ, còn
                thứ đang phát là bản đã dựng lại 9:16. Không ghi thì con số
                ngang 1280×720 nằm cạnh khung dọc trông như lỗi. */}
            <div className="text-[11.5px] text-muted">
              {formatDuration(video.duration_sec)}
              {video.width ? ` · gốc ${video.width}×${video.height}` : ""}
            </div>
          </div>
          <a className="btn btn-sm" href={api.fileUrl(video.id)} download>
            ⬇ Tải file
          </a>
          <button className="btn btn-sm" onClick={onDong} aria-label="Đóng xem thử">
            ✕
          </button>
        </div>

        <div className="flex min-h-0 flex-1 items-center justify-center bg-black p-2">
          {/* eslint-disable-next-line jsx-a11y/media-has-caption --
              Phụ đề đã BURN vào hình, không có track riêng để gắn. */}
          {/* Để chính thẻ video quyết chiều: khung ra sau khi dựng lại 9:16
              không suy được từ `width`/`height` của bản gốc. */}
          <video
            src={api.fileUrl(video.id)}
            controls
            autoPlay
            className="max-h-[72vh] max-w-full"
          />
        </div>
      </div>
    </div>
  );
}
