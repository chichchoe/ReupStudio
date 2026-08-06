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

export default function SourcesPage() {
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
    <div className="max-w-4xl">
      <header className="mb-5">
        <h1 className="text-xl font-semibold">Nguồn Trung Quốc</h1>
        <p className="text-[13px] text-muted mt-0.5">
          Douyin · Bilibili · Kuaishou · Xiaohongshu · Weibo
        </p>
      </header>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={6}
        placeholder={`https://v.douyin.com/iRxxxx/
https://www.bilibili.com/video/BV1xx411c7mD

Mỗi dòng một link — hỗ trợ link rút gọn và link có tham số share`}
        className="input w-full font-mono text-[12.5px] resize-y"
      />

      <div className="flex items-center gap-3 mt-3 flex-wrap">
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
        <div className="mt-4 text-[12.5px] text-err bg-err/[0.08] border border-err/25 rounded-lg p-3">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-4 text-[12.5px] bg-accent/[0.07] border border-accent/25 rounded-lg p-3 text-[#B8C6E8]">
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

      <div className="mt-8 card text-[12.5px] text-muted">
        <b className="text-fg">Chặng tiếp theo</b>
        <ul className="mt-2 space-y-1 list-disc list-inside">
          <li>M2 — theo dõi kênh nguồn tự động, chống trùng bằng pHash</li>
          <li>M3 — xoá watermark Douyin và phụ đề cứng tiếng Trung</li>
          <li>M4 — chuẩn hoá 9:16, hook 3 giây, chia tập theo nền tảng</li>
          <li>M5 — đăng thẳng lên TikTok / YouTube Shorts / Reels</li>
        </ul>
      </div>
    </div>
  );
}
