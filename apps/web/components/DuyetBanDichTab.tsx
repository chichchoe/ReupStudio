"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
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
  //: Chỉ tải phụ đề khi người dùng MỞ dòng ra. Một video có tới 672 câu, tải
  //: sẵn cho mọi dòng là kéo về hàng nghìn câu không ai đọc.
  //: Lấy CẢ HAI thứ tiếng trong một lượt — không truyền `lang` thì API trả hết.
  const { data: subs } = useQuery({
    queryKey: ["subtitles", video.id, "tat-ca"],
    queryFn: () => api.subtitles(video.id),
    enabled: mo,
  });

  //: Ghép câu Trung với câu Việt theo CHỈ SỐ, không theo mốc thời gian: bước
  //: chuẩn hoá phụ đề tách một câu dài thành nhiều mảnh nên hai bên có thể
  //: lệch số dòng, và mốc thời gian đã bị nắn lại.
  const doi = useMemo(() => {
    const vi = subs?.find((s) => s.lang === "vi")?.cues ?? [];
    const zh = subs?.find((s) => s.lang === "zh")?.cues ?? [];
    return vi.map((c, i) => ({ vi: c, zh: zh[i] ?? null }));
  }, [subs]);

  const title = video.title_vi || video.title_original || video.source_video_id;
  const { ai, giong } = _daDungGi(video);

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
          <div className="mb-3">
            <div className="mb-1.5 text-[11.5px] text-muted">
              Nghe thử giọng đã khớp thời gian
            </div>
            {/* eslint-disable-next-line jsx-a11y/media-has-caption --
                Đây là dải LỜI THOẠI, phụ đề của nó nằm ngay dưới. */}
            <audio controls preload="none" className="w-full" src={api.voiceTrackUrl(video.id)} />
          </div>

          <div className="mb-1.5 flex items-center gap-2 text-[11.5px] text-muted">
            <span>{doi.length} câu</span>
            <span className="opacity-40">·</span>
            {/* Đặt bản gốc CẠNH bản dịch chứ không chỉ hiện tiếng Việt: dịch
                Trung–Việt sai chỗ nào thì chỉ nhìn riêng tiếng Việt không thể
                biết — câu sai vẫn đọc trôi chảy như thường. */}
            <span>đối chiếu từng câu với bản gốc để bắt chỗ dịch chưa sát</span>
          </div>

          <div className="max-h-96 overflow-y-auto rounded-lg border border-border bg-bg">
            <div className="sticky top-0 grid grid-cols-[5.5rem_1fr_1fr] gap-2 border-b border-border bg-panel2 px-2 py-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted">
              <span>Thời gian</span>
              <span>Bản gốc</span>
              <span>Bản dịch</span>
            </div>
            {doi.map(({ vi, zh }) => (
              <div
                key={vi.i}
                className="grid grid-cols-[5.5rem_1fr_1fr] gap-2 border-b border-border/50 px-2 py-1.5 text-[12.5px] last:border-0 hover:bg-panel2/50"
              >
                <span className="font-mono text-[10.5px] text-muted">
                  {vi.start.toFixed(1)}–{vi.end.toFixed(1)}
                </span>
                <span className="whitespace-pre-wrap text-muted">{zh?.text ?? "—"}</span>
                <span className="whitespace-pre-wrap">{vi.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
