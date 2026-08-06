"use client";

/**
 * Hook WebSocket nhận tiến trình realtime.
 *
 * KHÔNG polling API để lấy tiến trình — worker publish lên Redis, API broadcast
 * xuống đây.
 */

import { useEffect, useRef, useState } from "react";
import { WS_URL } from "./api";
import type { PipelineStep, VideoStatus, WsEvent } from "./types";

export interface VideoProgress {
  step: PipelineStep;
  percent: number;
  note?: string;
}

export interface WsState {
  connected: boolean;
  progress: Record<string, VideoProgress>;
  statuses: Record<string, { status: VideoStatus; step: PipelineStep | null }>;
  lastAlert: { level: string; title: string; detail?: string } | null;
}

export function useReupSocket(onStatusChange?: () => void): WsState {
  const [state, setState] = useState<WsState>({
    connected: false,
    progress: {},
    statuses: {},
    lastAlert: null,
  });
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callbackRef = useRef(onStatusChange);
  callbackRef.current = onStatusChange;

  useEffect(() => {
    let closed = false;

    const connect = () => {
      if (closed) return;
      const socket = new WebSocket(WS_URL);
      socketRef.current = socket;

      socket.onopen = () => setState((s) => ({ ...s, connected: true }));

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

  return state;
}
