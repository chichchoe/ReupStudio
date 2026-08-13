import type { SafeArea } from "@/lib/types";

interface Props {
  /** Nhãn nền tảng đang xem trước, hiện phía trên khung. */
  platformLabel: string;
  safeArea: SafeArea;
}

/**
 * Khung 9:16 vẽ trực quan `safe_area`: 4 dải mờ áp theo cạnh khung hình,
 * kích thước đúng theo phần trăm đang nhập — đổi số ở bảng thì dải đổi theo
 * ngay (component chỉ nhận props, không tự giữ state).
 *
 * Đây là phần quan trọng nhất của tab — 4 con số trần (`top/bottom/left/right`)
 * không ai hình dung được vùng nào bị chắn, nên khung này thay lời giải thích.
 */
export function SafeAreaPreview({ platformLabel, safeArea }: Props) {
  const pct = (v: number) => `${Math.round(v * 100)}%`;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="text-[12.5px] font-medium">{platformLabel}</div>

      <div className="relative w-[132px] aspect-[9/16] rounded-lg overflow-hidden border border-border bg-panel3 shadow-inner">
        {/* Khung hình gốc — vùng còn lại (không bị dải phủ) là nơi phụ đề được đặt. */}
        <div className="absolute inset-0 flex items-center justify-center text-[10px] text-muted px-2 text-center leading-tight">
          Vùng đặt phụ đề
        </div>

        {/* 4 dải chắn — mỗi dải là % khung hình tính từ cạnh tương ứng, luật số 2 CLAUDE.md. */}
        <div
          className="absolute top-0 left-0 right-0 bg-warn/25 border-b border-warn/50"
          style={{ height: pct(safeArea.top) }}
        />
        <div
          className="absolute bottom-0 left-0 right-0 bg-warn/25 border-t border-warn/50"
          style={{ height: pct(safeArea.bottom) }}
        />
        <div
          className="absolute top-0 bottom-0 left-0 bg-warn/25 border-r border-warn/50"
          style={{ width: pct(safeArea.left) }}
        />
        <div
          className="absolute top-0 bottom-0 right-0 bg-warn/25 border-l border-warn/50"
          style={{ width: pct(safeArea.right) }}
        />
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10.5px] text-muted w-[132px]">
        <span>Trên {pct(safeArea.top)}</span>
        <span>Dưới {pct(safeArea.bottom)}</span>
        <span>Trái {pct(safeArea.left)}</span>
        <span>Phải {pct(safeArea.right)}</span>
      </div>
    </div>
  );
}
