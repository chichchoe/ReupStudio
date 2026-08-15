"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { NhaCungCapAI } from "@/components/NhaCungCapAI";
import type { MucCauHinh } from "@/lib/types";

/**
 * Trang Cấu hình — thay cho việc sửa tay file `.env`.
 *
 * Vì sao chuyển vào đây: `.env` nằm cạnh mã nguồn nên chỉ cần một lần
 * `git add -A` bất cẩn là khoá API lên GitHub. Chuyện đó suýt xảy ra ngày
 * 16.08.2026 và chỉ được chặn lại nhờ bộ quét bí mật của GitHub.
 *
 * Bí mật không bao giờ được tải về đây — backend trả về chuỗi che kèm cờ
 * `da_dat`. Ô để trống nghĩa là giữ nguyên, không phải xoá.
 */
export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [sua, setSua] = useState<Record<string, string>>({});
  const [loi, setLoi] = useState<string | null>(null);
  const [daLuu, setDaLuu] = useState(false);
  const [khoaMoi, setKhoaMoi] = useState<{ khoa: string; huong_dan: string } | null>(null);

  const { data, isLoading } = useQuery({ queryKey: ["cau-hinh"], queryFn: api.cauHinh });

  const luu = useMutation({
    mutationFn: () => api.luuCauHinh(sua),
    onSuccess: (moi) => {
      queryClient.setQueryData(["cau-hinh"], moi);
      // Cấu hình đổi thì model dịch và hạn mức đổi theo — kéo lại cho khớp.
      queryClient.invalidateQueries({ queryKey: ["llm-models"] });
      queryClient.invalidateQueries({ queryKey: ["llm-usage"] });
      setSua({});
      setLoi(null);
      setDaLuu(true);
      setTimeout(() => setDaLuu(false), 3000);
    },
    onError: (e) => setLoi(e instanceof ApiError ? e.message : "Không lưu được cấu hình"),
  });

  const sinhKhoa = useMutation({
    mutationFn: api.sinhKhoaMaHoa,
    onSuccess: setKhoaMoi,
  });

  const soThayDoi = Object.keys(sua).length;

  return (
    <main className="mx-auto max-w-3xl px-5 py-8">
      <h1 className="text-[22px] font-semibold">Cấu hình</h1>
      <p className="mt-1.5 max-w-[65ch] text-[13px] text-muted">
        Mọi thiết lập lưu trong database, không nằm trong file <code>.env</code> nữa — file đó
        nằm cạnh mã nguồn nên rất dễ bị đẩy nhầm lên GitHub. Khoá API được mã hoá trước khi
        lưu và không bao giờ hiện lại.
      </p>

      {isLoading && <p className="py-10 text-center text-[13px] text-muted">Đang tải…</p>}

      {data && (
        <>
          <div className="mt-5 rounded-xl border border-border bg-panel p-4">
            <div className="text-[13px] font-medium">Vẫn phải để trong .env</div>
            <p className="mt-1 text-[12px] text-muted">
              Ba biến này cần <em>trước</em> khi chạm được database nên không chuyển vào đây
              được: <code>{data.khoa_bootstrap.join("</code>, <code>")}</code>.
            </p>
            <button
              className="btn btn-sm mt-2.5"
              disabled={sinhKhoa.isPending}
              onClick={() => sinhKhoa.mutate()}
            >
              Sinh khoá mã hoá mới
            </button>
            {khoaMoi && (
              <div className="mt-2.5 rounded-lg border border-warn/30 bg-warn/[0.07] p-2.5 text-[12px]">
                <code className="block break-all font-mono text-[11.5px]">{khoaMoi.khoa}</code>
                <p className="mt-1.5 text-warn">{khoaMoi.huong_dan}</p>
              </div>
            )}
          </div>

          <section className="mt-6">
            <h2 className="mb-1 text-[15px] font-semibold">Nhà cung cấp AI</h2>
            <p className="mb-2.5 max-w-[65ch] text-[12px] text-muted">
              Dán khoá của bên nào bạn có; lúc dịch sẽ chọn bên và model. Mỗi bên mạnh một
              kiểu và có hạn mức riêng, nên dán sẵn nhiều bên rồi chọn theo từng video là
              cách rẻ nhất.
            </p>
            <NhaCungCapAI />
          </section>

          {data.nhom.map((nhom) => (
            <section key={nhom.ten} className="mt-6">
              <h2 className="mb-2 text-[15px] font-semibold">{nhom.ten}</h2>
              <div className="rounded-xl border border-border bg-panel">
                {nhom.muc.map((muc, i) => (
                  <Dong
                    key={muc.key}
                    muc={muc}
                    dauTien={i === 0}
                    giaTri={sua[muc.key]}
                    onDoi={(v) => setSua((cu) => ({ ...cu, [muc.key]: v }))}
                  />
                ))}
              </div>
            </section>
          ))}

          {loi && (
            <div className="mt-5 rounded-lg border border-err/25 bg-err/[0.08] p-3 text-[12.5px] text-err">
              {loi}
            </div>
          )}

          <div className="sticky bottom-0 mt-6 flex items-center gap-3 border-t border-border bg-bg/95 py-3 backdrop-blur">
            <button
              className="btn btn-primary"
              disabled={soThayDoi === 0 || luu.isPending}
              onClick={() => luu.mutate()}
            >
              {luu.isPending ? "Đang lưu…" : `Lưu ${soThayDoi > 0 ? `(${soThayDoi})` : ""}`}
            </button>
            {soThayDoi > 0 && (
              <button className="btn btn-sm" onClick={() => setSua({})}>
                Bỏ thay đổi
              </button>
            )}
            {daLuu && <span className="text-[12.5px] text-ok">Đã lưu và áp dụng ngay</span>}
          </div>
        </>
      )}
    </main>
  );
}

interface DongProps {
  muc: MucCauHinh;
  dauTien: boolean;
  giaTri: string | undefined;
  onDoi: (v: string) => void;
}

function Dong({ muc, dauTien, giaTri, onDoi }: DongProps) {
  // Bí mật KHÔNG đổ giá trị che vào ô nhập — người dùng sẽ tưởng đó là khoá
  // thật rồi lưu nguyên chuỗi chấm chấm đè lên khoá đang dùng.
  const hienThi = giaTri ?? (muc.is_secret ? "" : muc.value);

  return (
    <div className={`flex flex-wrap items-center gap-3 p-3 ${dauTien ? "" : "border-t border-border"}`}>
      <div className="min-w-[15rem] flex-1">
        <label htmlFor={muc.key} className="font-mono text-[12px]">
          {muc.key}
        </label>
        <div className="text-[11.5px] text-muted">{muc.mo_ta}</div>
      </div>

      <div className="flex items-center gap-2">
        {muc.is_secret && (
          <span className={`text-[11px] ${muc.da_dat ? "text-ok" : "text-muted"}`}>
            {muc.da_dat ? "đã đặt" : "chưa đặt"}
          </span>
        )}
        {muc.kieu === "select" ? (
          <select
            id={muc.key}
            className="input w-64 py-1"
            value={hienThi}
            onChange={(e) => onDoi(e.target.value)}
          >
            {(muc.lua_chon ?? []).map((v) => (
              <option key={v} value={v}>
                {v === "" ? "(không dùng)" : v}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={muc.key}
            className="input w-64 py-1"
            type={muc.is_secret ? "password" : muc.kieu === "number" ? "number" : "text"}
            step={muc.kieu === "number" ? "any" : undefined}
            value={hienThi}
            placeholder={muc.is_secret && muc.da_dat ? "để trống = giữ nguyên" : ""}
            onChange={(e) => onDoi(e.target.value)}
            autoComplete="off"
          />
        )}
      </div>
    </div>
  );
}
