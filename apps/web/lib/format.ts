export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds < 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "vừa xong";
  if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
  return `${Math.floor(diff / 86400)} ngày trước`;
}

const PLATFORM_LABEL: Record<string, string> = {
  douyin: "抖音 Douyin",
  bilibili: "哔哩哔哩",
  kuaishou: "快手 Kuaishou",
  xiaohongshu: "小红书",
  weibo: "微博",
  youtube: "YouTube",
  tiktok: "TikTok",
  instagram: "Instagram",
  facebook: "Facebook",
  twitter: "X",
  other: "Khác",
};

export function platformLabel(key: string): string {
  return PLATFORM_LABEL[key] ?? key;
}

/**
 * Một chữ số thập phân, bỏ đuôi ",0" cho gọn. Dấu phẩy vì giao diện tiếng Việt.
 */
function oneDecimalVi(value: number): string {
  return value.toFixed(1).replace(/\.0$/, "").replace(".", ",");
}

/** Số nguyên kiểu Việt Nam (dấu chấm ngăn nghìn) — dùng cho số lượt gọi, số câu thoại. */
export function formatCount(n: number): string {
  return n.toLocaleString("vi-VN");
}

/**
 * Rút gọn số token: 2_100_000 → "2,1M". Dải hạn mức rất chật chỗ, in đủ chữ số
 * làm dòng bị tràn và mắt khó bắt được con số quan trọng.
 */
export function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${oneDecimalVi(n / 1_000_000)}M`;
  if (n >= 1_000) return `${oneDecimalVi(n / 1_000)}K`;
  return formatCount(n);
}

/** Tiền USD hiển thị kiểu Việt Nam: 0 → "$0,00". */
export function formatUsd(amount: number): string {
  return `$${amount.toLocaleString("vi-VN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/** Đổi số byte thành chuỗi dễ đọc (MB) — dùng cho danh sách render variant. */
export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes < 0) return "—";
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(mb < 10 ? 2 : 1)} MB`;
}
