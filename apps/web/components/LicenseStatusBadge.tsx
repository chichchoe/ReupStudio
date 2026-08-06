import clsx from "clsx";
import { LICENSE_STATUS_LABEL, type LicenseStatus } from "@/lib/types";

interface Props {
  status: LicenseStatus;
}

/**
 * Nhãn tình trạng bản quyền của kênh nguồn. `unknown` là chốt an toàn pháp lý
 * (xem `reup_core.enums.LicenseStatus`): backend KHÔNG BAO GIỜ tự động xử lý
 * kênh này. Vì vậy nhãn "Chưa rõ" luôn kèm cảnh báo màu + chữ giải thích ngay
 * cạnh, không chỉ đổi màu chữ cho có.
 */
export function LicenseStatusBadge({ status }: Props) {
  const isUnknown = status === "unknown";

  return (
    <div>
      <span
        className={clsx(
          "inline-block rounded-full border px-2.5 py-0.5 text-[11.5px] font-medium",
          isUnknown ? "bg-warn/15 border-warn/40 text-warn" : "bg-ok/10 border-ok/30 text-ok",
        )}
      >
        {LICENSE_STATUS_LABEL[status]}
      </span>
      {isUnknown && (
        <div className="mt-1 max-w-[220px] text-[11px] leading-snug text-warn">
          ⚠ Chưa xác nhận quyền — sẽ KHÔNG tự động xử lý
        </div>
      )}
    </div>
  );
}
