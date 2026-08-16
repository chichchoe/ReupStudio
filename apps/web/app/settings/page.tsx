"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { NhaCungCapAI } from "@/components/NhaCungCapAI";
import { TheGiaiThich } from "@/components/TheGiaiThich";
import type { MucCauHinh, MucKiemTra } from "@/lib/types";

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
const MUC_ENV = "Cài đặt";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [sua, setSua] = useState<Record<string, string>>({});
  const [loi, setLoi] = useState<string | null>(null);
  const [daLuu, setDaLuu] = useState(false);
  const [khoaMoi, setKhoaMoi] = useState<{ khoa: string; huong_dan: string } | null>(null);
  const [daCaiDat, setDaCaiDat] = useState<string[] | null>(null);
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

  //: Chỉ hỏi khi đang mở mục Cài đặt — mỗi lần hỏi là một loạt kiểm tra thật
  //: (ping worker, gọi ffmpeg), không đáng chạy nền suốt cả phiên.
  const { data: may, refetch: hoiLaiMay } = useQuery({
    queryKey: ["thong-tin-may"],
    queryFn: api.thongTinMay,
    enabled: dangXem === MUC_ENV,
  });

  const caiDat = useMutation({
    mutationFn: api.caiDatNhanh,
    onSuccess: (kq) => {
      setDaCaiDat(kq.da_lam);
      hoiLaiMay();
      queryClient.invalidateQueries({ queryKey: ["cau-hinh"] });
    },
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
                  <h2 className="text-[15px] font-semibold">Cài đặt máy này</h2>
                  <TheGiaiThich nhan="Chuyển sang máy khác thì làm gì?">
                    Chép cả thư mục dự án sang máy mới, dựng PostgreSQL và Redis, rồi mở trang
                    này bấm <b className="text-fg">Cài đặt nhanh</b>. Nó tạo thư mục media,
                    sinh khoá mã hoá và chạy migration. Những thứ phải cài bằng tay (FFmpeg,
                    Docker) thì hiện lệnh sẵn để dán.
                  </TheGiaiThich>
                </div>

                {may && (
                  <>
                    <div className="mb-3 grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-xl border border-border bg-panel p-3.5 text-[12px]">
                      <ThongSo nhan="Máy" giaTri={may.ten_may} />
                      <ThongSo nhan="Hệ điều hành" giaTri={`${may.he_dieu_hanh} · ${may.kien_truc}`} />
                      <ThongSo nhan="Python" giaTri={may.python} />
                      <ThongSo nhan="Ổ đĩa còn trống" giaTri={`${may.dung_luong_trong_gb} GB`} />
                      <ThongSo nhan="Thư mục dự án" giaTri={may.thu_muc_du_an} rong />
                      <ThongSo nhan="Thư mục media" giaTri={may.thu_muc_media} rong />
                    </div>

                    <div className="rounded-xl border border-border bg-panel">
                      {may.muc.map((m, i) => (
                        <DongKiemTra key={m.ma} muc={m} dauTien={i === 0} />
                      ))}
                    </div>

                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button
                        className="btn btn-primary"
                        disabled={caiDat.isPending}
                        onClick={() => caiDat.mutate()}
                      >
                        {caiDat.isPending ? "Đang cài…" : "⚡ Cài đặt nhanh cho máy này"}
                      </button>
                      <button className="btn btn-sm" onClick={() => hoiLaiMay()}>
                        Kiểm tra lại
                      </button>
                      <button
                        className="btn btn-sm ml-auto"
                        disabled={sinhKhoa.isPending}
                        onClick={() => sinhKhoa.mutate()}
                      >
                        Sinh khoá mã hoá mới
                      </button>
                    </div>

                    {daCaiDat && (
                      <ul className="mt-3 rounded-lg border border-ok/25 bg-ok/[0.06] p-3 text-[12.5px]">
                        {daCaiDat.map((v) => (
                          <li key={v} className="py-0.5">
                            ✓ {v}
                          </li>
                        ))}
                      </ul>
                    )}

                    {khoaMoi && (
                      <div className="mt-3 rounded-lg border border-warn/30 bg-warn/[0.07] p-2.5 text-[12px]">
                        <code className="block break-all font-mono text-[11.5px]">
                          {khoaMoi.khoa}
                        </code>
                        <p className="mt-1.5 text-warn">{khoaMoi.huong_dan}</p>
                      </div>
                    )}

                    <p className="mt-3 text-[11.5px] text-muted">
                      Ba biến <code>{data.khoa_bootstrap.join("</code>, <code>")}</code> phải nằm
                      trong <code>.env</code> vì chúng cần <em>trước</em> khi chạm được database.
                    </p>
                  </>
                )}
              </>
            )}

            {nhomDangXem && (
              <>
                <h2 className="mb-3 text-[15px] font-semibold">{nhomDangXem.ten}</h2>
                {/* Sáu chặng pipeline nằm chung một mục, phân cách bằng tiêu đề
                    nhỏ. Tách thành sáu mục riêng thì mỗi mục chỉ 2–5 ô và sửa
                    một video là phải nhảy qua bốn mục; dồn thành một danh sách
                    phẳng 22 ô thì lại không biết ô nào thuộc bước nào. */}
                <div className="rounded-xl border border-border bg-panel">
                  {nhomDangXem.muc.map((muc, i) => {
                    const phanMoi = muc.phan && muc.phan !== nhomDangXem.muc[i - 1]?.phan;
                    return (
                      <div key={muc.key}>
                        {phanMoi && (
                          <div
                            className={clsx(
                              "bg-panel2/60 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted",
                              i > 0 && "border-t border-border",
                            )}
                          >
                            {muc.phan}
                          </div>
                        )}
                        <Dong
                          muc={muc}
                          dauTien={i === 0 || Boolean(phanMoi)}
                          giaTri={sua[muc.key]}
                          onDoi={(v) => setSua((cu) => ({ ...cu, [muc.key]: v }))}
                        />
                      </div>
                    );
                  })}
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

function ThongSo({ nhan, giaTri, rong }: { nhan: string; giaTri: string; rong?: boolean }) {
  return (
    <div className={clsx("flex gap-2", rong && "col-span-2")}>
      <span className="w-[7.5rem] shrink-0 text-muted">{nhan}</span>
      <span className="min-w-0 truncate font-mono text-[11.5px]" title={giaTri}>
        {giaTri}
      </span>
    </div>
  );
}

/**
 * Một mục trong danh sách kiểm.
 *
 * Mục hỏng phải nói NGAY cách sửa ở cùng chỗ. Bắt người dùng đọc "FFmpeg:
 * thiếu" rồi tự đi tra lệnh cài là để họ dừng lại giữa chừng.
 */
function DongKiemTra({ muc, dauTien }: { muc: MucKiemTra; dauTien: boolean }) {
  return (
    <div className={clsx("flex gap-3 p-3", dauTien || "border-t border-border")}>
      <span
        className={clsx("mt-[3px] h-2 w-2 shrink-0 rounded-full", muc.ok ? "bg-ok" : "bg-err")}
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12.5px] font-medium">{muc.ten}</span>
          {!muc.ok && muc.tu_sua_duoc && (
            <span className="rounded-full border border-accent/40 px-2 py-0.5 text-[10.5px] text-accent">
              nút bấm tự sửa được
            </span>
          )}
        </div>
        <div className="mt-0.5 break-words text-[11.5px] text-muted">{muc.chi_tiet}</div>
        {!muc.ok && muc.cach_sua && (
          <div className="mt-1 rounded bg-bg px-2 py-1 font-mono text-[11px] text-[#E8D4A8]">
            {muc.cach_sua}
          </div>
        )}
      </div>
    </div>
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
