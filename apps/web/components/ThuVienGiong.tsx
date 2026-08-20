"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { ThemGiongModal } from "@/components/ThemGiongModal";
import { api } from "@/lib/api";
import type { GiongThuVien } from "@/lib/types";

const NHAN_NGUON: Record<string, string> = {
  dung_san: "dựng sẵn",
  tu_thu: "tự thu",
  cat_tu_file: "cắt từ file",
  thue_doc: "thuê đọc",
  tam_tu_may: "giọng tạm",
};

/**
 * Thư viện giọng — mọi giọng ở MỘT chỗ, dựng sẵn lẫn clone.
 *
 * Vì sao gộp: trước đây ba nhóm giọng cứng trong ba dropdown chọn tuần tự.
 * Thêm giọng clone vào khuôn đó là thêm tầng thứ tư. Gộp lại thì thêm giọng
 * chỉ là thêm một dòng trong bảng.
 *
 * Mọi thẻ đều nghe thử CÙNG MỘT CÂU — bấm lần lượt là so được ngay.
 */
export function ThuVienGiong() {
  const queryClient = useQueryClient();
  const [themMoi, setThemMoi] = useState(false);

  const { data: giong = [], isLoading } = useQuery({
    queryKey: ["giong-doc"],
    queryFn: api.giongDoc,
    //: Giọng đang dựng thì hỏi lại vài giây một lần cho tới khi xong. Đây
    //: KHÔNG phải polling tiến trình pipeline (thứ đã có WebSocket) mà là một
    //: việc ngắn, chỉ chạy khi đúng thẻ đó đang xử lý.
    refetchInterval: (q) =>
      (q.state.data ?? []).some((g) => g.trang_thai === "dang_xu_ly") ? 3000 : false,
  });

  const lam_moi = () => queryClient.invalidateQueries({ queryKey: ["giong-doc"] });

  const datMacDinh = useMutation({
    mutationFn: (id: string) => api.suaGiong(id, { mac_dinh: true }),
    onSuccess: lam_moi,
  });
  const xoa = useMutation({ mutationFn: api.xoaGiong, onSuccess: lam_moi });
  const docLai = useMutation({ mutationFn: api.docLaiGiong, onSuccess: lam_moi });

  if (isLoading) return <p className="py-8 text-center text-[13px] text-muted">Đang tải…</p>;

  return (
    <div>
      {giong.map((g) => (
        <div key={g.id} className="mb-2 rounded-xl border border-border bg-panel p-3">
          <div className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                {g.mac_dinh && <span className="text-accent" title="giọng mặc định">●</span>}
                <span className="truncate text-[13.5px] font-medium">{g.ten}</span>
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11.5px] text-muted">
                <span>{NHAN_NGUON[g.nguon] ?? g.nguon}</span>
                <span className="opacity-40">·</span>
                <span className="font-mono">{g.nha_cung_cap}</span>
                {g.nha_cung_cap === "fish_mlx" && (
                  //: Fish Audio Research License — thương mại phải mua phép
                  //: riêng. Giấu đi là để người dùng vi phạm mà không biết.
                  <>
                    <span className="opacity-40">·</span>
                    <span className="text-warn">chạy tại máy · phi thương mại</span>
                  </>
                )}
              </div>
              {g.trang_thai === "dang_xu_ly" && (
                <div className="mt-1 text-[11px] text-run">Đang dựng giọng…</div>
              )}
              {g.trang_thai === "hong" && (
                <div className="mt-1 text-[11px] text-err">Dựng hỏng: {g.loi}</div>
              )}
              {g.canh_bao?.map((c) => (
                <div key={c.ma} className="mt-1 text-[11px] text-warn">
                  ⚠ {c.thong_diep}
                </div>
              ))}
            </div>

            <div className="flex shrink-0 items-center gap-1.5">
              {/* Hiện trình phát khi ĐÃ CÓ FILE, không phải khi trạng thái
                  là san_sang: giọng seed sẵn mang san_sang nhưng chưa ai dựng
                  câu đọc thử — hiện nút ▶ rồi trả 404 thì trông như hỏng. */}
              {g.co_nghe_thu ? (
                /* eslint-disable-next-line jsx-a11y/media-has-caption -- câu đọc thử, không có phụ đề */
                <audio controls preload="none" className="h-8 w-52" src={api.ngheThuUrl(g.id)} />
              ) : (
                g.trang_thai === "san_sang" && (
                  <button
                    className="btn btn-sm"
                    disabled={docLai.isPending}
                    onClick={() => docLai.mutate(g.id)}
                  >
                    Dựng câu đọc thử
                  </button>
                )
              )}
              {!g.mac_dinh && g.trang_thai === "san_sang" && (
                <button className="btn btn-sm" onClick={() => datMacDinh.mutate(g.id)}>
                  Đặt mặc định
                </button>
              )}
              {g.nguon !== "dung_san" && (
                <button
                  className="btn btn-sm border-err/35 text-err"
                  onClick={() => xoa.mutate(g.id)}
                >
                  Xoá
                </button>
              )}
            </div>
          </div>
        </div>
      ))}

      <button className="btn btn-primary btn-sm mt-2" onClick={() => setThemMoi(true)}>
        + Thêm giọng
      </button>

      {themMoi && (
        <ThemGiongModal
          onDong={() => setThemMoi(false)}
          onXong={() => {
            setThemMoi(false);
            lam_moi();
          }}
        />
      )}
    </div>
  );
}
