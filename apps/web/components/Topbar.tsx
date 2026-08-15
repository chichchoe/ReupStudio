"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useReupSocket } from "@/lib/ws";

export function Topbar() {
  const { connected } = useReupSocket();
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: false,
  });

  const apiOk = health?.ok ?? false;

  return (
    <header className="h-[52px] shrink-0 flex items-center gap-4 px-4 bg-panel border-b border-border">
      <Link href="/" className="flex items-center gap-2 font-bold text-[15px]">
        <span className="w-6 h-6 rounded-md bg-gradient-to-br from-accent to-run flex items-center justify-center text-xs">
          ▶
        </span>
        ReupStudio
      </Link>

      <nav className="flex items-center gap-3 text-[12.5px]">
        <Link href="/library" className="text-muted hover:text-fg">
          Thư viện
        </Link>
        <Link href="/settings" className="text-muted hover:text-fg">
          Cấu hình
        </Link>
      </nav>

      <div className="ml-auto flex items-center gap-3 text-xs text-muted">
        <Badge ok={apiOk} label={apiOk ? "API sẵn sàng" : "API chưa kết nối"} />
        <Badge ok={connected} label={connected ? "Realtime bật" : "Realtime tắt"} />
      </div>
    </header>
  );
}

function Badge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1.5 bg-bg border border-border rounded-full px-2.5 py-1">
      <span
        className="w-[7px] h-[7px] rounded-full"
        style={{ background: ok ? "#2FBF71" : "#E5484D" }}
      />
      {label}
    </span>
  );
}
