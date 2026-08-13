/**
 * Validate phía client cho một dòng `platform_limits`, khớp đúng quy tắc
 * `apps/api/src/services/platform_limit_service.py` — để báo lỗi tiếng Việt
 * ngay khi gõ thay vì đợi round-trip 422 rồi mới biết sai chỗ nào.
 *
 * Đây CHỈ là lớp gợi ý sớm cho người dùng — server vẫn là nguồn sự thật cuối
 * cùng, lỗi trả về từ API (nếu có) luôn được ưu tiên hiển thị.
 */

import type { SafeArea } from "./types";

export interface PlatformLimitDraft {
  max_duration_sec: number;
  max_title_len: number;
  max_desc_len: number;
  max_hashtags: number;
  safe_daily_posts: number;
  safe_area: SafeArea;
  notes: string | null;
}

/** Tổng top+bottom hoặc left+right tối đa — luôn chừa >=40% khung hình cho phụ đề. */
const MAX_SAFE_AREA_SUM = 0.6;

const POSITIVE_INT_FIELDS: readonly (keyof PlatformLimitDraft)[] = [
  "max_title_len",
  "max_desc_len",
  "max_hashtags",
  "safe_daily_posts",
];

const POSITIVE_INT_LABEL: Record<string, string> = {
  max_title_len: "Tiêu đề tối đa",
  max_desc_len: "Mô tả tối đa",
  max_hashtags: "Hashtag tối đa",
  safe_daily_posts: "Bài/ngày an toàn",
};

const SAFE_AREA_LABEL: Record<keyof SafeArea, string> = {
  top: "Trên",
  bottom: "Dưới",
  left: "Trái",
  right: "Phải",
};

export function validatePlatformLimitDraft(draft: PlatformLimitDraft): string | null {
  for (const field of POSITIVE_INT_FIELDS) {
    const value = draft[field];
    if (!Number.isInteger(value) || (value as number) <= 0) {
      return `'${POSITIVE_INT_LABEL[field]}' phải là số nguyên dương`;
    }
  }

  if (!Number.isInteger(draft.max_duration_sec) || draft.max_duration_sec < 0) {
    return "'Thời lượng tối đa' phải là số nguyên >= 0 (0 nghĩa là không giới hạn)";
  }

  for (const key of Object.keys(SAFE_AREA_LABEL) as (keyof SafeArea)[]) {
    const value = draft.safe_area[key];
    if (!(value >= 0 && value < 0.5)) {
      return `Vùng an toàn '${SAFE_AREA_LABEL[key]}' phải trong khoảng [0%, 50%)`;
    }
  }

  if (draft.safe_area.top + draft.safe_area.bottom > MAX_SAFE_AREA_SUM) {
    return "Vùng an toàn Trên + Dưới quá lớn — không còn chỗ đặt phụ đề (tối đa 60%)";
  }
  if (draft.safe_area.left + draft.safe_area.right > MAX_SAFE_AREA_SUM) {
    return "Vùng an toàn Trái + Phải quá lớn — không còn chỗ đặt phụ đề (tối đa 60%)";
  }

  return null;
}
