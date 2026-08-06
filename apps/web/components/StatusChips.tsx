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
  return (
    <div className="flex gap-2 flex-wrap mb-3">
      {FILTERS.map((key) => (
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
