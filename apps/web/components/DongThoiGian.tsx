"use client";

import clsx from "clsx";
import { useEffect, useMemo, useRef } from "react";
import {
  biEpNhanh,
  coTran,
  daiGiongSauEp,
  nhanGiay,
  pxSangGiay,
  viTriKhoi,
  type CapDoiChieu,
} from "@/lib/dongThoiGian";

/** Các mức phóng to, pixel mỗi giây. Bấm +/− nhảy giữa các mức này. */
const MUC_PHONG = [4, 8, 16, 32, 64, 128];

/** Cao của một lớp. Đủ đọc được chữ trong khối mà không chiếm hết màn hình. */
const CAO_LOP = 34;

interface Props {
  cues: CapDoiChieu[];
  /** Tổng thời lượng video, giây — để thước kẻ hết chiều dài. */
  tongGiay: number;
  giayHienTai: number;
  /** Chỉ số MẢNG của câu đang chọn, -1 nếu chưa chọn. */
  dangChon: number;
  mucPhong: number;
  /** Chữ người dùng đang gõ chưa lưu, hiện ngay trên khối. */
  dangSua?: Record<number, string>;
  onChonCau: (viTri: number) => void;
  onTuaToi: (giay: number) => void;
  onDoiMucPhong: (px: number) => void;
}

/**
 * Dòng thời gian hai lớp cho màn duyệt bản dịch.
 *
 * Vì sao cần: danh sách chữ không bao giờ cho thấy chuyện tiếng Việt dài hơn
 * tiếng Trung. Đo trên video thật ngày 2026-08-20 — 53/80 câu phải đọc ở tốc
 * độ tối đa 1,5 lần, và 33/80 VẪN tràn sang câu sau. Người duyệt không thấy
 * gì cho tới khi render xong và mở lên nghe.
 *
 * Hai lớp:
 * - **Phụ đề**: mỗi câu một khối, bề rộng đúng bằng thời lượng cue.
 * - **Giọng**: độ dài THẬT của file giọng sau khi ép nhanh, xếp từ đúng lúc
 *   câu bắt đầu. Đỏ khi tràn, vàng khi phải ép tới trần.
 */
export function DongThoiGian({
  cues,
  tongGiay,
  giayHienTai,
  dangChon,
  mucPhong,
  dangSua,
  onChonCau,
  onTuaToi,
  onDoiMucPhong,
}: Props) {
  const khung = useRef<HTMLDivElement>(null);
  const rongTong = Math.max(tongGiay, 1) * mucPhong;

  //: Mốc thước: chọn bước sao cho hai mốc cách nhau ít nhất 80px, nếu không
  //: chữ chồng lên nhau khi thu nhỏ.
  const buocMoc = useMemo(() => {
    for (const b of [1, 2, 5, 10, 15, 30, 60, 120, 300]) {
      if (b * mucPhong >= 80) return b;
    }
    return 600;
  }, [mucPhong]);

  const moc = useMemo(() => {
    const ra: number[] = [];
    for (let g = 0; g <= tongGiay; g += buocMoc) ra.push(g);
    return ra;
  }, [tongGiay, buocMoc]);

  //: Cuộn theo con trỏ phát, nhưng chỉ khi nó sắp ra khỏi tầm nhìn — cuộn mỗi
  //: khung hình thì dòng thời gian rung liên tục và không bấm được vào đâu.
  useEffect(() => {
    const el = khung.current;
    if (!el) return;
    const x = giayHienTai * mucPhong;
    const trai = el.scrollLeft;
    const phai = trai + el.clientWidth;
    if (x < trai + 40 || x > phai - 120) {
      el.scrollLeft = Math.max(0, x - el.clientWidth / 3);
    }
  }, [giayHienTai, mucPhong]);

  const bamVaoNen = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = khung.current;
    if (!el) return;
    const x = e.clientX - el.getBoundingClientRect().left + el.scrollLeft;
    onTuaToi(pxSangGiay(x, mucPhong));
  };

  const chiSoMuc = MUC_PHONG.indexOf(mucPhong);

  return (
    <div className="flex flex-col border-t border-border bg-panel">
      <div className="flex items-center gap-2 px-3 py-1.5 text-[11.5px] text-muted">
        <span className="font-mono text-fg">{nhanGiay(giayHienTai)}</span>
        <span className="opacity-40">/</span>
        <span className="font-mono">{nhanGiay(tongGiay)}</span>

        <span className="ml-auto flex items-center gap-1">
          <button
            className="btn btn-sm px-2"
            disabled={chiSoMuc <= 0}
            onClick={() => onDoiMucPhong(MUC_PHONG[Math.max(0, chiSoMuc - 1)])}
            aria-label="Thu nhỏ dòng thời gian"
          >
            −
          </button>
          <span className="w-14 text-center font-mono text-[10.5px]">{mucPhong} px/s</span>
          <button
            className="btn btn-sm px-2"
            disabled={chiSoMuc >= MUC_PHONG.length - 1}
            onClick={() => onDoiMucPhong(MUC_PHONG[Math.min(MUC_PHONG.length - 1, chiSoMuc + 1)])}
            aria-label="Phóng to dòng thời gian"
          >
            +
          </button>
        </span>
      </div>

      <div ref={khung} className="relative overflow-x-auto overflow-y-hidden pb-2">
        <div style={{ width: rongTong }} className="relative">
          {/* Thước thời gian */}
          <div
            className="relative h-5 cursor-pointer border-b border-border/60"
            onClick={bamVaoNen}
          >
            {moc.map((g) => (
              <span
                key={g}
                className="absolute top-0 h-full border-l border-border pl-1 text-[10px] leading-5 text-muted"
                style={{ left: g * mucPhong }}
              >
                {nhanGiay(g)}
              </span>
            ))}
          </div>

          {/* Lớp PHỤ ĐỀ */}
          <LopNhan nhan="Phụ đề" />
          <div className="relative" style={{ height: CAO_LOP }} onClick={bamVaoNen}>
            {cues.map((c, o) => {
              const { left, width } = viTriKhoi(c.start, c.end - c.start, mucPhong);
              return (
                <button
                  key={c.i}
                  onClick={(e) => {
                    e.stopPropagation();
                    onChonCau(o);
                  }}
                  title={dangSua?.[c.i] ?? c.dich}
                  style={{ left, width }}
                  className={clsx(
                    "absolute top-1 h-[26px] overflow-hidden rounded border px-1 text-left text-[10.5px] leading-[24px] whitespace-nowrap",
                    o === dangChon
                      ? "border-accent bg-accent/30 text-fg"
                      : c.sua_tay
                        ? "border-accent/50 bg-accent/15 text-fg/90"
                        : "border-border bg-panel3 text-fg/80 hover:bg-panel2",
                  )}
                >
                  {dangSua?.[c.i] ?? c.dich}
                </button>
              );
            })}
          </div>

          {/* Lớp GIỌNG — đây mới là chỗ lộ ra lỗi lệch tiếng */}
          <LopNhan nhan="Giọng" />
          <div className="relative" style={{ height: CAO_LOP }} onClick={bamVaoNen}>
            {cues.map((c, o) => {
              const dai = daiGiongSauEp(c);
              if (dai <= 0) return null;
              const { left, width } = viTriKhoi(c.start, dai, mucPhong);
              const tran = coTran(c);
              const ep = biEpNhanh(c);
              return (
                <button
                  key={c.i}
                  onClick={(e) => {
                    e.stopPropagation();
                    onChonCau(o);
                  }}
                  title={
                    tran
                      ? `Tràn ${c.tran_giay.toFixed(2)}s sang câu sau (đã ép ${c.he_so_toc_do.toFixed(2)}×)`
                      : ep
                        ? `Phải đọc nhanh ${c.he_so_toc_do.toFixed(2)}× mới vừa`
                        : `${dai.toFixed(2)}s`
                  }
                  style={{ left, width }}
                  className={clsx(
                    "absolute top-1 h-[26px] rounded border",
                    tran
                      ? "border-err bg-err/40"
                      : ep
                        ? "border-warn/70 bg-warn/25"
                        : "border-ok/50 bg-ok/20",
                    o === dangChon && "ring-1 ring-accent",
                  )}
                />
              );
            })}
          </div>

          {/* Con trỏ phát — vẽ sau cùng để nằm trên mọi khối */}
          <div
            className="pointer-events-none absolute top-0 bottom-0 w-px bg-accent"
            style={{ left: giayHienTai * mucPhong }}
          >
            <span className="absolute -top-0 -left-[3px] h-1.5 w-1.5 rounded-full bg-accent" />
          </div>
        </div>
      </div>
    </div>
  );
}

function LopNhan({ nhan }: { nhan: string }) {
  return (
    <div className="sticky left-0 z-10 w-fit px-1 pt-1 text-[9.5px] uppercase tracking-wider text-muted">
      {nhan}
    </div>
  );
}
