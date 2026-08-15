"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
 * Ở đây người dùng làm đúng hai việc: ĐỌC lại toàn bộ câu tiếng Việt, và NGHE
 * thử dải tiếng đã khớp thời gian. Cả hai đều nhanh, và cả hai đều không thể
 * thay bằng việc đọc log.
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
  const { data: subs } = useQuery({
    queryKey: ["subtitles", video.id, "vi"],
    queryFn: () => api.subtitles(video.id, "vi"),
    enabled: mo,
  });
  const cues = subs?.find((s) => s.lang === "vi")?.cues ?? [];
  const title = video.title_vi || video.title_original || video.source_video_id;

  return (
    <div className="mb-2 rounded-xl border border-border bg-panel p-3">
      <div className="flex items-center gap-3">
        <button className="btn btn-sm shrink-0" onClick={onMo} aria-expanded={mo}>
          {mo ? "Thu lại" : "Xem"}
        </button>

        <div className="min-w-0 flex-1">
          <div className="truncate text-[13.5px] font-medium">{title}</div>
          <div className="text-[11.5px] text-muted">{formatDuration(video.duration_sec)}</div>
          <div className="mt-1 text-[11px] text-warn">
            Đã dịch và lồng tiếng — đọc lại rồi duyệt để ghép vào video
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

          <div className="mb-1.5 text-[11.5px] text-muted">
            {cues.length} câu tiếng Việt — đọc lại trước khi ghép
          </div>
          <div className="max-h-72 overflow-y-auto rounded-lg border border-border bg-bg p-2">
            {cues.map((c) => (
              <div key={c.i} className="flex gap-3 py-1 text-[12.5px]">
                <span className="w-24 shrink-0 font-mono text-[11px] text-muted">
                  {c.start.toFixed(1)}–{c.end.toFixed(1)}s
                </span>
                <span className="whitespace-pre-wrap">{c.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
