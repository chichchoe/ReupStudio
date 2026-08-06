"use client";

import clsx from "clsx";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ChannelsTab } from "@/components/ChannelsTab";
import { PasteLinksForm } from "@/components/PasteLinksForm";

type Tab = "links" | "channels";

const TABS: { value: Tab; label: string }[] = [
  { value: "links", label: "Dán link" },
  { value: "channels", label: "Kênh theo dõi" },
];

function SourcesInner() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab: Tab = params.get("tab") === "channels" ? "channels" : "links";

  // Đồng bộ tab đang chọn vào query string (`?tab=channels`) để tải lại trang
  // vẫn giữ đúng tab, giống cách `library/page.tsx` đồng bộ bộ lọc.
  const setTab = (next: Tab) => {
    const qs = new URLSearchParams(params.toString());
    if (next === "links") qs.delete("tab");
    else qs.set("tab", next);
    const query = qs.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  return (
    <div className="max-w-4xl">
      <header className="mb-5">
        <h1 className="text-xl font-semibold">Nguồn Trung Quốc</h1>
        <p className="mt-0.5 text-[13px] text-muted">
          Douyin · Bilibili · Kuaishou · Xiaohongshu · Weibo
        </p>
      </header>

      <div className="mb-5 flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={clsx("chip", tab === t.value && "chip-active")}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "links" ? <PasteLinksForm /> : <ChannelsTab />}
    </div>
  );
}

export default function SourcesPage() {
  return (
    <Suspense fallback={<p className="text-[13px] text-muted">Đang tải…</p>}>
      <SourcesInner />
    </Suspense>
  );
}
