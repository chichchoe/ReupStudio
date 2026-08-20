"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { KhungDuyet } from "@/components/KhungDuyet";
import { api, ApiError } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { Video } from "@/lib/types";

const REVIEW_STATUS = "review";

/**
 * Tab duyệt bản dịch và giọng đọc, TRƯỚC khi ghép vào video.
 *
 * Vì sao có chỗ dừng này: bước sau nó (xoá chữ cứng rồi render) là phần nặng
 * nhất pipeline — video một tiếng mất hàng tiếng. Không ưng bản dịch hay giọng
 * đọc mà phát hiện sau khi render xong thì đã đốt ngần ấy thời gian máy.
 *
 * Ở đây người dùng làm đúng ba việc: ĐỐI CHIẾU từng câu Trung với câu Việt,
 * NGHE thử dải tiếng đã khớp thời gian, và biết bản dịch này do model nào làm
 * ra để lần sau chọn khác nếu chưa ưng.
 */
export function DuyetBanDichTab() {
  const queryClient = useQueryClient();
  const [dangMo, setDangMo] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["videos", REVIEW_STATUS, ""],
    queryFn: () => api.listVideos({ status: REVIEW_STATUS }),
  });

  //: Cùng trạng thái `review` với tab Chờ dịch, phân biệt bằng cờ — video ở
  //: chỗ dừng thứ nhất chưa có bản dịch để mà duyệt.
  const videos = (data?.items ?? []).filter((v) => Boolean(v.flags?.cho_duyet_ban_dich));

  const duyet = useMutation({
    mutationFn: (id: string) => api.approveDub(id),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["videos"] });
      queryClient.invalidateQueries({ queryKey: ["counts"] });
    },
  });

  if (isLoading) return <p className="py-8 text-center text-[13px] text-muted">Đang tải…</p>;

  if (videos.length === 0) {
    return (
      <div className="py-16 text-center text-[13px] text-muted">
        Không có bản dịch nào đang chờ duyệt.
      </div>
    );
  }

  return (
    <div>
      {videos.map((v) => (
        <DongDuyet
          key={v.id}
          video={v}
          mo={dangMo === v.id}
          dangGui={duyet.isPending && duyet.variables === v.id}
          onMo={() => setDangMo(dangMo === v.id ? null : v.id)}
          onDuyet={() => duyet.mutate(v.id)}
        />
      ))}
    </div>
  );
}

/** Chuỗi mô tả AI đã dịch và giọng đã đọc, lấy từ ``process_config``. */
function _daDungGi(video: Video): { ai: string; giong: string } {
  const c = (video.process_config ?? {}) as Record<string, unknown>;
  const ben = String(c.llm_provider_ma ?? "");
  const model = String(c.llm_model ?? "");
  const benDoc = String(c.tts_provider ?? "");
  const giongDoc = String(c.giong_doc ?? "");
  return {
    ai: [ben, model].filter(Boolean).join(" · ") || "mặc định",
    giong: [benDoc, giongDoc].filter(Boolean).join(" · ") || "mặc định",
  };
}

interface DongProps {
  video: Video;
  mo: boolean;
  dangGui: boolean;
  onMo: () => void;
  onDuyet: () => void;
}

function DongDuyet({ video, mo, dangGui, onMo, onDuyet }: DongProps) {
  const queryClient = useQueryClient();
  //: Ghép ở BACKEND theo THỜI GIAN. Bản cũ ghép theo CHỈ SỐ, mà bước chuẩn
  //: hoá phụ đề gộp/tách câu rồi đánh số lại — đo trên DB thật ngày
  //: 2026-08-20: 8/10 video lệch, video tệ nhất ghép lệch 7 giây và ra chữ
  //: không liên quan. Endpoint trả kèm số đo lồng tiếng để vẽ dòng thời gian.
  const { data: doi = [] } = useQuery({
    queryKey: ["doi-chieu", video.id],
    queryFn: () => api.doiChieu(video.id),
    enabled: mo,
  });

  const title = video.title_vi || video.title_original || video.source_video_id;
  const { ai, giong } = _daDungGi(video);

  //: Chỉ giữ câu ĐÃ SỬA, không chép cả bảng vào state: video 672 câu mà mỗi
  //: phím gõ lại dựng lại toàn bộ mảng thì gõ bị khựng.
  const [sua, setSua] = useState<Record<number, string>>({});
  const soSua = Object.keys(sua).length;

  const luu = useMutation({
    mutationFn: () =>
      api.suaBanDich(
        video.id,
        Object.entries(sua).map(([i, text]) => ({ i: Number(i), text })),
      ),
    onSuccess: () => {
      setSua({});
      queryClient.invalidateQueries({ queryKey: ["doi-chieu", video.id] });
      queryClient.invalidateQueries({ queryKey: ["videos"] });
    },
  });

  const dichLai = useMutation({
    mutationFn: (body: { chi_so?: number[] }) => api.dichLai(video.id, body),
    onSuccess: () => {
      setSua({});
      queryClient.invalidateQueries({ queryKey: ["doi-chieu", video.id] });
      queryClient.invalidateQueries({ queryKey: ["videos"] });
      //: Dịch lại tiêu thêm lượt/token — kéo lại dải hạn mức cho khớp thực tế.
      queryClient.invalidateQueries({ queryKey: ["llm-usage"] });
    },
  });

  return (
    <div className="mb-2 rounded-xl border border-border bg-panel p-3">
      <div className="flex items-center gap-3">
        <button className="btn btn-sm shrink-0" onClick={onMo} aria-expanded={mo}>
          {mo ? "Thu lại" : "Đối chiếu"}
        </button>

        <div className="min-w-0 flex-1">
          <div className="truncate text-[13.5px] font-medium">{title}</div>
          {/* Model và giọng hiện NGAY TRÊN DÒNG, không phải mở ra mới thấy:
              đọc thấy bản dịch chưa sát thì câu hỏi đầu tiên luôn là "con nào
              dịch cái này", và đó là thứ quyết định lần sau chọn gì. */}
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-muted">
            <span>{formatDuration(video.duration_sec)}</span>
            <span className="opacity-40">·</span>
            <span>
              AI dịch: <span className="font-mono text-fg">{ai}</span>
            </span>
            <span className="opacity-40">·</span>
            <span>
              Giọng: <span className="font-mono text-fg">{giong}</span>
            </span>
          </div>
          <div className="mt-1 text-[11px] text-warn">
            Đã dịch và lồng tiếng — đối chiếu rồi duyệt để ghép vào video
          </div>
        </div>

        <button className="btn btn-primary btn-sm shrink-0" disabled={dangGui} onClick={onDuyet}>
          {dangGui ? "Đang gửi…" : "Duyệt và ghép"}
        </button>
      </div>

      {mo && (
        <div className="mt-3 border-t border-border pt-3">
          <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11.5px] text-muted">
            <span>{doi.length} câu</span>
            <span className="opacity-40">·</span>
            {/* Đặt bản gốc CẠNH bản dịch chứ không chỉ hiện tiếng Việt: dịch
                Trung–Việt sai chỗ nào thì chỉ nhìn riêng tiếng Việt không thể
                biết — câu sai vẫn đọc trôi chảy như thường. */}
            <span>bấm một câu trên dòng thời gian để nghe và sửa</span>

            {soSua > 0 && (
              <span className="ml-auto flex items-center gap-2">
                <span className="text-accent">{soSua} câu đã sửa</span>
                <button className="btn btn-sm" onClick={() => setSua({})} disabled={luu.isPending}>
                  Bỏ sửa
                </button>
                {/* Đọc lại NGAY khi lưu: bản dịch đổi mà dải tiếng còn của bản
                    cũ thì duyệt xong ghép vào video là lệch hẳn lời. Worker chỉ
                    gọi nhà cung cấp cho câu đã đổi chữ. */}
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => luu.mutate()}
                  disabled={luu.isPending}
                >
                  {luu.isPending ? "Đang lưu…" : `Lưu và đọc lại ${soSua} câu`}
                </button>
              </span>
            )}
            {luu.isSuccess && soSua === 0 && (
              <span className="ml-auto text-ok">Đã lưu — đang đọc lại giọng…</span>
            )}
            {luu.isError && (
              <span className="ml-auto text-err">
                {luu.error instanceof ApiError ? luu.error.message : "Không lưu được"}
              </span>
            )}
          </div>

          <KhungDuyet
            videoId={video.id}
            cues={doi}
            hien="vi"
            coDaiTieng
            dangSua={sua}
            onDoiChu={(i, chu) =>
              setSua((cu) => {
                //: Gõ về đúng chữ cũ thì BỎ khỏi danh sách sửa — không thì nút
                //: báo "3 câu đã sửa" trong khi chẳng câu nào khác đi.
                const goc = doi.find((c) => c.i === i)?.dich ?? "";
                const { [i]: _bo, ...con_lai } = cu;
                return chu === goc ? con_lai : { ...cu, [i]: chu };
              })
            }
            onDichLaiCau={(i) => dichLai.mutate({ chi_so: [i] })}
          />

          <div className="mt-2 flex items-center gap-2">
            <button
              className="btn btn-sm ml-auto"
              disabled={dichLai.isPending}
              onClick={() => dichLai.mutate({})}
            >
              {dichLai.isPending ? "Đang gửi…" : "Dịch lại toàn bộ"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
