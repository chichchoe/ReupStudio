"use client";

import clsx from "clsx";
import { STATUS_LABEL, type VideoStatus } from "@/lib/types";

/** Thứ tự hiển thị chip lọc — lấy đủ toàn bộ `VideoStatus`, không gõ chuỗi rời rạc. */
const FILTERS: (VideoStatus | "all")[] = [
  "all",
  "queued",
  "running",
  "review",
  "ready",
  "scheduled",
  "posted",
  "error",
  "skipped",
];

interface Props {
  status: string;
  counts?: Record<string, number>;
  onChange: (status: string) => void;
}

/** Dải chip lọc theo trạng thái video ở trang Thư viện. */
export function StatusChips({ status, counts, onChange }: Props) {
  // Ẩn trạng thái đang rỗng: bấm vào chỉ ra danh sách trắng. Lúc mới dùng thì
  // 7/9 chip là số 0, chúng lấn át hai chip thật sự bấm được.
  // Vẫn giữ "Tất cả" và chip đang chọn — nếu không, lọc xong rồi xoá hết video
  // là chip đang chọn biến mất và không còn đường quay lại.
  const hien = FILTERS.filter(
    (key) => key === "all" || key === status || (counts?.[key] ?? 0) > 0,
  );

  //: Chỉ còn mỗi "Tất cả" thì dải lọc không lọc được gì — bỏ hẳn cho đỡ rác.
  if (hien.length < 2) return null;

  return (
    <div className="flex gap-2 flex-wrap mb-3">
      {hien.map((key) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={clsx("chip", status === key && "chip-active")}
        >
          {key === "all" ? "Tất cả" : STATUS_LABEL[key as VideoStatus]}
          {counts?.[key] != null && ` · ${counts[key]}`}
        </button>
      ))}
    </div>
  );
}
