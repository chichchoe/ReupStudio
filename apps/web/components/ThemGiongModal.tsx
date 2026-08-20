"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";

const NGUON = [
  { ma: "tu_thu", nhan: "Tôi tự thu", goi_y: "Thu 10–15 giây bằng điện thoại, phòng yên, không nhạc nền." },
  { ma: "cat_tu_file", nhan: "Cắt từ file có sẵn", goi_y: "Chọn đoạn 10–15 giây trong file audio/video bạn có quyền dùng." },
  { ma: "thue_doc", nhan: "Thuê người đọc", goi_y: "Tải lên file người đọc gửi. Trả tiền một lần, dùng cho mọi video." },
  { ma: "tam_tu_may", nhan: "Giọng tạm dựng bằng máy", goi_y: "Chạy được ngay, nhưng là giọng máy — nên thay bằng giọng thật khi có điều kiện." },
];

interface Props {
  onDong: () => void;
  onXong: () => void;
}

/**
 * Thêm một giọng vào thư viện.
 *
 * KHÔNG hỏi người dùng phần chữ của đoạn mẫu: Whisper tự gõ ở bước sau, người
 * dùng chỉ việc sửa lại nếu lệch. Bắt gõ tay 15 giây lời nói là việc nản nhất
 * của cả luồng.
 */
export function ThemGiongModal({ onDong, onXong }: Props) {
  const [ten, setTen] = useState("");
  const [nguon, setNguon] = useState("tu_thu");
  const [file, setFile] = useState<File | null>(null);
  const [tu, setTu] = useState("");
  const [den, setDen] = useState("");

  const canFile = nguon !== "tam_tu_may";
  const coCat = nguon === "cat_tu_file";

  const them = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("ten", ten);
      form.append("nguon", nguon);
      form.append("nha_cung_cap", "fish_mlx");
      if (file) form.append("file", file);
      if (coCat && tu) form.append("cat_tu_giay", tu);
      if (coCat && den) form.append("cat_den_giay", den);
      return api.themGiong(form);
    },
    onSuccess: onXong,
  });

  const duocGui = ten.trim().length > 0 && (!canFile || file !== null) && !them.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-xl border border-border bg-panel p-4">
        <h3 className="mb-3 text-[15px] font-semibold">Thêm giọng</h3>

        <label className="mb-1 block text-[12px] text-muted">Tên giọng</label>
        <input
          className="mb-3 w-full rounded border border-border bg-bg px-2 py-1.5 text-[13px] outline-none focus:border-accent"
          value={ten}
          onChange={(e) => setTen(e.target.value)}
          placeholder="Giọng tôi"
        />

        <label className="mb-1 block text-[12px] text-muted">Nguồn giọng</label>
        <div className="mb-3 space-y-1.5">
          {NGUON.map((n) => (
            <label key={n.ma} className="flex cursor-pointer items-start gap-2 text-[12.5px]">
              <input
                type="radio"
                className="mt-1"
                checked={nguon === n.ma}
                onChange={() => setNguon(n.ma)}
              />
              <span>
                <span className="font-medium">{n.nhan}</span>
                <span className="block text-[11.5px] text-muted">{n.goi_y}</span>
              </span>
            </label>
          ))}
        </div>

        {canFile && (
          <>
            <label className="mb-1 block text-[12px] text-muted">File âm thanh hoặc video</label>
            <input
              type="file"
              accept="audio/*,video/*"
              className="mb-3 w-full text-[12px]"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </>
        )}

        {coCat && (
          <div className="mb-3 flex items-center gap-2 text-[12px]">
            <span className="text-muted">Lấy từ giây</span>
            <input
              className="w-20 rounded border border-border bg-bg px-2 py-1 outline-none focus:border-accent"
              value={tu}
              onChange={(e) => setTu(e.target.value)}
              placeholder="12.5"
            />
            <span className="text-muted">đến giây</span>
            <input
              className="w-20 rounded border border-border bg-bg px-2 py-1 outline-none focus:border-accent"
              value={den}
              onChange={(e) => setDen(e.target.value)}
              placeholder="26"
            />
          </div>
        )}

        <p className="mb-3 text-[11.5px] text-muted">
          Sau khi tải lên, hệ thống tự cắt còn tối đa 15 giây, cân âm lượng, rồi dùng Whisper gõ
          lại phần chữ cho bạn sửa. Chất lượng lồng tiếng không bao giờ vượt được chất lượng đoạn
          mẫu — nên mẫu thu người thật luôn hơn hẳn giọng máy.
        </p>

        {them.isError && (
          <div className="mb-2 text-[12px] text-err">
            {them.error instanceof ApiError ? them.error.message : "Không thêm được giọng"}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button className="btn btn-sm" onClick={onDong}>
            Huỷ
          </button>
          <button
            className="btn btn-primary btn-sm"
            disabled={!duocGui}
            onClick={() => them.mutate()}
          >
            {them.isPending ? "Đang gửi…" : "Thêm giọng"}
          </button>
        </div>
      </div>
    </div>
  );
}
