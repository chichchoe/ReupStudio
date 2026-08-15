"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { BulkActionBar } from "@/components/BulkActionBar";
import { BulkSkipNotice } from "@/components/BulkSkipNotice";
import { LlmQuotaStrip } from "@/components/LlmQuotaStrip";
import { PendingVideoRow } from "@/components/PendingVideoRow";
import { api, ApiError } from "@/lib/api";
import type { BulkResult } from "@/lib/types";
import { useLibraryMutations } from "@/lib/useLibraryMutations";
import { useTranslateMutations, type TranslateFailure } from "@/lib/useTranslateMutations";

/** Pipeline dừng sau bước nhận dạng giọng nói và để video ở đúng trạng thái này. */
const REVIEW_STATUS = "review";
/** Tab này không có ô tìm kiếm; giữ chuỗi rỗng để khoá cache khớp `useLibraryMutations`. */
const NO_QUERY = "";

/**
 * Tab "Chờ dịch" của trang Thư viện.
 *
 * Pipeline cố ý dừng ở đây: lúc này đã biết video có bao nhiêu câu thoại nên
 * người dùng chọn model cho hợp — video 672 câu chọn model hạn mức cao, video
 * 50 câu chọn model chất lượng cao. Vì vậy số câu thoại và dropdown model phải
 * nằm ngay trên dòng, cạnh nút Dịch.
 */
export function PendingTranslateTab() {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkNotice, setBulkNotice] = useState<BulkResult | null>(null);
  const [failures, setFailures] = useState<TranslateFailure[]>([]);

  // Khoá cache phải đúng dạng ["videos", status, query] — hai hook mutation bên
  // dưới sửa thẳng vào ô cache này để cập nhật lạc quan.
  const videosKey = useMemo(() => ["videos", REVIEW_STATUS, NO_QUERY] as const, []);

  const { data, isLoading } = useQuery({
    queryKey: videosKey,
    queryFn: () => api.listVideos({ status: REVIEW_STATUS }),
  });
  const { data: models, error: modelsError } = useQuery({
    queryKey: ["llm-models"],
    queryFn: api.llmModels,
  });
  const { data: nhaCungCap = [] } = useQuery({
    queryKey: ["ai-providers"],
    queryFn: api.nhaCungCapAI,
    staleTime: 5 * 60 * 1000,
  });
  const { data: ttsOptions = [] } = useQuery({
    queryKey: ["tts-options"],
    queryFn: api.ttsOptions,
    //: Danh sách giọng gần như không đổi — không cần hỏi lại mỗi lần đổi tab.
    staleTime: 10 * 60 * 1000,
  });

  const videos = useMemo(() => data?.items ?? [], [data]);
  const translateModels = models?.translate ?? [];
  //: Model cấu hình sẵn để chọn trước trong ô chọn — không có thì rơi về
  //: model đầu danh sách, mà model đầu thường là bản hạn mức thấp.
  const defaultModel = models?.default ?? "";

  const { translate, pendingIds, translatePending } = useTranslateMutations({
    videosKey,
    onDone: (result) => {
      setSelected(new Set());
      setFailures(result);
    },
  });

  const { bulk, bulkPending } = useLibraryMutations({
    status: REVIEW_STATUS,
    query: NO_QUERY,
    onBulkDone: (result) => {
      setSelected(new Set());
      setBulkNotice(result.skipped.length > 0 ? result : null);
    },
  });

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div>
      <LlmQuotaStrip />

      {/* Danh sách model rỗng vì lỗi khác hẳn "nhà cung cấp không có model nào" —
          nói rõ lý do, nếu không người dùng chỉ thấy dropdown trống mà không hiểu. */}
      {modelsError && (
        <div className="mb-3 rounded-lg border border-warn/30 bg-warn/10 px-3.5 py-2.5 text-[12.5px] text-warn">
          Chưa lấy được danh sách model AI:{" "}
          {modelsError instanceof ApiError ? modelsError.message : "lỗi không rõ"}
        </div>
      )}

      {bulkNotice && <BulkSkipNotice result={bulkNotice} onDismiss={() => setBulkNotice(null)} />}

      {/* Video gửi dịch lỗi phải hiện rõ kèm lý do, không im lặng bỏ qua. */}
      {failures.length > 0 && (
        <div className="mb-3 flex items-start justify-between gap-3 rounded-lg border border-err/30 bg-err/10 px-3.5 py-2.5 text-[12.5px] text-err">
          <div>
            <div className="font-medium">Không gửi được {failures.length} video đi dịch</div>
            <ul className="mt-1 list-inside list-disc space-y-0.5">
              {failures.map((f) => (
                <li key={f.id}>
                  {f.id.slice(0, 8)}… — {f.message}
                </li>
              ))}
            </ul>
          </div>
          <button
            className="shrink-0 text-muted hover:text-fg"
            onClick={() => setFailures([])}
            aria-label="Đóng thông báo"
          >
            ✕
          </button>
        </div>
      )}

      {isLoading && <p className="py-8 text-center text-[13px] text-muted">Đang tải…</p>}

      {!isLoading && videos.length === 0 && (
        <div className="py-16 text-center text-[13px] text-muted">
          Không có video nào đang chờ dịch.
        </div>
      )}

      {videos.map((video) => (
        <PendingVideoRow
          key={video.id}
          video={video}
          nhaCungCap={nhaCungCap}
          selected={selected.has(video.id)}
          pending={pendingIds.has(video.id)}
          ttsOptions={ttsOptions}
          onToggle={toggle}
          onTranslate={(id, tuyChon) => translate([id], tuyChon)}
        />
      ))}

      <BulkActionBar
        selectedCount={selected.size}
        pending={bulkPending || translatePending}
        translateModels={translateModels}
        onTranslate={(model) =>
          //: Chọn hàng loạt thì dùng mặc định AN TOÀN: vẫn xoá chữ cứng (đó là
          //: lý do chính dùng công cụ này) và giọng miễn phí không tính lượt.
          //: Muốn khác thì bấm Dịch ở từng dòng.
          translate([...selected], {
            llmProvider: nhaCungCap.find((n) => n.da_dat_khoa || !n.can_khoa)?.ma ?? "",
            llmModel: model,
            xoaChuCung: true,
            ttsProvider: "edge",
            giongDoc: "vi-VN-HoaiMyNeural",
          })
        }
        onApprove={() => bulk([...selected], "approve")}
        onRetry={() => bulk([...selected], "retry")}
        onDelete={() => bulk([...selected], "delete")}
        onApplyPreset={(presetId) => bulk([...selected], "apply_preset", { preset_id: presetId })}
      />
    </div>
  );
}
