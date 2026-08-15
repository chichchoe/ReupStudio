"use client";

import { useEffect } from "react";
import { PasteLinksForm } from "./PasteLinksForm";

interface Props {
  onDong: () => void;
}

/**
 * Modal dán link.
 *
 * Trước đây ô dán nằm thẳng trong trang và bị ép nhỏ để không lấn danh sách,
 * nên dán quá năm sáu link là phải cuộn trong khung nhập mới thấy hết. Ở modal
 * thì khung nhập cao gấp đôi và không tranh chỗ với thứ gì.
 *
 * Vẫn để nguyên `PasteLinksForm` bên trong: chỗ nhập link chỉ nên có MỘT bản
 * để sửa, còn modal chỉ là cái khung bọc.
 */
export function ThemVideoModal({ onDong }: Props) {
  useEffect(() => {
    const nghe = (e: KeyboardEvent) => {
      if (e.key === "Escape") onDong();
    };
    window.addEventListener("keydown", nghe);
    return () => window.removeEventListener("keydown", nghe);
  }, [onDong]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-6"
      onClick={(e) => {
        // Chỉ đóng khi bấm trúng nền. Bấm trong khung — kể cả quét chọn chữ rồi
        // nhả chuột ra ngoài — không được làm mất link vừa dán.
        if (e.target === e.currentTarget) onDong();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="them-video-title"
        className="card my-auto w-full max-w-2xl"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 id="them-video-title" className="text-[15px] font-semibold">
            Thêm video
          </h2>
          <button className="text-muted hover:text-fg" onClick={onDong} aria-label="Đóng">
            ✕
          </button>
        </div>

        <PasteLinksForm soDong={14} onXong={onDong} />
      </div>
    </div>
  );
}
