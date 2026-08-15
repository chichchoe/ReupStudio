import { redirect } from "next/navigation";

/**
 * Trang "Nguồn Trung Quốc" đã gộp vào `/library`.
 *
 * Giữ lại đường dẫn này thay vì xoá hẳn vì nó nằm trong bookmark, trong link
 * cũ ở trang Tổng quan, và trong query string `?tab=channels`. Chuyển hướng
 * còn giữ nguyên tab kênh theo dõi để người đang dùng không bị đá về đầu danh
 * sách.
 */
export default async function SourcesPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab } = await searchParams;
  redirect(tab === "channels" ? "/library?tab=kenh" : "/library");
}
