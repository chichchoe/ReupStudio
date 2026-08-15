import { STATUS_LABEL, STEP_LABEL, type Video } from "@/lib/types";
import type { VideoProgress } from "@/lib/ws";

/** Nhãn tiếng Việt cho lý do trùng — khớp `reason` ghi ở `tasks/video.py:_mark_duplicate`. */
const DUPLICATE_REASON_LABEL: Record<string, string> = {
  md5: "md5",
  phash: "pHash",
};

/**
 * Một dòng nói rõ video đang ở đâu: đang chạy bước nào, lỗi gì, trùng với ai.
 *
 * Để ở `lib/` vì cả dòng trong danh sách lẫn khung xem bên phải đều cần —
 * hai chỗ mô tả cùng một video mà lệch chữ thì người dùng tưởng là hai việc
 * khác nhau.
 */
export function ghiChuVideo(video: Video, progress?: VideoProgress): string {
  if (video.status === "error") return video.error_message ?? "Lỗi không rõ";
  if (video.status === "running") {
    const step = progress?.step ?? video.current_step;
    const percent = progress?.percent;
    const label = step ? STEP_LABEL[step] : "Đang xử lý";
    return percent != null ? `${label}… ${percent}%` : `${label}…`;
  }
  if (video.status === "ready") return "Đã render xong";
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
