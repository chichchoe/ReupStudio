"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Page as ApiPage, TuyChonDich, Video } from "@/lib/types";

/** Video gửi dịch không thành — LUÔN kèm lý do, không được nuốt lỗi im lặng. */
export interface TranslateFailure {
  id: string;
  message: string;
}

interface Options {
  /**
   * Khoá cache của danh sách video chờ dịch. Phải TRÙNG khoá `useQuery` ở tab,
   * nếu lệch thì optimistic update ghi vào ô cache không ai đọc và danh sách
   * đứng im cho tới lần refetch sau.
   */
  videosKey: readonly unknown[];
  onDone?: (failures: TranslateFailure[]) => void;
}

/**
 * Gửi yêu cầu dịch cho một hoặc nhiều video ở trạng thái `review`.
 *
 * Hợp đồng API chỉ có endpoint cho MỘT video (`POST /videos/{id}/translate`)
 * nên bản hàng loạt gọi lặp. Endpoint trả `202` ngay, việc dịch chạy trong
 * Celery — tiến trình thật xem qua WebSocket như mọi bước khác, KHÔNG polling.
 */
export function useTranslateMutations({ videosKey, onDone }: Options) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async ({ ids, tuyChon }: { ids: string[]; tuyChon: TuyChonDich }) => {
      // allSettled chứ không Promise.all: một video lỗi (chạm trần hạn mức,
      // model không hợp lệ) không được chặn những video còn lại trong lô.
      const results = await Promise.allSettled(
        ids.map((id) => api.translateVideo(id, tuyChon)),
      );
      return results.flatMap<TranslateFailure>((result, index) =>
        result.status === "rejected"
          ? [
              {
                id: ids[index],
                message:
                  result.reason instanceof ApiError
                    ? result.reason.message
                    : "Không gửi được yêu cầu dịch",
              },
            ]
          : [],
      );
    },
    onMutate: async ({ ids }) => {
      // Với người dùng đây là thao tác nhanh (chỉ đẩy vào hàng đợi) nên bỏ video
      // khỏi danh sách chờ ngay, không bắt đợi round-trip. Video nào gửi lỗi sẽ
      // quay lại danh sách sau lần invalidate ở onSettled.
      await queryClient.cancelQueries({ queryKey: videosKey });
      const previous = queryClient.getQueryData<ApiPage<Video>>(videosKey);
      if (previous) {
        const idSet = new Set(ids);
        queryClient.setQueryData<ApiPage<Video>>(videosKey, {
          ...previous,
          items: previous.items.filter((v) => !idSet.has(v.id)),
          total: Math.max(0, previous.total - ids.length),
        });
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(videosKey, context.previous);
    },
    onSuccess: onDone,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["videos"] });
      queryClient.invalidateQueries({ queryKey: ["counts"] });
      // Gửi dịch là tiêu thêm lượt/token — kéo lại dải hạn mức cho khớp thực tế.
      queryClient.invalidateQueries({ queryKey: ["llm-usage"] });
    },
  });

  return {
    translate: (ids: string[], tuyChon: TuyChonDich) => mutation.mutate({ ids, tuyChon }),
    /** Id các video đang có yêu cầu dịch bay dở — dùng để khoá nút ở từng dòng. */
    pendingIds: new Set(mutation.isPending ? mutation.variables?.ids ?? [] : []),
    translatePending: mutation.isPending,
  };
}
