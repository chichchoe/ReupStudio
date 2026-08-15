"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { CreateFromLinksResult } from "@/lib/types";

/**
 * Văn phong dịch — không còn ô chọn trên giao diện. Giữ đúng giá trị mà ô đó
 * vẫn mặc định, để video thêm từ nay dịch y hệt video đã thêm trước; bỏ hẳn
 * thì worker rơi về "doi_thuong" và giọng dịch đổi mà không ai biết.
 */
const VAN_PHONG_MAC_DINH = "ngon_tinh";

/** Ô dán link ở trang Video: dán nhiều link, gửi thẳng vào hàng đợi. */
export function PasteLinksForm() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<CreateFromLinksResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (urls: string[]) => api.createFromLinks(urls, { tone: VAN_PHONG_MAC_DINH }),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      setText("");
      queryClient.invalidateQueries({ queryKey: ["videos"] });
      queryClient.invalidateQueries({ queryKey: ["counts"] });
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

      <div className="mt-3 flex flex-wrap items-center gap-3">
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
          {/* `invalid` có giá trị mặc định ở backend nên OpenAPI đánh dấu là tuỳ
              chọn — thực tế luôn có, nhưng vẫn phải chịu được khi vắng. */}
          {(result.invalid?.length ?? 0) > 0 && (
            <div className="mt-1.5 text-warn">
              {result.invalid?.length} link không nhận diện được: {result.invalid?.[0]}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
