"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";

interface Props {
  selectedCount: number;
  /** true khi đang chờ một bulk mutation khác trả lời — chặn bấm chồng thao tác. */
  pending?: boolean;
  onApprove: () => void;
  onRetry: () => void;
  onDelete: () => void;
  onApplyPreset: (presetId: string) => void;
  /**
   * Chỉ tab "Chờ dịch" truyền hai prop dưới đây. Không truyền thì phần dịch
   * hàng loạt không hiện — video ở trạng thái khác `review` không dịch được.
   */
  translateModels?: string[];
  onTranslate?: (llmModel: string) => void;
}

/** Thanh hành động hàng loạt sticky ở đáy trang Thư viện, hiện khi có video được chọn. */
export function BulkActionBar({
  selectedCount,
  pending,
  onApprove,
  onRetry,
  onDelete,
  onApplyPreset,
  translateModels = [],
  onTranslate,
}: Props) {
  // Preset áp cho video chỉ lấy kind="process" — backend từ chối kind khác.
  const { data: presets } = useQuery({
    queryKey: ["presets", "process"],
    queryFn: () => api.listPresets("process"),
  });
  const [presetId, setPresetId] = useState("");
  // Giống dropdown ở từng dòng: mặc định model đầu danh sách, tính khi render để
  // không phải đồng bộ state khi danh sách model về muộn.
  const [chosenModel, setChosenModel] = useState("");
  const llmModel = chosenModel || translateModels[0] || "";

  if (selectedCount === 0) return null;

  return (
    <div className="sticky bottom-0 flex items-center gap-2.5 bg-panel2 border border-accent/30 rounded-xl px-4 py-3 mt-3 shadow-[0_-6px_26px_rgba(0,0,0,0.4)] flex-wrap">
      <span className="text-[13px] font-medium">Đã chọn {selectedCount} video</span>

      {onTranslate && (
        <>
          <select
            className="input py-1"
            value={llmModel}
            disabled={translateModels.length === 0}
            onChange={(e) => setChosenModel(e.target.value)}
            aria-label="Chọn model AI để dịch các video đã chọn"
          >
            {translateModels.length === 0 && <option value="">Chưa có model</option>}
            {translateModels.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <button
            className="btn btn-primary btn-sm"
            disabled={pending || !llmModel}
            onClick={() => onTranslate(llmModel)}
          >
            Dịch với AI…
          </button>
        </>
      )}

      <button className="btn btn-sm" disabled={pending} onClick={onApprove}>
        ✓ Duyệt
      </button>

      <button className="btn btn-sm" disabled={pending} onClick={onRetry}>
        Xử lý lại
      </button>

      <select
        className="input py-1"
        value={presetId}
        onChange={(e) => setPresetId(e.target.value)}
        aria-label="Chọn preset xử lý để áp cho video đã chọn"
      >
        <option value="">Chọn preset xử lý…</option>
        {presets?.map((preset) => (
          <option key={preset.id} value={preset.id}>
            {preset.name}
          </option>
        ))}
      </select>
      <button
        className="btn btn-sm"
        disabled={pending || !presetId}
        onClick={() => {
          onApplyPreset(presetId);
          setPresetId("");
        }}
      >
        Áp preset
      </button>

      <button
        className="btn btn-sm text-err border-err/35 ml-auto"
        disabled={pending}
        onClick={onDelete}
      >
        Xoá
      </button>
    </div>
  );
}
