"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useMemo, useState } from "react";
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
 *
 * Bố cục: một cột mục bên trái, một mục hiện mỗi lần. Trước đây 27 ô xếp dọc
 * thành một trang cuộn dài, muốn sửa cỡ chữ phụ đề phải lăn qua toàn bộ phần
 * Whisper. Thay đổi đang chờ lưu vẫn giữ khi chuyển mục, và mục nào có ô chưa
 * lưu thì hiện chấm ở cột trái — nếu không, chuyển mục xong sẽ tưởng mình mất
 * thay đổi.
 */

/** Hai mục không đến từ API: một mục khoá AI, một mục biến `.env`. */
const MUC_KHOA_AI = "Nhà cung cấp AI";
const MUC_ENV = "Biến trong .env";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [sua, setSua] = useState<Record<string, string>>({});
  const [loi, setLoi] = useState<string | null>(null);
  const [daLuu, setDaLuu] = useState(false);
  const [khoaMoi, setKhoaMoi] = useState<{ khoa: string; huong_dan: string } | null>(null);
  const [dangXem, setDangXem] = useState(MUC_KHOA_AI);

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

  // Mục nào đang có ô chưa lưu — để chấm ở cột trái. Tính từ khoá đang sửa
  // chứ không giữ thêm state song song, tránh hai nguồn sự thật lệch nhau.
  const mucCoThayDoi = useMemo(() => {
    const ra = new Set<string>();
    for (const nhom of data?.nhom ?? []) {
      if (nhom.muc.some((m) => m.key in sua)) ra.add(nhom.ten);
    }
    return ra;
  }, [data, sua]);

  const nhomDangXem = data?.nhom.find((n) => n.ten === dangXem);

  return (
    //: `h-full` + `min-h-0` để cột phải tự cuộn. Không có nó, cả trang cuộn và
    //: cột mục bên trái trôi mất khỏi màn hình.
    <div className="flex h-full min-h-0 flex-col">
      <header className="mb-3 flex items-center gap-3">
        <h1 className="text-xl font-semibold">Cấu hình</h1>
        <TheGiaiThich nhan="Vì sao không để trong .env?">
          Mọi thiết lập lưu trong database, không nằm trong file <code>.env</code> nữa — file
          đó nằm cạnh mã nguồn nên rất dễ bị đẩy nhầm lên GitHub. Khoá API được mã hoá trước
          khi lưu và không bao giờ hiện lại.
        </TheGiaiThich>
      </header>

      {isLoading && <p className="py-10 text-center text-[13px] text-muted">Đang tải…</p>}

      {data && (
        <div className="flex min-h-0 flex-1 gap-5">
          <nav className="w-56 shrink-0 overflow-y-auto">
            <MucNav
              ten={MUC_KHOA_AI}
              dangXem={dangXem === MUC_KHOA_AI}
              onChon={() => setDangXem(MUC_KHOA_AI)}
            />
            <div className="my-2 border-t border-border" />
            {data.nhom.map((nhom) => (
              <MucNav
                key={nhom.ten}
                ten={nhom.ten}
                soO={nhom.muc.length}
                coThayDoi={mucCoThayDoi.has(nhom.ten)}
                dangXem={dangXem === nhom.ten}
                onChon={() => setDangXem(nhom.ten)}
              />
            ))}
            <div className="my-2 border-t border-border" />
            <MucNav
              ten={MUC_ENV}
              dangXem={dangXem === MUC_ENV}
              onChon={() => setDangXem(MUC_ENV)}
            />
          </nav>

          {/* CHỈ cột phải cuộn. Mục "Nhà cung cấp AI" có sáu thẻ chồng nhau,
              để cả trang cuộn thì cột mục bên trái trôi mất và không biết mình
              đang ở đâu nữa. */}
          <div className="min-w-0 flex-1 overflow-y-auto pr-1">
            {dangXem === MUC_KHOA_AI && (
              <>
                <div className="mb-3 flex items-center gap-3">
                  <h2 className="text-[15px] font-semibold">{MUC_KHOA_AI}</h2>
                  <TheGiaiThich nhan="Nên dán mấy bên?">
                    Dán khoá của bên nào bạn có; lúc dịch sẽ chọn bên và model. Mỗi bên mạnh
                    một kiểu và có hạn mức riêng, nên dán sẵn nhiều bên rồi chọn theo từng
                    video là cách rẻ nhất.
                  </TheGiaiThich>
                </div>
                <NhaCungCapAI />
              </>
            )}

            {dangXem === MUC_ENV && (
              <>
                <div className="mb-3 flex items-center gap-3">
                  <h2 className="text-[15px] font-semibold">{MUC_ENV}</h2>
                  <TheGiaiThich nhan="Vì sao ba biến này ở ngoài?">
                    Ba biến này cần <em>trước</em> khi chạm được database nên không chuyển
                    vào đây được. Sửa chúng trong file <code>.env</code> rồi khởi động lại API.
                  </TheGiaiThich>
                </div>
                <div className="rounded-xl border border-border bg-panel p-4">
                  <ul className="font-mono text-[12px]">
                    {data.khoa_bootstrap.map((k) => (
                      <li key={k} className="border-b border-border py-1.5 last:border-0">
                        {k}
                      </li>
                    ))}
                  </ul>
                  <button
                    className="btn btn-sm mt-3"
                    disabled={sinhKhoa.isPending}
                    onClick={() => sinhKhoa.mutate()}
                  >
                    Sinh khoá mã hoá mới
                  </button>
                  {khoaMoi && (
                    <div className="mt-2.5 rounded-lg border border-warn/30 bg-warn/[0.07] p-2.5 text-[12px]">
                      <code className="block break-all font-mono text-[11.5px]">
                        {khoaMoi.khoa}
                      </code>
                      <p className="mt-1.5 text-warn">{khoaMoi.huong_dan}</p>
                    </div>
                  )}
                </div>
              </>
            )}

            {nhomDangXem && (
              <>
                <h2 className="mb-3 text-[15px] font-semibold">{nhomDangXem.ten}</h2>
                <div className="rounded-xl border border-border bg-panel">
                  {nhomDangXem.muc.map((muc, i) => (
                    <Dong
                      key={muc.key}
                      muc={muc}
                      dauTien={i === 0}
                      giaTri={sua[muc.key]}
                      onDoi={(v) => setSua((cu) => ({ ...cu, [muc.key]: v }))}
                    />
                  ))}
                </div>
              </>
            )}

            {loi && (
              <div className="mt-4 rounded-lg border border-err/25 bg-err/[0.08] p-3 text-[12.5px] text-err">
                {loi}
              </div>
            )}

            {/* Thanh lưu chỉ hiện khi có thay đổi — mục Nhà cung cấp AI tự lưu
                riêng nên một nút "Lưu" mờ nằm đó chỉ gây phân vân. */}
            {(soThayDoi > 0 || daLuu) && (
              <div className="sticky bottom-0 mt-5 flex items-center gap-3 border-t border-border bg-bg/95 py-3 backdrop-blur">
                <button
                  className="btn btn-primary"
                  disabled={soThayDoi === 0 || luu.isPending}
                  onClick={() => luu.mutate()}
                >
                  {luu.isPending ? "Đang lưu…" : `Lưu ${soThayDoi} thay đổi`}
                </button>
                {soThayDoi > 0 && (
                  <button className="btn btn-sm" onClick={() => setSua({})}>
                    Bỏ thay đổi
                  </button>
                )}
                {daLuu && <span className="text-[12.5px] text-ok">Đã lưu và áp dụng ngay</span>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Đoạn giải thích thu lại thành một thẻ nhỏ, bấm mới mở.
 *
 * Mấy đoạn này chỉ cần đọc MỘT lần — lần đầu vào trang. Để nguyên dạng đoạn
 * văn thì lần thứ hai mươi vào sửa cỡ chữ phụ đề vẫn phải lướt qua chúng.
 */
function TheGiaiThich({ nhan, children }: { nhan: string; children: React.ReactNode }) {
  const [mo, setMo] = useState(false);

  return (
    <span className="relative">
      <button
        className={clsx(
          "rounded-full border px-2.5 py-[3px] text-[11.5px] transition-colors",
          mo
            ? "border-accent/45 bg-accent/15 text-fg"
            : "border-border bg-panel text-muted hover:text-fg",
        )}
        onClick={() => setMo((v) => !v)}
        aria-expanded={mo}
      >
        ⓘ {nhan}
      </button>
      {mo && (
        <span className="absolute left-0 top-[calc(100%+6px)] z-20 block w-[46ch] rounded-lg border border-border bg-panel2 p-3 text-[12.5px] leading-relaxed text-muted shadow-lg">
          {children}
        </span>
      )}
    </span>
  );
}

interface MucNavProps {
  ten: string;
  soO?: number;
  coThayDoi?: boolean;
  dangXem: boolean;
  onChon: () => void;
}

function MucNav({ ten, soO, coThayDoi, dangXem, onChon }: MucNavProps) {
  return (
    //: Mục đang chọn phải NHÌN LÀ BIẾT: nền mờ không đủ, thêm vạch màu bên
    //: trái và mũi tên bên phải — giống hệt cách sidebar chính đánh dấu trang
    //: đang mở, nên không phải học thêm quy ước mới.
    <button
      onClick={onChon}
      aria-current={dangXem ? "true" : undefined}
      className={clsx(
        "flex w-full items-center gap-2 rounded-lg border-l-2 px-3 py-[7px] text-left text-[13px] transition-colors",
        dangXem
          ? "border-accent bg-accent/12 font-medium text-fg"
          : "border-transparent text-muted hover:bg-panel2 hover:text-fg",
      )}
    >
      <span className="flex-1 truncate">{ten}</span>
      {coThayDoi ? (
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" title="có thay đổi chưa lưu" />
      ) : (
        soO != null && <span className="shrink-0 text-[11px] text-muted/70">{soO}</span>
      )}
      <span className={clsx("shrink-0 text-[11px]", dangXem ? "text-accent" : "text-transparent")}>
        ›
      </span>
    </button>
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
  const daSua = giaTri !== undefined;

  return (
    <div
      className={clsx(
        "flex flex-wrap items-center gap-3 p-3",
        dauTien || "border-t border-border",
        daSua && "bg-accent/[0.06]",
      )}
    >
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
