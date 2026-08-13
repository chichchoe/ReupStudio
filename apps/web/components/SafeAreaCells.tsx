import type { SafeArea } from "@/lib/types";

/** Chuỗi hiển thị 4 ô `safe_area` — tách riêng khỏi số đã parse, xem `parseDecimal`. */
export type SafeAreaText = Record<keyof SafeArea, string>;

export function toSafeAreaText(safeArea: SafeArea): SafeAreaText {
  return {
    top: String(safeArea.top),
    bottom: String(safeArea.bottom),
    left: String(safeArea.left),
    right: String(safeArea.right),
  };
}

/**
 * Parse số thập phân người dùng gõ, chấp nhận cả dấu phẩy lẫn dấu chấm.
 *
 * Lý do cần hàm riêng: `<input type="number">` ở hệ điều hành/trình duyệt đặt
 * locale vi-VN (dấu phẩy thập phân) ÂM THẦM chặn phím "." — gõ "0.3" chỉ còn
 * lại "3" (mất dấu chấm), overlay xem trước lệch hẳn (phát hiện khi bấm thử
 * trên trình duyệt thật). Vì vậy 4 ô `safe_area` dùng `type="text"` +
 * `inputMode="decimal"` và tự parse ở đây thay vì để trình duyệt lo.
 */
export function parseDecimal(raw: string): number | null {
  const normalized = raw.trim().replace(",", ".");
  if (normalized === "" || normalized === "." || normalized === "-") return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

interface Props {
  text: SafeAreaText;
  onFocus: () => void;
  onChange: (key: keyof SafeArea, raw: string) => void;
}

/** 4 ô nhập `safe_area` (trên/dưới/trái/phải) của một dòng nền tảng. */
export function SafeAreaCells({ text, onFocus, onChange }: Props) {
  return (
    <div className="grid grid-cols-2 gap-1 w-[104px]">
      {(["top", "bottom", "left", "right"] as (keyof SafeArea)[]).map((key) => (
        <input
          key={key}
          type="text"
          inputMode="decimal"
          className="input w-full py-1 px-2 text-[12px]"
          value={text[key]}
          onFocus={onFocus}
          onChange={(e) => onChange(key, e.target.value)}
        />
      ))}
    </div>
  );
}
