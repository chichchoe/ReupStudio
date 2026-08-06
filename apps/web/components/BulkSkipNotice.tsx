import type { BulkResult } from "@/lib/types";

const ACTION_LABEL: Record<string, string> = {
  approve: "duyệt",
  delete: "xoá",
  retry: "xử lý lại",
  apply_preset: "áp preset",
  assign_channels: "gán kênh",
};

interface Props {
  result: BulkResult;
  onDismiss: () => void;
}

/**
 * Banner báo video nào bị bỏ qua khi thực hiện hành động hàng loạt, kèm lý do —
 * `skipped` từ backend không bao giờ được nuốt mất, người dùng phải thấy vì sao.
 */
export function BulkSkipNotice({ result, onDismiss }: Props) {
  return (
    <div className="flex items-start justify-between gap-3 bg-warn/10 border border-warn/30 text-warn rounded-lg px-3.5 py-2.5 mb-3 text-[12.5px]">
      <div>
        <div className="font-medium">
          Bỏ qua {result.skipped.length} video khi {ACTION_LABEL[result.action] ?? result.action}
        </div>
        <ul className="list-disc list-inside mt-1 space-y-0.5">
          {result.skipped.map((s) => (
            <li key={s.id}>
              {s.id.slice(0, 8)}… — {s.reason}
            </li>
          ))}
        </ul>
      </div>
      <button
        className="text-muted hover:text-fg shrink-0"
        onClick={onDismiss}
        aria-label="Đóng thông báo"
      >
        ✕
      </button>
    </div>
  );
}
