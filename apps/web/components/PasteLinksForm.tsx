"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { CreateFromLinksResult } from "@/lib/types";

const TONES = [
  { value: "doi_thuong", label: "Đời thường" },
  { value: "ngon_tinh", label: "Ngôn tình" },
  { value: "hai_huoc", label: "Hài hước" },
  { value: "trang_trong", label: "Trang trọng" },
];

/** Tab "Dán link" ở trang Nguồn: dán nhiều link, chọn văn phong, gửi vào hàng đợi. */
export function PasteLinksForm() {
  const [text, setText] = useState("");
  const [tone, setTone] = useState("ngon_tinh");
  const [result, setResult] = useState<CreateFromLinksResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const router = useRouter();

  const mutation = useMutation({
    mutationFn: (urls: string[]) => api.createFromLinks(urls, { tone }),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      setText("");
      queryClient.invalidateQueries({ queryKey: ["videos"] });
      queryClient.invalidateQueries({ queryKey: ["counts"] });
      if (data.created > 0) setTimeout(() => router.push("/library"), 1200);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Không gửi được yêu cầu");
    },
  });

  const urls = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  return (
    <div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={6}
        placeholder={`https://v.douyin.com/iRxxxx/
https://www.bilibili.com/video/BV1xx411c7mD
https://www.youtube.com/shorts/xxxxxxxxxxx
https://www.tiktok.com/@user/video/7123456789012345678

Mỗi dòng một link — hỗ trợ link rút gọn và link có tham số share`}
        className="input w-full resize-y font-mono text-[12.5px]"
      />

      <p className="mt-2 text-xs text-muted">
        Nhận link từ Douyin, Bilibili, Kuaishou, Xiaohongshu, Weibo, YouTube, TikTok, Instagram,
        Facebook, X — và hầu hết trang video khác. Nguồn lạ vẫn được thử tải; nếu không tải được,
        video sẽ báo lỗi rõ ràng trong Thư viện.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="text-xs text-muted">Văn phong dịch</label>
        <select value={tone} onChange={(e) => setTone(e.target.value)} className="input">
          {TONES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>

        <span className="text-xs text-muted">
          {urls.length > 0 ? `${urls.length} link` : "chưa có link nào"}
        </span>

        <button
          className="btn btn-primary ml-auto"
          disabled={urls.length === 0 || mutation.isPending}
          onClick={() => mutation.mutate(urls)}
        >
          {mutation.isPending ? "Đang gửi…" : "Thêm vào hàng đợi"}
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-err/25 bg-err/[0.08] p-3 text-[12.5px] text-err">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-4 rounded-lg border border-accent/25 bg-accent/[0.07] p-3 text-[12.5px] text-[#B8C6E8]">
          Đã tạo <b>{result.created}</b> video
          {result.skipped_duplicate > 0 && <> · bỏ qua {result.skipped_duplicate} link trùng</>}
          {result.invalid.length > 0 && (
            <div className="mt-1.5 text-warn">
              {result.invalid.length} link không nhận diện được: {result.invalid[0]}
            </div>
          )}
          {result.created > 0 && <div className="mt-1">Đang chuyển sang Thư viện…</div>}
        </div>
      )}
    </div>
  );
}
