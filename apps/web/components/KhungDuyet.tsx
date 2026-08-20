"use client";

import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { DongThoiGian } from "@/components/DongThoiGian";
import { api } from "@/lib/api";
import {
  biEpNhanh,
  cauDangPhat,
  coTran,
  demVanDe,
  nhanGiay,
  type CapDoiChieu,
} from "@/lib/dongThoiGian";

/** Lệch quá ngần này giây thì nắn dải tiếng về khớp hình. */
const NGUONG_LECH_GIAY = 0.15;

interface Props {
  videoId: string;
  cues: CapDoiChieu[];
  /** `zh` hiện câu gốc trên hình (tab Chờ dịch), `vi` hiện bản dịch (tab Chờ duyệt). */
  hien: "vi" | "zh";
  /** Có dải tiếng Việt để nghe kèm không — chỉ tab Chờ duyệt mới có. */
  coDaiTieng?: boolean;
  /** Chữ đang gõ chưa lưu: `{ [i]: text }`. */
  dangSua?: Record<number, string>;
  onDoiChu?: (i: number, chu: string) => void;
  onDichLaiCau?: (i: number) => void;
}

/**
 * Màn duyệt bản dịch: xem trước ở giữa, thuộc tính bên phải, dòng thời gian dưới.
 *
 * Bố cục theo kiểu trình dựng phim vì việc ở đây đúng là việc dựng: phải thấy
 * câu nằm ở đâu trên trục thời gian, dài bao nhiêu, và giọng đọc có tràn sang
 * câu sau không. Danh sách chữ cuộn dọc giấu hết những thứ đó.
 */
export function KhungDuyet({
  videoId,
  cues,
  hien,
  coDaiTieng = false,
  dangSua,
  onDoiChu,
  onDichLaiCau,
}: Props) {
  const theVideo = useRef<HTMLVideoElement>(null);
  const theTieng = useRef<HTMLAudioElement>(null);
  const [giay, setGiay] = useState(0);
  const [tongGiay, setTongGiay] = useState(0);
  const [ngheTiengViet, setNgheTiengViet] = useState(coDaiTieng);
  const [mucPhong, setMucPhong] = useState(32);
  const [chonTay, setChonTay] = useState<number | null>(null);

  const dangPhat = useMemo(() => cauDangPhat(cues, giay), [cues, giay]);
  //: Người dùng bấm chọn một câu thì GIỮ nguyên lựa chọn đó, không để con trỏ
  //: phát cướp mất — đang sửa câu 12 mà video chạy tới câu 13 là ô sửa nhảy.
  const dangChon = chonTay ?? dangPhat;
  const cue = dangChon >= 0 && dangChon < cues.length ? cues[dangChon] : null;

  const vanDe = useMemo(() => demVanDe(cues), [cues]);

  const chuTrenHinh =
    dangPhat >= 0
      ? hien === "vi"
        ? (dangSua?.[cues[dangPhat].i] ?? cues[dangPhat].dich)
        : cues[dangPhat].goc
      : "";

  // Khoá dải tiếng theo hình. Chỉ nắn khi lệch quá ngưỡng — nắn mỗi lần
  // `timeupdate` thì tiếng bị giật liên tục.
  useEffect(() => {
    const v = theVideo.current;
    const a = theTieng.current;
    if (!v || !a) return;

    const dongBo = () => {
      if (Math.abs(a.currentTime - v.currentTime) > NGUONG_LECH_GIAY) {
        a.currentTime = v.currentTime;
      }
    };
    const phat = () => {
      dongBo();
      if (ngheTiengViet) void a.play().catch(() => undefined);
    };
    const dung = () => a.pause();

    v.addEventListener("play", phat);
    v.addEventListener("pause", dung);
    v.addEventListener("seeked", dongBo);
    return () => {
      v.removeEventListener("play", phat);
      v.removeEventListener("pause", dung);
      v.removeEventListener("seeked", dongBo);
    };
  }, [ngheTiengViet]);

  const tuaToi = (s: number) => {
    const v = theVideo.current;
    if (!v) return;
    v.currentTime = s;
  };

  return (
    <div className="flex flex-col rounded-lg border border-border bg-bg">
      <div className="flex min-h-0 gap-3 p-3">
        {/* GIỮA — khung xem */}
        <div className="relative shrink-0 self-start overflow-hidden rounded bg-black">
          {/* eslint-disable-next-line jsx-a11y/media-has-caption --
              Phụ đề vẽ bằng overlay ngay dưới, không có track riêng. */}
          <video
            key={videoId}
            ref={theVideo}
            src={api.previewUrl(videoId)}
            controls
            //: Tắt tiếng gốc khi đang nghe bản lồng tiếng — hai giọng chồng
            //: nhau thì không nghe rõ giọng nào.
            muted={ngheTiengViet}
            onTimeUpdate={(e) => setGiay(e.currentTarget.currentTime)}
            onLoadedMetadata={(e) => setTongGiay(e.currentTarget.duration || 0)}
            className="max-h-[46vh] w-auto"
          />

          {chuTrenHinh && (
            <div className="pointer-events-none absolute inset-x-0 bottom-[12%] px-3 text-center">
              <span className="inline-block whitespace-pre-wrap rounded bg-black/65 px-2 py-1 text-[14px] font-medium leading-snug text-white">
                {chuTrenHinh}
              </span>
            </div>
          )}

          {coDaiTieng && (
            // eslint-disable-next-line jsx-a11y/media-has-caption -- dải lời thoại
            <audio ref={theTieng} src={api.voiceTrackUrl(videoId)} preload="auto" />
          )}
        </div>

        {/* PHẢI — thuộc tính câu đang chọn */}
        <div className="flex min-w-0 flex-1 flex-col rounded border border-border bg-panel p-3">
          {coDaiTieng && (
            <div className="mb-2 flex items-center gap-2 text-[11.5px]">
              <span className="text-muted">Đang nghe:</span>
              <button
                className={clsx("btn btn-sm", ngheTiengViet && "btn-primary")}
                onClick={() => setNgheTiengViet(true)}
              >
                Tiếng Việt
              </button>
              <button
                className={clsx("btn btn-sm", !ngheTiengViet && "btn-primary")}
                onClick={() => setNgheTiengViet(false)}
              >
                Tiếng gốc
              </button>

              {(vanDe.tran > 0 || vanDe.epNhanh > 0) && (
                <span className="ml-auto text-[11px]">
                  {vanDe.tran > 0 && <span className="text-err">{vanDe.tran} câu tràn</span>}
                  {vanDe.tran > 0 && vanDe.epNhanh > 0 && <span className="text-muted"> · </span>}
                  {vanDe.epNhanh > 0 && (
                    <span className="text-warn">{vanDe.epNhanh} câu đọc nhanh hết cỡ</span>
                  )}
                </span>
              )}
            </div>
          )}

          {!cue ? (
            <div className="flex flex-1 items-center justify-center text-center text-[12.5px] text-muted">
              Bấm một câu trên dòng thời gian để xem và sửa.
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto">
              <div className="mb-2 flex items-center gap-2 text-[11px] text-muted">
                <span className="font-mono">câu {cue.i + 1}</span>
                <span className="opacity-40">·</span>
                <span className="font-mono">
                  {nhanGiay(cue.start)}–{nhanGiay(cue.end)}
                </span>
                {cue.sua_tay && <span className="text-accent">đã sửa tay</span>}
              </div>

              <div className="mb-1 text-[11px] text-muted">Bản gốc</div>
              <div className="mb-3 whitespace-pre-wrap rounded bg-panel2 px-2 py-1.5 text-[13px]">
                {cue.goc || "—"}
              </div>

              {hien === "vi" && (
                <>
                  <div className="mb-1 text-[11px] text-muted">Bản dịch</div>
                  <textarea
                    className="mb-3 w-full resize-y rounded border border-border bg-bg px-2 py-1.5 text-[13px] outline-none focus:border-accent"
                    rows={3}
                    value={dangSua?.[cue.i] ?? cue.dich}
                    onChange={(e) => onDoiChu?.(cue.i, e.target.value)}
                    aria-label={`Sửa câu ${cue.i + 1}`}
                  />

                  {cue.giong_giay !== null && (
                    <div className="mb-3 space-y-1 text-[11.5px]">
                      <div className="flex justify-between text-muted">
                        <span>Giọng đã đọc</span>
                        <span className="font-mono text-fg">{cue.giong_giay.toFixed(2)}s</span>
                      </div>
                      <div className="flex justify-between text-muted">
                        <span>Chỗ trống tới câu sau</span>
                        <span className="font-mono text-fg">
                          {cue.cho_trong_giay.toFixed(2)}s
                        </span>
                      </div>
                      {biEpNhanh(cue) && (
                        <div className="text-warn">
                          ⚠ Phải đọc nhanh {cue.he_so_toc_do.toFixed(2)}× — đã chạm trần, trên
                          nữa người xem không bắt kịp ý.
                        </div>
                      )}
                      {coTran(cue) && (
                        <div className="text-err">
                          ⚠ Vẫn tràn {cue.tran_giay.toFixed(2)}s sang câu sau. Rút ngắn bản dịch
                          là cách chữa duy nhất.
                        </div>
                      )}
                    </div>
                  )}

                  {onDichLaiCau && (
                    <button className="btn btn-sm w-full" onClick={() => onDichLaiCau(cue.i)}>
                      Dịch lại câu này
                    </button>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* DƯỚI — dòng thời gian */}
      <DongThoiGian
        cues={cues}
        tongGiay={tongGiay}
        giayHienTai={giay}
        dangChon={dangChon}
        mucPhong={mucPhong}
        dangSua={dangSua}
        onChonCau={(o) => {
          setChonTay(o);
          tuaToi(cues[o].start);
        }}
        onTuaToi={(s) => {
          setChonTay(null);
          tuaToi(s);
        }}
        onDoiMucPhong={setMucPhong}
      />
    </div>
  );
}
