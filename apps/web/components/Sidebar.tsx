"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  href: string;
  label: string;
  icon: string;
  /** Chưa làm ở chặng M1 — hiện mờ để biết lộ trình. */
  soon?: boolean;
}

const GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Làm việc",
    items: [
      { href: "/", label: "Tổng quan", icon: "◲" },
      { href: "/pipelines", label: "Luồng tự động", icon: "⚡", soon: true },
      { href: "/sources", label: "Nguồn Trung Quốc", icon: "↓" },
      { href: "/library", label: "Thư viện", icon: "▤" },
      { href: "/editor", label: "Editor", icon: "✧" },
    ],
  },
  {
    title: "Phân phối",
    items: [
      { href: "/channels", label: "Kênh Việt Nam", icon: "◈", soon: true },
      { href: "/schedule", label: "Lịch đăng", icon: "▦", soon: true },
      { href: "/stats", label: "Thống kê", icon: "◑", soon: true },
    ],
  },
  {
    title: "Hệ thống",
    items: [{ href: "/settings", label: "Cài đặt", icon: "⚙", soon: true }],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-[232px] shrink-0 bg-panel border-r border-border py-2.5 overflow-y-auto">
      {GROUPS.map((group) => (
        <div key={group.title}>
          <div className="px-[18px] pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
            {group.title}
          </div>
          {group.items.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "flex items-center gap-3 px-[18px] py-2 text-[13.5px] border-l-2 transition-colors",
                  active
                    ? "bg-accent/10 text-fg border-accent font-medium"
                    : "text-muted border-transparent hover:bg-panel2 hover:text-fg",
                )}
              >
                <span className="w-4 text-center">{item.icon}</span>
                {item.label}
                {item.soon && (
                  <span className="ml-auto text-[10px] text-muted/70 border border-border rounded px-1.5">
                    sắp có
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      ))}
    </aside>
  );
}
