"use client";

/**
 * Đoạn giải thích thu lại thành một thẻ nhỏ, rê chuột vào là hiện.
 *
 * Mấy đoạn này chỉ cần đọc MỘT lần — lần đầu vào trang. Để nguyên dạng đoạn
 * văn thì lần thứ hai mươi vào sửa cỡ chữ phụ đề vẫn phải lướt qua chúng, và
 * cùng một câu lặp lại dưới sáu thẻ nhà cung cấp thì càng vô nghĩa.
 *
 * Hiện bằng CSS chứ không giữ state: rê vào hiện, rời ra ẩn, không phải bấm
 * mở rồi bấm đóng. `group-focus-within` để bàn phím cũng đọc được — thẻ là
 * `button` nên tab tới được, không phải chuột mới xem được.
 */
interface Props {
  nhan: string;
  children: React.ReactNode;
  /** Thả bong bóng sang trái khi thẻ nằm sát mép phải. */
  vePhai?: boolean;
}

export function TheGiaiThich({ nhan, children, vePhai }: Props) {
  return (
    <span className="group relative">
      <button
        type="button"
        className="cursor-help rounded-full border border-border bg-panel px-2.5 py-[3px] text-[11.5px] text-muted transition-colors group-hover:border-accent/45 group-hover:bg-accent/15 group-hover:text-fg group-focus-within:border-accent/45 group-focus-within:bg-accent/15 group-focus-within:text-fg"
      >
        ⓘ {nhan}
      </button>
      {/* `pointer-events-none` để bong bóng không che mất thứ nằm dưới nó —
          đây là chữ để đọc, không có gì bấm vào trong. */}
      <span
        role="tooltip"
        className={`pointer-events-none invisible absolute top-[calc(100%+6px)] z-20 block w-[46ch] max-w-[80vw] rounded-lg border border-border bg-panel2 p-3 text-[12.5px] leading-relaxed text-muted opacity-0 shadow-lg transition-opacity group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100 ${
          vePhai ? "right-0" : "left-0"
        }`}
      >
        {children}
      </span>
    </span>
  );
}
