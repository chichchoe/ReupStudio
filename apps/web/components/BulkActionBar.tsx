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
}

/** Thanh hành động hàng loạt sticky ở đáy trang Thư viện, hiện khi có video được chọn. */
export function BulkActionBar({
  selectedCount,
  pending,
  onApprove,
  onRetry,
  onDelete,
  onApplyPreset,
}: Props) {
  // Preset áp cho video chỉ lấy kind="process" — backend từ chối kind khác.
  const { data: presets } = useQuery({
    queryKey: ["presets", "process"],
    queryFn: () => api.listPresets("process"),
  });
  const [presetId, setPresetId] = useState("");

  if (selectedCount === 0) return null;

  return (
    <div className="sticky bottom-0 flex items-center gap-2.5 bg-panel2 border border-accent/30 rounded-xl px-4 py-3 mt-3 shadow-[0_-6px_26px_rgba(0,0,0,0.4)] flex-wrap">
      <span className="text-[13px] font-medium">Đã chọn {selectedCount} video</span>

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
