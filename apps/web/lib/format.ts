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
  other: "Khác",
};

export function platformLabel(key: string): string {
  return PLATFORM_LABEL[key] ?? key;
}

/** Đổi số byte thành chuỗi dễ đọc (MB) — dùng cho danh sách render variant. */
export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes < 0) return "—";
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(mb < 10 ? 2 : 1)} MB`;
}
