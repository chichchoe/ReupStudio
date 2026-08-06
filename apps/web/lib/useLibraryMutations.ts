"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { BulkAction, BulkResult, Page as ApiPage, Video } from "@/lib/types";

interface Options {
  status: string;
  query: string;
  onBulkDone?: (result: BulkResult) => void;
}

/**
 * Gom mutation của trang Thư viện: xử lý lại một video, xoá một video, và hành
 * động hàng loạt. Xoá đơn cùng Duyệt/Xoá hàng loạt là thao tác nhanh theo
 * CLAUDE.md — phản hồi ngay bằng optimistic update trên cache `["videos", ...]`,
 * rollback nếu server báo lỗi. Xử lý lại và áp preset không đoán trước được kết
 * quả nên vẫn chờ round-trip như cũ.
 */
export function useLibraryMutations({ status, query, onBulkDone }: Options) {
  const queryClient = useQueryClient();
  const videosKey = ["videos", status, query] as const;

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["videos"] });
    queryClient.invalidateQueries({ queryKey: ["counts"] });
  };

  const retryMutation = useMutation({
    mutationFn: (id: string) => api.retry(id),
    onSuccess: refresh,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.remove(id),
    onMutate: async (id: string) => {
      await queryClient.cancelQueries({ queryKey: videosKey });
      const previous = queryClient.getQueryData<ApiPage<Video>>(videosKey);
      if (previous) {
        queryClient.setQueryData<ApiPage<Video>>(videosKey, {
          ...previous,
          items: previous.items.filter((v) => v.id !== id),
          total: Math.max(0, previous.total - 1),
        });
      }
      return { previous };
    },
    onError: (_err, _id, context) => {
      if (context?.previous) queryClient.setQueryData(videosKey, context.previous);
    },
    onSettled: refresh,
  });

  const bulkMutation = useMutation({
    mutationFn: ({
      ids,
      action,
      payload,
    }: {
      ids: string[];
      action: BulkAction;
      payload?: Record<string, unknown>;
    }) => api.bulk(ids, action, payload),
    onMutate: async ({ ids, action }) => {
      // Chỉ đoán trước kết quả cho duyệt/xoá — "sẵn sàng" cho review, biến mất
      // khỏi danh sách khi xoá. Xử lý lại/áp preset để nguyên chờ server trả lời.
      if (action !== "approve" && action !== "delete") return undefined;
      await queryClient.cancelQueries({ queryKey: videosKey });
      const previous = queryClient.getQueryData<ApiPage<Video>>(videosKey);
      if (previous) {
        const idSet = new Set(ids);
        queryClient.setQueryData<ApiPage<Video>>(videosKey, {
          ...previous,
          items:
            action === "delete"
              ? previous.items.filter((v) => !idSet.has(v.id))
              : previous.items.map((v) =>
                  idSet.has(v.id) && v.status === "review" ? { ...v, status: "ready" } : v,
                ),
          total: action === "delete" ? Math.max(0, previous.total - ids.length) : previous.total,
        });
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(videosKey, context.previous);
    },
    onSuccess: onBulkDone,
    onSettled: refresh,
  });

  return {
    retry: (id: string) => retryMutation.mutate(id),
    remove: (id: string) => deleteMutation.mutate(id),
    bulk: (ids: string[], action: BulkAction, payload?: Record<string, unknown>) =>
      bulkMutation.mutate({ ids, action, payload }),
    bulkPending: bulkMutation.isPending,
  };
}
