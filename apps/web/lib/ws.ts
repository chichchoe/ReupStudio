"use client";

/**
 * Hook WebSocket nhận tiến trình realtime.
 *
 * KHÔNG polling API để lấy tiến trình — worker publish lên Redis, API broadcast
 * xuống đây.
 *
 * API chỉ đẩy `progress`/`status` cho client đã subscribe topic `video:<id>`
 * tương ứng, và `queue` cho client đã subscribe topic `queue`. Topic `alert`
 * luôn được gửi cho mọi client. Vì vậy hook này:
 *   - Tự subscribe topic `queue` ngay khi mở socket.
 *   - Nhận thêm danh sách topic video qua tham số `topics`, gửi lệnh
 *     subscribe/unsubscribe phần chênh lệch mỗi khi danh sách đổi.
 *   - Khi socket đứt rồi nối lại, gửi lại TOÀN BỘ topic đang cần — kết nối
 *     mới ở phía server không nhớ subscription cũ, thiếu bước này thì sau khi
 *     mất mạng người dùng sẽ mất sạch tiến trình vĩnh viễn.
 */

import { useEffect, useRef, useState } from "react";
import { WS_URL } from "./api";
import type { PipelineStep, VideoStatus, WsEvent } from "./types";

export interface VideoProgress {
  step: PipelineStep;
  percent: number;
  note?: string;
}

export interface QueueCounts {
  active: number;
  pending: number;
}

export interface WsState {
  connected: boolean;
  progress: Record<string, VideoProgress>;
  statuses: Record<string, { status: VideoStatus; step: PipelineStep | null }>;
  queue: QueueCounts | null;
  lastAlert: { level: string; title: string; detail?: string } | null;
}

export interface UseReupSocketOptions {
  /** Topic video cần theo dõi thêm, dạng `video:<id>`. Topic `queue` luôn được subscribe sẵn. */
  topics?: string[];
  onStatusChange?: () => void;
}

/** Topic mặc định mọi kết nối đều cần, không phụ thuộc component gọi hook. */
const BASE_TOPICS = ["queue"];

export function useReupSocket(options: UseReupSocketOptions = {}): WsState {
  const { topics = [], onStatusChange } = options;

  const [state, setState] = useState<WsState>({
    connected: false,
    progress: {},
    statuses: {},
    queue: null,
    lastAlert: null,
  });
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callbackRef = useRef(onStatusChange);
  callbackRef.current = onStatusChange;

  // Topic video mong muốn hiện tại — đọc lại khi socket nối lại để gửi subscribe đầy đủ.
  const desiredTopicsRef = useRef<string[]>(topics);
  // Topic đã báo cho server biết trên kết nối hiện tại (để chỉ gửi phần chênh lệch).
  const sentTopicsRef = useRef<Set<string>>(new Set());

  const syncTopics = (desiredVideoTopics: string[]) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const desired = new Set([...BASE_TOPICS, ...desiredVideoTopics]);
    const toAdd = [...desired].filter((t) => !sentTopicsRef.current.has(t));
    const toRemove = [...sentTopicsRef.current].filter((t) => !desired.has(t));
    if (toAdd.length > 0) socket.send(JSON.stringify({ subscribe: toAdd }));
    if (toRemove.length > 0) socket.send(JSON.stringify({ unsubscribe: toRemove }));
    sentTopicsRef.current = desired;
  };

  useEffect(() => {
    let closed = false;

    const connect = () => {
      if (closed) return;
      const socket = new WebSocket(WS_URL);
      socketRef.current = socket;

      socket.onopen = () => {
        setState((s) => ({ ...s, connected: true }));
        // Kết nối mới (kể cả sau reconnect) — server chưa biết subscription
        // nào cả, phải coi như chưa gửi gì và bắn lại toàn bộ topic cần.
        sentTopicsRef.current = new Set();
        syncTopics(desiredTopicsRef.current);
      };

      socket.onmessage = (event) => {
        let data: WsEvent;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }

        if (data.type === "progress") {
          setState((s) => ({
            ...s,
            progress: {
              ...s.progress,
              [data.video_id]: { step: data.step, percent: data.percent, note: data.note },
            },
          }));
        } else if (data.type === "status") {
          setState((s) => ({
            ...s,
            statuses: {
              ...s.statuses,
              [data.video_id]: { status: data.status, step: data.step },
            },
          }));
          callbackRef.current?.();
        } else if (data.type === "queue") {
          setState((s) => ({ ...s, queue: { active: data.active, pending: data.pending } }));
        } else if (data.type === "alert") {
          setState((s) => ({
            ...s,
            lastAlert: { level: data.level, title: data.title, detail: data.detail },
          }));
        }
      };

      socket.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (!closed) retryRef.current = setTimeout(connect, 3000);
      };

      socket.onerror = () => socket.close();
    };

    connect();

    return () => {
      closed = true;
      if (retryRef.current) clearTimeout(retryRef.current);
      socketRef.current?.close();
    };
  }, []);

  // topics là mảng mới mỗi lần render ở phía gọi, nên dùng chuỗi nối làm khoá
  // effect thay vì so sánh tham chiếu mảng — tránh chạy lại effect vô ích.
  const topicsKey = topics.join(",");
  useEffect(() => {
    desiredTopicsRef.current = topics;
    syncTopics(topics);
    // topicsKey đại diện đầy đủ cho nội dung của topics ở trên.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicsKey]);

  return state;
}
