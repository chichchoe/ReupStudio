"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { AddChannelModal } from "@/components/AddChannelModal";
import { LicenseStatusBadge } from "@/components/LicenseStatusBadge";
import { api } from "@/lib/api";
import { platformLabel } from "@/lib/format";

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

  //: Xoá hai nhịp: bấm lần đầu nút đổi thành "Xoá thật?", bấm lần hai mới gọi
  //: API. Kênh xoá nhầm phải dán lại URL và chọn lại chu kỳ, tình trạng bản
  //: quyền — mất nhiều hơn một cú bấm.
  const [hoiXoa, setHoiXoa] = useState<string | null>(null);

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
                      className={clsx(
                        "btn btn-sm border-err/35 text-err",
                        hoiXoa === c.id && "bg-err/15",
                      )}
                      disabled={xoaMutation.isPending}
                      onClick={() => {
                        if (hoiXoa === c.id) {
                          xoaMutation.mutate(c.id);
                          setHoiXoa(null);
                        } else {
                          setHoiXoa(c.id);
                        }
                      }}
                      onBlur={() => setHoiXoa((cu) => (cu === c.id ? null : cu))}
                    >
                      {hoiXoa === c.id ? "Xoá thật?" : "Xoá"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
