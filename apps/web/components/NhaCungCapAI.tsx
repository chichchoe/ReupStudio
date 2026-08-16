"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { HopXacNhan } from "@/components/HopXacNhan";
import { TheGiaiThich } from "@/components/TheGiaiThich";
import { api, ApiError } from "@/lib/api";
import type { NhaCungCapAI as Nha } from "@/lib/types";

/**
 * Cấu hình nhiều nhà cung cấp AI cùng lúc — chỉ cần dán khoá.
 *
 * Vì sao nhiều bên chứ không một: mỗi bên mạnh một kiểu và có hạn mức riêng.
 * Gemini có bậc miễn phí và là bên duy nhất ở đây có TTS; DeepSeek dịch
 * Trung–Việt tốt vì là model Trung Quốc; OpenRouter một khoá dùng được model
 * của nhiều hãng. Dán sẵn cả bốn rồi chọn theo từng video là cách rẻ nhất.
 *
 * Khoá không bao giờ tải về đây — backend chỉ trả cờ "đã đặt hay chưa".
 */
export function NhaCungCapAI() {
  const { data = [], isLoading } = useQuery({
    queryKey: ["ai-providers"],
    queryFn: api.nhaCungCapAI,
  });

  if (isLoading) return <p className="py-6 text-center text-[13px] text-muted">Đang tải…</p>;

  return (
    <div className="grid gap-2.5">
      {data.map((nha) => (
        <TheNhaCungCap key={nha.ma} nha={nha} />
      ))}
    </div>
  );
}

function TheNhaCungCap({ nha }: { nha: Nha }) {
  const queryClient = useQueryClient();
  const [khoa, setKhoa] = useState("");
  const [baseUrl, setBaseUrl] = useState(nha.base_url);
  const [loi, setLoi] = useState<string | null>(null);
  const [models, setModels] = useState<string[] | null>(null);
  //: Gỡ khoá cũng phải hỏi: khoá đã lưu thì không đọc lại được, gỡ nhầm là
  //: phải vào tận trang nhà cung cấp lấy khoá mới.
  const [hoiGo, setHoiGo] = useState(false);

  const luu = useMutation({
    mutationFn: () =>
      api.luuNhaCungCapAI(nha.ma, {
        api_key: khoa || undefined,
        base_url: baseUrl,
        enabled: true,
      }),
    onSuccess: (moi) => {
      queryClient.setQueryData(["ai-providers"], moi);
      setKhoa("");
      setLoi(null);
    },
    onError: (e) => setLoi(e instanceof ApiError ? e.message : "Không lưu được"),
  });

  const goKhoa = useMutation({
    mutationFn: () => api.goKhoaAI(nha.ma),
    onSuccess: (moi) => {
      queryClient.setQueryData(["ai-providers"], moi);
      setModels(null);
    },
  });

  // Bấm "Kiểm tra" gọi thẳng sang nhà cung cấp. Đây là cách DUY NHẤT biết khoá
  // có dùng được không mà không phải chờ tới lúc dịch — lúc đó thì đã tải và
  // nhận dạng xong cả video rồi.
  const kiemTra = useMutation({
    mutationFn: () => api.modelCuaNhaCungCap(nha.ma, "translate"),
    onSuccess: (ds) => {
      setModels(ds);
      setLoi(null);
    },
    onError: (e) => {
      setModels(null);
      setLoi(e instanceof ApiError ? e.message : "Không hỏi được danh sách model");
    },
  });

  const sanSang = nha.da_dat_khoa || !nha.can_khoa;

  return (
    <div className="rounded-xl border border-border bg-panel p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[14px] font-medium">{nha.ten}</span>
        <span
          className={`rounded-full border px-2 py-0.5 text-[10.5px] ${
            sanSang ? "border-ok/40 text-ok" : "border-border text-muted"
          }`}
        >
          {sanSang ? "sẵn sàng" : "chưa có khoá"}
        </span>
        {nha.ghi_chu && <TheGiaiThich nhan="Bên này thế nào?">{nha.ghi_chu}</TheGiaiThich>}
        {nha.trang_lay_khoa && (
          <a
            href={nha.trang_lay_khoa}
            target="_blank"
            rel="noreferrer"
            className="ml-auto text-[11.5px] text-accent hover:underline"
          >
            Lấy khoá ↗
          </a>
        )}
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        {nha.can_khoa && (
          <input
            className="input w-72 py-1"
            type="password"
            autoComplete="off"
            placeholder={nha.da_dat_khoa ? "để trống = giữ khoá đang dùng" : "dán khoá API vào đây"}
            value={khoa}
            onChange={(e) => setKhoa(e.target.value)}
          />
        )}
        {/* Lời nhắc về địa chỉ gốc nằm NGAY TRONG ô nó nói về, không phải một
            dòng chữ lặp y hệt dưới cả sáu thẻ nhà cung cấp. */}
        <input
          className="input w-64 py-1"
          placeholder={nha.base_url_mac_dinh}
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          aria-label={`Địa chỉ gốc của ${nha.ten}`}
          title="Để trống là dùng địa chỉ mặc định — chỉ điền khi chạy qua proxy hoặc bản tự dựng."
        />
        <button
          className="btn btn-primary btn-sm"
          disabled={luu.isPending}
          onClick={() => luu.mutate()}
        >
          {luu.isPending ? "Đang lưu…" : "Lưu"}
        </button>
        {sanSang && (
          <button
            className="btn btn-sm"
            disabled={kiemTra.isPending}
            onClick={() => kiemTra.mutate()}
          >
            {kiemTra.isPending ? "Đang hỏi…" : "Kiểm tra khoá"}
          </button>
        )}
        {nha.da_dat_khoa && (
          <button
            className="btn btn-sm text-err"
            disabled={goKhoa.isPending}
            onClick={() => setHoiGo(true)}
          >
            Gỡ khoá
          </button>
        )}
      </div>

      {hoiGo && (
        <HopXacNhan
          tieuDe={`Gỡ khoá ${nha.ten}?`}
          moTa={
            <>
              Khoá đã lưu không đọc lại được, nên gỡ xong phải vào tận trang {nha.ten} lấy khoá
              mới. Video đang dịch dở bằng bên này sẽ lỗi ở lượt gọi tiếp theo.
            </>
          }
          nhanXacNhan="Gỡ khoá"
          dangChay={goKhoa.isPending}
          onXacNhan={() => {
            goKhoa.mutate();
            setHoiGo(false);
          }}
          onHuy={() => setHoiGo(false)}
        />
      )}

      {models && (
        <div className="mt-2 rounded-lg border border-ok/25 bg-ok/[0.06] p-2 text-[11.5px]">
          Khoá dùng được · <b>{models.length}</b> model hợp cho dịch:{" "}
          {models.slice(0, 5).join(", ")}
          {models.length > 5 && "…"}
        </div>
      )}

      {loi && (
        <div className="mt-2 rounded-lg border border-err/25 bg-err/[0.08] p-2 text-[11.5px] text-err">
          {loi}
        </div>
      )}
    </div>
  );
}
