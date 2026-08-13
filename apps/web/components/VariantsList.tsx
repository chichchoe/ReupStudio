"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatDuration, formatFileSize } from "@/lib/format";
import { TARGET_PLATFORM_LABEL } from "@/lib/types";

interface Props {
  videoId: string;
}

/** Danh sách bản đã render của video, mỗi dòng có nút tải file (`GET /variants/{id}/file`). */
export function VariantsList({ videoId }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["variants", videoId],
    queryFn: () => api.listVariants(videoId),
  });

  return (
    <div className="card">
      <div className="text-[13px] font-medium mb-2.5">Bản đã render</div>

      {isLoading && <p className="text-[12.5px] text-muted">Đang tải…</p>}

      {!isLoading && (!data || data.length === 0) && (
        <p className="text-[12.5px] text-muted">Chưa có bản nào — chọn nền tảng rồi bấm render.</p>
      )}

      {data && data.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {data.map((variant) => (
            <div
              key={variant.id}
              className="flex items-center gap-3 bg-panel2 border border-border rounded-lg px-3 py-2 text-[12.5px]"
            >
              <span className="font-medium w-28 shrink-0">
                {TARGET_PLATFORM_LABEL[variant.target_platform as keyof typeof TARGET_PLATFORM_LABEL] ??
                  variant.target_platform}
              </span>
              {variant.part_total > 1 && (
                <span className="text-muted shrink-0">
                  Tập {variant.part_index}/{variant.part_total}
                </span>
              )}
              <span className="text-muted shrink-0">{formatDuration(variant.duration_sec)}</span>
              {variant.width && variant.height && (
                <span className="text-muted shrink-0">
                  {variant.width}×{variant.height}
                </span>
              )}
              <span className="text-muted shrink-0">{formatFileSize(variant.file_size)}</span>
              {variant.qc_passed === false && (
                <span className="text-warn shrink-0">Chưa đạt QC</span>
              )}
              <span className="flex-1" />
              {variant.out_path ? (
                <a className="btn btn-sm shrink-0" href={api.variantFileUrl(variant.id)} download>
                  ⬇ Tải về
                </a>
              ) : (
                <span className="text-muted shrink-0">Chưa có file</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
