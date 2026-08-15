"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { AddChannelModal } from "@/components/AddChannelModal";
import { HopXacNhan } from "@/components/HopXacNhan";
import { LicenseStatusBadge } from "@/components/LicenseStatusBadge";
import { api } from "@/lib/api";
import { platformLabel } from "@/lib/format";
import type { SourceChannel } from "@/lib/types";

/** Khớp mốc chọn ở `AddChannelModal` — dùng chung để hiển thị nhất quán. */
const SCAN_INTERVAL_LABEL: Record<number, string> = {
  15: "15 phút",
  60: "1 giờ",
  360: "6 giờ",
  1440: "24 giờ",
};

/** Tab "Kênh theo dõi" ở trang Nguồn: bảng kênh + nút mở modal thêm kênh. */
export function ChannelsTab() {
  const [showModal, setShowModal] = useState(false);
  const queryClient = useQueryClient();

  const { data: channels, isLoading } = useQuery({
    queryKey: ["source-channels"],
    queryFn: api.listSourceChannels,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.updateSourceChannel(id, { enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["source-channels"] }),
  });

  const xoaMutation = useMutation({
    mutationFn: (id: string) => api.deleteSourceChannel(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["source-channels"] }),
  });

  //: Kênh đang chờ xác nhận xoá. Giữ cả object để hộp hỏi lại gọi đúng tên
  //: kênh — "Xoá kênh này?" không nói được là kênh nào khi bảng có chục dòng.
  const [xoaKenh, setXoaKenh] = useState<SourceChannel | null>(null);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[13px] text-muted">
          {channels ? `${channels.length} kênh` : "đang tải…"}
        </p>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          + Thêm kênh
        </button>
      </div>

      {isLoading && <p className="py-8 text-center text-[13px] text-muted">Đang tải…</p>}

      {!isLoading && (channels?.length ?? 0) === 0 && (
        <div className="py-16 text-center text-[13px] text-muted">
          Chưa theo dõi kênh nào. Bấm “Thêm kênh” để bắt đầu.
        </div>
      )}

      {channels && channels.length > 0 && (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="border-b border-border text-left text-muted">
                <th className="px-3 py-2.5 font-medium">Kênh</th>
                <th className="px-3 py-2.5 font-medium">Nền tảng</th>
                <th className="px-3 py-2.5 font-medium">Chu kỳ quét</th>
                <th className="px-3 py-2.5 font-medium">Tình trạng bản quyền</th>
                <th className="px-3 py-2.5 text-right font-medium">Bật/tắt</th>
                <th className="px-3 py-2.5 text-right font-medium" />
              </tr>
            </thead>
            <tbody>
              {channels.map((c) => (
                <tr key={c.id} className="border-b border-border align-top last:border-0">
                  <td className="px-3 py-2.5">
                    <div className="font-medium">
                      {c.handle ?? c.display_name ?? c.external_id}
                    </div>
                    <div className="max-w-[220px] truncate text-[11px] text-muted">{c.url}</div>
                  </td>
                  <td className="px-3 py-2.5">{platformLabel(c.platform)}</td>
                  <td className="px-3 py-2.5">
                    {SCAN_INTERVAL_LABEL[c.scan_interval_min] ?? `${c.scan_interval_min} phút`}
                  </td>
                  <td className="px-3 py-2.5">
                    <LicenseStatusBadge status={c.license_status} />
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <button
                      className={clsx("btn btn-sm", !c.enabled && "opacity-50")}
                      disabled={toggleMutation.isPending}
                      onClick={() => toggleMutation.mutate({ id: c.id, enabled: !c.enabled })}
                    >
                      {c.enabled ? "Đang bật" : "Đang tắt"}
                    </button>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <button
                      className="btn btn-sm border-err/35 text-err"
                      onClick={() => setXoaKenh(c)}
                    >
                      Xoá
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {xoaKenh && (
        <HopXacNhan
          tieuDe="Xoá kênh theo dõi?"
          moTa={
            <>
              <b className="text-fg">{xoaKenh.handle ?? xoaKenh.display_name ?? xoaKenh.external_id}</b>{" "}
              sẽ không được quét nữa. Video đã tải về từ kênh này vẫn giữ nguyên.
              <br />
              Thêm lại phải dán URL và chọn lại chu kỳ quét, tình trạng bản quyền.
            </>
          }
          dangChay={xoaMutation.isPending}
          onXacNhan={() => {
            xoaMutation.mutate(xoaKenh.id);
            setXoaKenh(null);
          }}
          onHuy={() => setXoaKenh(null)}
        />
      )}

      {showModal && (
        <AddChannelModal
          onClose={() => setShowModal(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["source-channels"] });
            setShowModal(false);
          }}
        />
      )}
    </div>
  );
}
