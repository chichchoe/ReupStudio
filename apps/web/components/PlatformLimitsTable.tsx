"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { TARGET_PLATFORM_LABEL, type SafeArea } from "@/lib/types";
import { PlatformLimitRow } from "./PlatformLimitRow";
import { SafeAreaPreview } from "./SafeAreaPreview";

const DEFAULT_SAFE_AREA: SafeArea = { top: 0, bottom: 0, left: 0, right: 0 };

/**
 * Bảng giới hạn nền tảng, sửa trực tiếp tại chỗ (`GET`/`PATCH /platform-limits`)
 * + xem trước vùng an toàn trực quan. Bấm vào một ô số ở dòng nào, khung 9:16
 * bên phải hiện đúng `safe_area` dòng đó và đổi NGAY theo số đang gõ — chưa
 * cần bấm "Lưu".
 */
export function PlatformLimitsTable() {
  const { data, isLoading } = useQuery({
    queryKey: ["platform-limits"],
    queryFn: api.listPlatformLimits,
  });

  const [previewPlatform, setPreviewPlatform] = useState<string | null>(null);
  const [liveSafeArea, setLiveSafeArea] = useState<Record<string, SafeArea>>({});

  const activePlatform = previewPlatform ?? data?.[0]?.platform ?? null;
  const activeLimit = data?.find((l) => l.platform === activePlatform);
  const previewSafeArea =
    (activePlatform ? liveSafeArea[activePlatform] : undefined) ??
    activeLimit?.safe_area ??
    DEFAULT_SAFE_AREA;

  if (isLoading) return <p className="text-[13px] text-muted py-4">Đang tải giới hạn nền tảng…</p>;
  if (!data || data.length === 0) {
    return <p className="text-[13px] text-muted py-4">Chưa có dữ liệu giới hạn nền tảng.</p>;
  }

  return (
    <div className="flex gap-5 flex-wrap items-start">
      <div className="card flex-1 min-w-[560px] overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="text-[10.5px] uppercase tracking-wide text-muted border-b border-border">
              <th className="px-2 py-2 font-medium">Nền tảng</th>
              <th className="px-2 py-2 font-medium">Thời lượng (giây)</th>
              <th className="px-2 py-2 font-medium">Tiêu đề (ký tự)</th>
              <th className="px-2 py-2 font-medium">Mô tả (ký tự)</th>
              <th className="px-2 py-2 font-medium">Hashtag</th>
              <th className="px-2 py-2 font-medium">Bài/ngày an toàn</th>
              <th className="px-2 py-2 font-medium">Vùng an toàn (trên/dưới/trái/phải)</th>
              <th className="px-2 py-2 font-medium">Ghi chú</th>
              <th className="px-2 py-2 font-medium"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.map((limit) => (
              <PlatformLimitRow
                key={limit.platform}
                limit={limit}
                previewed={limit.platform === activePlatform}
                onFocusRow={setPreviewPlatform}
                onSafeAreaDraftChange={(platform, safeArea) =>
                  setLiveSafeArea((prev) => ({ ...prev, [platform]: safeArea }))
                }
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className="card shrink-0">
        <div className="text-[11px] text-muted mb-2 max-w-[132px] leading-snug">
          Xem trước vùng an toàn — bấm vào một ô số ở dòng nào để xem dòng đó.
        </div>
        <SafeAreaPreview
          platformLabel={
            activePlatform
              ? TARGET_PLATFORM_LABEL[activePlatform as keyof typeof TARGET_PLATFORM_LABEL] ??
                activePlatform
              : "—"
          }
          safeArea={previewSafeArea}
        />
      </div>
    </div>
  );
}
