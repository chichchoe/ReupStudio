"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { api, ApiError } from "@/lib/api";
import { formatCount, formatTokenCount, formatUsd } from "@/lib/format";

/**
 * Chạm 80% trần là đổi màu vàng. Cảnh báo sớm để người dùng kịp đổi sang model
 * hạn mức cao trước khi cả lô video bị chặn giữa chừng.
 */
const QUOTA_WARN_RATIO = 0.8;

/**
 * Trần bằng 0 nghĩa là KHÔNG giới hạn (theo hợp đồng API), không phải "hết hạn
 * mức" — khi đó chỉ hiện số đã dùng, tuyệt đối không hiện phần "/trần".
 */
function usageText(used: number, cap: number, format: (n: number) => string): string {
  return cap > 0 ? `${format(used)}/${format(cap)}` : format(used);
}

function isNearCap(used: number, cap: number): boolean {
  return cap > 0 && used / cap >= QUOTA_WARN_RATIO;
}

/** Dải số liệu hạn mức LLM đặt phía trên danh sách video chờ dịch. */
export function LlmQuotaStrip() {
  const { data, isLoading, error } = useQuery({ queryKey: ["llm-usage"], queryFn: api.llmUsage });

  // Không nuốt lỗi thành trạng thái "đang tải" vĩnh viễn: endpoint này trả lỗi
  // riêng khi khoá API sai (LLM_AUTH_FAILED), người dùng cần biết để đi sửa.
  if (error) {
    return (
      <div className="mb-3 rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-[12px] text-warn">
        Chưa lấy được số liệu hạn mức: {error instanceof ApiError ? error.message : "lỗi không rõ"}
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="mb-3 rounded-lg border border-border bg-panel px-3 py-2 text-[12px] text-muted">
        Đang tải hạn mức…
      </div>
    );
  }

  const nearDay = isNearCap(data.requests_last_day, data.max_requests_per_day);
  const nearMinute = isNearCap(data.requests_last_min, data.max_requests_per_min);
  const nearMoney = isNearCap(data.cost_usd_this_month, data.monthly_budget_usd);
  const warn = nearDay || nearMinute || nearMoney;

  return (
    <div
      className={clsx(
        "mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border px-3 py-2 text-[12px]",
        warn ? "border-warn/30 bg-warn/10 text-warn" : "border-border bg-panel text-muted",
      )}
    >
      <span className="font-medium">Hạn mức AI</span>
      <span className="opacity-40">·</span>

      <span className={clsx(nearDay && "font-medium")}>
        hôm nay: {usageText(data.requests_last_day, data.max_requests_per_day, formatCount)} lượt
      </span>
      <span className="opacity-40">·</span>

      <span>{formatTokenCount(data.tokens_last_day)} token</span>
      <span className="opacity-40">·</span>

      <span className={clsx(nearMoney && "font-medium")}>
        {usageText(data.cost_usd_this_month, data.monthly_budget_usd, formatUsd)}
      </span>

      {/* Trần theo phút là thứ chặn thao tác hàng loạt sớm nhất, nên hiện kèm — nhưng chỉ khi có trần. */}
      {data.max_requests_per_min > 0 && (
        <>
          <span className="opacity-40">·</span>
          <span className={clsx(nearMinute && "font-medium")}>
            phút này: {formatCount(data.requests_last_min)}/{formatCount(data.max_requests_per_min)}
          </span>
        </>
      )}

      {warn && (
        <span className="ml-auto font-medium">
          ⚠ Sắp chạm trần — cân nhắc chọn model hạn mức cao hơn.
        </span>
      )}
    </div>
  );
}
