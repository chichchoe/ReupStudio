"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { api } from "@/lib/api";
import { formatCount, formatDuration, platformLabel } from "@/lib/format";
import type { Video } from "@/lib/types";

/** Bản phụ đề gốc tiếng Trung — số cue của bản này chính là số câu thoại của video. */
const SOURCE_LANG = "zh";

interface Props {
  video: Video;
  /** Danh sách model dịch từ `GET /llm/models`; tab cha tải một lần rồi truyền xuống. */
  models: string[];
  /** Model cấu hình sẵn (`LLM_MODEL`), chọn sẵn trong ô chọn. Rỗng khi khoá
   * hiện tại không dùng được nó — khi đó rơi về model đầu danh sách. */
  defaultModel: string;
  selected: boolean;
  /** true khi yêu cầu dịch của chính video này đang bay — chặn bấm hai lần. */
  pending: boolean;
  onToggle: (id: string) => void;
  onTranslate: (id: string, model: string) => void;
}

/**
 * Một dòng video chờ dịch. Điểm khác VideoRow: hiện SỐ CÂU THOẠI và cho chọn
 * model ngay tại dòng — người dùng cần con số đó để quyết định model, không thể
 * bắt họ mở từng video ra đếm.
 */
export function PendingVideoRow({
  video,
  models,
  defaultModel,
  selected,
  pending,
  onToggle,
  onTranslate,
}: Props) {
  // Đếm cue từ endpoint phụ đề sẵn có. Mỗi dòng tự hỏi phần của mình, TanStack
  // Query gộp theo khoá nên chuyển tab qua lại không gọi lại API.
  const { data: subtitles, isLoading: loadingCues } = useQuery({
    queryKey: ["subtitles", video.id, SOURCE_LANG],
    queryFn: () => api.subtitles(video.id, SOURCE_LANG),
  });
  const cueCount = subtitles?.find((s) => s.lang === SOURCE_LANG)?.cues.length ?? null;

  // Chưa chọn gì thì lấy model MẶC ĐỊNH backend trả về, không phải model đầu
  // danh sách. Ảnh chụp giao diện thật (2026-08-15) cho thấy hậu quả của việc
  // lấy option đầu: ô chọn hiện `gemini-2.5-flash` (20 lượt/NGÀY) trong khi
  // cấu hình để `gemini-3.5-flash-lite` (500 lượt/ngày) — ai bấm nhanh dính
  // đúng model tệ nhất về hạn mức mà không biết.
  //
  // Tính khi render thay vì đồng bộ bằng useEffect, vì danh sách model thường
  // về SAU khi dòng đã hiện.
  const [chosen, setChosen] = useState("");
  const model = chosen || defaultModel || models[0] || "";

  const title = video.title_vi || video.title_original || video.source_video_id;

  return (
    <div
      className={clsx(
        "mb-2 flex items-center gap-3 rounded-xl border bg-panel p-3 transition-colors",
        selected ? "border-accent/55 bg-accent/5" : "border-border hover:border-[#39404F]",
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

      <div className="relative flex h-[60px] w-11 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-[#2E3646] to-[#171B24] text-xl">
        🎬
        <span className="absolute bottom-0.5 right-0.5 rounded bg-black/75 px-1 text-[9.5px]">
          {formatDuration(video.duration_sec)}
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] font-medium">{title}</div>
        <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-muted">
          <span>{platformLabel(video.source_platform)}</span>
          {video.source_author && (
            <>
              <span className="opacity-40">·</span>
              <span>{video.source_author}</span>
            </>
          )}
          <span className="opacity-40">·</span>
          <span>{formatDuration(video.duration_sec)}</span>
        </div>
        <div className="mt-1.5 text-[11px] text-warn">Đã nhận dạng xong — chờ dịch</div>
      </div>

      <div className="w-20 shrink-0 text-right">
        <div className="text-[15px] font-semibold leading-none">
          {cueCount != null ? formatCount(cueCount) : loadingCues ? "…" : "—"}
        </div>
        <div className="mt-1 text-[10.5px] text-muted">
          {cueCount != null || loadingCues ? "câu thoại" : "chưa có phụ đề"}
        </div>
      </div>

      <select
        className="input w-48 shrink-0 py-1"
        value={model}
        disabled={models.length === 0}
        onChange={(e) => setChosen(e.target.value)}
        aria-label="Chọn model AI để dịch video này"
      >
        {models.length === 0 && <option value="">Chưa có model</option>}
        {models.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>

      <button
        className="btn btn-primary btn-sm shrink-0"
        disabled={pending || !model}
        onClick={() => onTranslate(video.id, model)}
      >
        {pending ? "Đang gửi…" : "Dịch"}
      </button>
    </div>
  );
}
