"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { api } from "@/lib/api";
import { formatCount, formatDuration, platformLabel } from "@/lib/format";
import type { TtsOptions, TuyChonDich, Video } from "@/lib/types";

/** Bản phụ đề gốc tiếng Trung — số cue của bản này chính là số câu thoại của video. */
const SOURCE_LANG = "zh";

/**
 * Trên ngần này câu thì Gemini TTS ăn hết hạn mức ngày (500 lượt, mỗi câu một
 * lượt). Cảnh báo ngay tại chỗ chọn, vì biết sau khi chạy được nửa video thì
 * đã muộn.
 */
const CAU_TOI_DA_CHO_GEMINI = 400;

interface Props {
  video: Video;
  /** Danh sách model dịch từ `GET /llm/models`; tab cha tải một lần rồi truyền xuống. */
  models: string[];
  /** Model cấu hình sẵn (`LLM_MODEL`), chọn sẵn trong ô chọn. */
  defaultModel: string;
  /** Giọng đọc theo từng nhà cung cấp, từ `GET /videos/tts-options`. */
  ttsOptions: TtsOptions[];
  selected: boolean;
  /** true khi yêu cầu dịch của chính video này đang bay — chặn bấm hai lần. */
  pending: boolean;
  onToggle: (id: string) => void;
  onTranslate: (id: string, tuyChon: TuyChonDich) => void;
}

/**
 * Một dòng video chờ dịch. Ba quyết định người dùng phải ra TRƯỚC khi chạy, và
 * cả ba đều tốn kém nếu chọn sai:
 *
 * - **Model dịch** — hạn mức mỗi model khác nhau cả chục lần.
 * - **Xoá chữ cứng** — bước nặng nhất pipeline, video một tiếng mất hàng tiếng.
 *   Video không có chữ cứng thì bỏ tích là tiết kiệm được ngần ấy.
 * - **Giọng đọc** — Gemini hay hơn nhưng tính hạn mức mỗi câu.
 *
 * Vì vậy dòng này hiện SỐ CÂU THOẠI: đó là con số quyết định cả ba lựa chọn,
 * và không thể bắt người dùng mở từng video ra đếm.
 */
export function PendingVideoRow({
  video,
  models,
  defaultModel,
  ttsOptions,
  selected,
  pending,
  onToggle,
  onTranslate,
}: Props) {
  const { data: subtitles, isLoading: loadingCues } = useQuery({
    queryKey: ["subtitles", video.id, SOURCE_LANG],
    queryFn: () => api.subtitles(video.id, SOURCE_LANG),
  });
  const cueCount = subtitles?.find((s) => s.lang === SOURCE_LANG)?.cues.length ?? null;

  // Chưa chọn gì thì lấy model MẶC ĐỊNH backend trả về, không phải model đầu
  // danh sách. Ảnh chụp giao diện thật (2026-08-15) cho thấy hậu quả của việc
  // lấy option đầu: ô chọn hiện model 20 lượt/NGÀY trong khi cấu hình để model
  // 500 lượt/ngày — ai bấm nhanh dính đúng model tệ nhất mà không biết.
  const [chosen, setChosen] = useState("");
  const model = chosen || defaultModel || models[0] || "";

  const [xoaChuCung, setXoaChuCung] = useState(true);
  const [provider, setProvider] = useState(ttsOptions[0]?.provider ?? "edge");
  const [giong, setGiong] = useState("");

  const nhomGiong = ttsOptions.find((o) => o.provider === provider);
  const giongDaChon = giong || nhomGiong?.giong?.[0]?.ma || "";
  const quaNhieuCauChoGemini =
    provider === "gemini" && cueCount != null && cueCount > CAU_TOI_DA_CHO_GEMINI;

  const title = video.title_vi || video.title_original || video.source_video_id;

  function doiProvider(ma: string) {
    setProvider(ma);
    // Giọng của nhà cung cấp cũ không tồn tại ở nhà cung cấp mới — xoá đi để
    // rơi về giọng đầu danh sách, thay vì gửi lên một mã giọng không có thật.
    setGiong("");
  }

  return (
    <div
      className={clsx(
        "mb-2 rounded-xl border bg-panel p-3 transition-colors",
        selected ? "border-accent/55 bg-accent/5" : "border-border hover:border-[#39404F]",
      )}
    >
      <div className="flex items-center gap-3">
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

        <button
          className="btn btn-primary btn-sm shrink-0"
          disabled={pending || !model}
          onClick={() =>
            onTranslate(video.id, {
              llmModel: model,
              xoaChuCung,
              ttsProvider: provider,
              giongDoc: giongDaChon,
            })
          }
        >
          {pending ? "Đang gửi…" : "Dịch"}
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-3">
        <label className="flex items-center gap-2 text-[12px]">
          <span className="text-muted">AI dịch</span>
          <select
            className="input w-44 py-1"
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
        </label>

        <label className="flex items-center gap-2 text-[12px]">
          <input
            type="checkbox"
            checked={xoaChuCung}
            onChange={(e) => setXoaChuCung(e.target.checked)}
            className="h-3.5 w-3.5 accent-[color:var(--accent,#5B8CFF)]"
          />
          <span>Xoá chữ cứng và watermark</span>
          <span className="text-[11px] text-muted">
            {xoaChuCung ? "· bước nặng nhất, video 1 tiếng mất hàng tiếng" : "· bỏ qua, chạy nhanh"}
          </span>
        </label>

        <label className="flex items-center gap-2 text-[12px]">
          <span className="text-muted">Giọng</span>
          <select
            className="input w-28 py-1"
            value={provider}
            onChange={(e) => doiProvider(e.target.value)}
            aria-label="Chọn nhà cung cấp giọng đọc"
          >
            {ttsOptions.map((o) => (
              <option key={o.provider} value={o.provider}>
                {o.provider}
              </option>
            ))}
          </select>
          <select
            className="input w-48 py-1"
            value={giongDaChon}
            onChange={(e) => setGiong(e.target.value)}
            aria-label="Chọn giọng đọc"
          >
            {(nhomGiong?.giong ?? []).map((g) => (
              <option key={g.ma} value={g.ma}>
                {g.ten}
              </option>
            ))}
          </select>
        </label>
      </div>

      {nhomGiong?.ghi_chu && (
        <div className={clsx("mt-2 text-[11px]", quaNhieuCauChoGemini ? "text-err" : "text-muted")}>
          {quaNhieuCauChoGemini
            ? `Video có ${cueCount} câu — Gemini tính mỗi câu một lượt, sẽ hết hạn mức ngày giữa chừng. Dùng edge-tts cho video này.`
            : nhomGiong.ghi_chu}
        </div>
      )}
    </div>
  );
}
