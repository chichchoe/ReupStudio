"use client";

import { useEffect, useRef } from "react";

interface Props {
  tieuDe: string;
  /** Nói rõ xoá cái gì và mất gì. Tên video, số lượng, thứ không lấy lại được. */
  moTa: React.ReactNode;
  nhanXacNhan?: string;
  dangChay?: boolean;
  onXacNhan: () => void;
  onHuy: () => void;
}

/**
 * Hộp hỏi lại trước khi xoá.
 *
 * Dùng chung cho MỌI nút xoá trong tool. Trước đây mỗi chỗ tự xử một kiểu:
 * dòng video xoá thẳng không hỏi, kênh theo dõi hỏi bằng cách đổi chữ trên
 * chính cái nút. Cùng một chữ "Xoá" mà chỗ mất luôn chỗ hỏi lại thì không ai
 * dám bấm chỗ nào.
 *
 * Nút mặc định được chọn là "Huỷ": mở hộp ra rồi gõ Enter theo quán tính thì
 * không mất gì.
 */
export function HopXacNhan({
  tieuDe,
  moTa,
  nhanXacNhan = "Xoá",
  dangChay,
  onXacNhan,
  onHuy,
}: Props) {
  const nutHuy = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    nutHuy.current?.focus();
    const nghe = (e: KeyboardEvent) => {
      if (e.key === "Escape") onHuy();
    };
    window.addEventListener("keydown", nghe);
    return () => window.removeEventListener("keydown", nghe);
  }, [onHuy]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/65 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onHuy();
      }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="xac-nhan-tieu-de"
        className="card w-full max-w-sm"
      >
        <h2 id="xac-nhan-tieu-de" className="text-[15px] font-semibold">
          {tieuDe}
        </h2>
        <div className="mt-2 text-[12.5px] leading-relaxed text-muted">{moTa}</div>

        <div className="mt-4 flex justify-end gap-2">
          <button ref={nutHuy} className="btn" onClick={onHuy} disabled={dangChay}>
            Huỷ
          </button>
          <button
            className="btn border-err bg-err/90 text-white hover:bg-err"
            onClick={onXacNhan}
            disabled={dangChay}
          >
            {dangChay ? "Đang xoá…" : nhanXacNhan}
          </button>
        </div>
      </div>
    </div>
  );
}
