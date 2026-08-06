"use client";

import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { platformLabel } from "@/lib/format";
import { LICENSE_STATUS_LABEL, type LicenseStatus, type ResolveChannelResult } from "@/lib/types";

/** Các mốc chu kỳ quét cho phép chọn — theo brief, không hardcode chỗ khác. */
const SCAN_INTERVALS = [15, 60, 360, 1440];
const SCAN_INTERVAL_LABEL: Record<number, string> = {
  15: "15 phút",
  60: "1 giờ",
  360: "6 giờ",
  1440: "24 giờ",
};

const LICENSE_STATUSES: LicenseStatus[] = ["unknown", "permitted", "licensed", "open", "own"];

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

/**
 * Modal thêm kênh nguồn — tự viết bằng div overlay + Tailwind (không dùng thư
 * viện modal). Hai bước: dán URL để backend nhận diện nền tảng/handle (chỉ
 * phân tích chuỗi URL, không gọi mạng), rồi chọn chu kỳ quét + tình trạng bản
 * quyền trước khi lưu. URL không nhận diện được thì báo lỗi ngay tại modal,
 * không tự đóng.
 */
export function AddChannelModal({ onClose, onCreated }: Props) {
  const [url, setUrl] = useState("");
  const [resolved, setResolved] = useState<ResolveChannelResult | null>(null);
  const [scanInterval, setScanInterval] = useState(60);
  const [licenseStatus, setLicenseStatus] = useState<LicenseStatus>("unknown");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const resolveMutation = useMutation({
    mutationFn: (u: string) => api.resolveSourceChannel(u),
    onSuccess: (data) => {
      setResolved(data);
      setError(null);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Không nhận diện được URL kênh");
    },
  });

  const createMutation = useMutation({
    mutationFn: () => {
      if (!resolved) throw new Error("Chưa nhận diện URL");
      return api.createSourceChannel({
        platform: resolved.platform,
        external_id: resolved.external_id,
        url: resolved.url,
        handle: resolved.handle,
        scan_interval_min: scanInterval,
        license_status: licenseStatus,
      });
    },
    onSuccess: onCreated,
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Không lưu được kênh");
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-channel-title"
        className="card w-full max-w-md"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 id="add-channel-title" className="text-[15px] font-semibold">
            Thêm kênh theo dõi
          </h2>
          <button className="text-muted hover:text-fg" onClick={onClose} aria-label="Đóng">
            ✕
          </button>
        </div>

        {!resolved ? (
          <>
            <label className="mb-1.5 block text-xs text-muted" htmlFor="channel-url">
              Dán URL kênh nguồn
            </label>
            <input
              id="channel-url"
              className="input w-full"
              placeholder="https://www.douyin.com/user/MS4wLjABAAAA..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              autoFocus
            />
            {error && <p className="mt-2 text-[12px] text-err">{error}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button className="btn" onClick={onClose}>
                Huỷ
              </button>
              <button
                className="btn btn-primary"
                disabled={!url.trim() || resolveMutation.isPending}
                onClick={() => resolveMutation.mutate(url.trim())}
              >
                {resolveMutation.isPending ? "Đang nhận diện…" : "Nhận diện"}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="mb-4 rounded-lg border border-border bg-panel2 px-3 py-2.5 text-[12.5px]">
              <div>
                Nền tảng: <b>{platformLabel(resolved.platform)}</b>
              </div>
              <div>
                Handle: <b>{resolved.handle ?? "—"}</b>
              </div>
              <div className="mt-1 truncate text-[11px] text-muted">{resolved.url}</div>
            </div>

            <label className="mb-1.5 block text-xs text-muted" htmlFor="scan-interval">
              Chu kỳ quét
            </label>
            <select
              id="scan-interval"
              className="input mb-3 w-full"
              value={scanInterval}
              onChange={(e) => setScanInterval(Number(e.target.value))}
            >
              {SCAN_INTERVALS.map((v) => (
                <option key={v} value={v}>
                  {SCAN_INTERVAL_LABEL[v]}
                </option>
              ))}
            </select>

            <label className="mb-1.5 block text-xs text-muted" htmlFor="license-status">
              Tình trạng bản quyền
            </label>
            <select
              id="license-status"
              className="input w-full"
              value={licenseStatus}
              onChange={(e) => setLicenseStatus(e.target.value as LicenseStatus)}
            >
              {LICENSE_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {LICENSE_STATUS_LABEL[s]}
                </option>
              ))}
            </select>

            {licenseStatus === "unknown" && (
              <p className="mt-2 text-[11.5px] leading-snug text-warn">
                ⚠ Kênh &ldquo;Chưa rõ&rdquo; sẽ KHÔNG được xử lý tự động cho tới khi bạn xác nhận
                quyền sử dụng — đây là chốt an toàn pháp lý.
              </p>
            )}

            {error && <p className="mt-2 text-[12px] text-err">{error}</p>}

            <div className="mt-4 flex justify-end gap-2">
              <button className="btn" onClick={() => setResolved(null)}>
                ← Đổi URL
              </button>
              <button
                className="btn btn-primary"
                disabled={createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
                {createMutation.isPending ? "Đang lưu…" : "Lưu kênh"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
