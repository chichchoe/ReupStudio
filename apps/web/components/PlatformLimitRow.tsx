"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { TARGET_PLATFORM_LABEL, type PlatformLimit, type SafeArea } from "@/lib/types";
import { validatePlatformLimitDraft, type PlatformLimitDraft } from "@/lib/validatePlatformLimit";
import { parseDecimal, SafeAreaCells, toSafeAreaText } from "./SafeAreaCells";

/** Màu chấm nền tảng — lấy đúng biến đã định nghĩa trong tailwind.config, không mã màu thô. */
const PLATFORM_DOT: Record<string, string> = {
  tiktok: "bg-tiktok",
  youtube: "bg-yt",
  facebook: "bg-fb",
  instagram: "bg-ig",
};

function toDraft(limit: PlatformLimit): PlatformLimitDraft {
  return {
    max_duration_sec: limit.max_duration_sec,
    max_title_len: limit.max_title_len,
    max_desc_len: limit.max_desc_len,
    max_hashtags: limit.max_hashtags,
    safe_daily_posts: limit.safe_daily_posts,
    safe_area: { ...limit.safe_area },
    notes: limit.notes,
  };
}

function draftsEqual(a: PlatformLimitDraft, b: PlatformLimitDraft): boolean {
  return (
    a.max_duration_sec === b.max_duration_sec &&
    a.max_title_len === b.max_title_len &&
    a.max_desc_len === b.max_desc_len &&
    a.max_hashtags === b.max_hashtags &&
    a.safe_daily_posts === b.safe_daily_posts &&
    a.notes === b.notes &&
    a.safe_area.top === b.safe_area.top &&
    a.safe_area.bottom === b.safe_area.bottom &&
    a.safe_area.left === b.safe_area.left &&
    a.safe_area.right === b.safe_area.right
  );
}

interface Props {
  limit: PlatformLimit;
  previewed: boolean;
  onFocusRow: (platform: string) => void;
  onSafeAreaDraftChange: (platform: string, safeArea: SafeArea) => void;
}

/** Một dòng nền tảng, sửa trực tiếp tại chỗ — bấm "Lưu" gọi `PATCH /platform-limits/{platform}`. */
export function PlatformLimitRow({ limit, previewed, onFocusRow, onSafeAreaDraftChange }: Props) {
  const [draft, setDraft] = useState<PlatformLimitDraft>(() => toDraft(limit));
  // Chuỗi RAW đang gõ cho 4 ô safe_area, tách khỏi `draft.safe_area` (số đã
  // parse) — để giữ nguyên ký tự người dùng gõ dở (VD "0.") thay vì bị ép về
  // lại "0" mỗi lần render do parse thất bại giữa chừng.
  const [safeAreaText, setSafeAreaText] = useState(() => toSafeAreaText(limit.safe_area));
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // Chỉ đồng bộ lại draft khi CHÍNH dòng này vừa lưu xong (updated_at đổi) —
  // không reset draft khi query refetch do lưu MỘT dòng khác, tránh mất chữ
  // người dùng đang gõ dở.
  useEffect(() => {
    setDraft(toDraft(limit));
    setSafeAreaText(toSafeAreaText(limit.safe_area));
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit.updated_at]);

  const dirty = !draftsEqual(draft, toDraft(limit));

  const mutation = useMutation({
    mutationFn: () =>
      api.updatePlatformLimit(limit.platform, {
        max_duration_sec: draft.max_duration_sec,
        max_title_len: draft.max_title_len,
        max_desc_len: draft.max_desc_len,
        max_hashtags: draft.max_hashtags,
        safe_daily_posts: draft.safe_daily_posts,
        safe_area: draft.safe_area,
        notes: draft.notes,
      }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["platform-limits"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Lưu thất bại"),
  });

  const save = () => {
    const invalid = validatePlatformLimitDraft(draft);
    if (invalid) {
      setError(invalid);
      return;
    }
    mutation.mutate();
  };

  /** Luôn cập nhật chuỗi hiển thị; chỉ cập nhật số/preview khi parse được. */
  const setSafeAreaRaw = (key: keyof SafeArea, raw: string) => {
    setSafeAreaText({ ...safeAreaText, [key]: raw });
    const parsed = parseDecimal(raw);
    if (parsed === null) return;
    const next = { ...draft.safe_area, [key]: parsed };
    setDraft({ ...draft, safe_area: next });
    onSafeAreaDraftChange(limit.platform, next);
  };

  const numInput = (
    value: number,
    onChange: (v: number) => void,
    props: { min?: number; step?: number } = {},
  ) => (
    <input
      type="number"
      className="input w-16 py-1 px-2 text-[12px]"
      value={value}
      min={props.min ?? 0}
      step={props.step ?? 1}
      onFocus={() => onFocusRow(limit.platform)}
      onChange={(e) => onChange(Number(e.target.value))}
    />
  );

  return (
    <tr className={previewed ? "bg-accent/[0.04]" : undefined}>
      <td className="px-2 py-2 whitespace-nowrap">
        <span className="inline-flex items-center gap-1.5 text-[12.5px] font-medium">
          <span className={`w-2 h-2 rounded-full ${PLATFORM_DOT[limit.platform] ?? "bg-accent"}`} />
          {TARGET_PLATFORM_LABEL[limit.platform as keyof typeof TARGET_PLATFORM_LABEL] ??
            limit.platform}
        </span>
      </td>
      <td className="px-2 py-2">
        {numInput(draft.max_duration_sec, (v) => setDraft({ ...draft, max_duration_sec: v }))}
        <div className="text-[10px] text-muted mt-0.5">0 = không giới hạn</div>
      </td>
      <td className="px-2 py-2">
        {numInput(draft.max_title_len, (v) => setDraft({ ...draft, max_title_len: v }))}
      </td>
      <td className="px-2 py-2">
        {numInput(draft.max_desc_len, (v) => setDraft({ ...draft, max_desc_len: v }))}
      </td>
      <td className="px-2 py-2">
        {numInput(draft.max_hashtags, (v) => setDraft({ ...draft, max_hashtags: v }))}
      </td>
      <td className="px-2 py-2">
        {numInput(draft.safe_daily_posts, (v) => setDraft({ ...draft, safe_daily_posts: v }))}
      </td>
      <td className="px-2 py-2">
        <SafeAreaCells
          text={safeAreaText}
          onFocus={() => onFocusRow(limit.platform)}
          onChange={setSafeAreaRaw}
        />
      </td>
      <td className="px-2 py-2">
        <input
          className="input w-40 py-1 px-2 text-[12px]"
          value={draft.notes ?? ""}
          onFocus={() => onFocusRow(limit.platform)}
          onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
        />
      </td>
      <td className="px-2 py-2 align-top">
        <button
          className="btn btn-sm"
          disabled={!dirty || mutation.isPending}
          onClick={save}
        >
          {mutation.isPending ? "Đang lưu…" : "Lưu"}
        </button>
        {error && <div className="text-[10.5px] text-err mt-1 max-w-[160px]">{error}</div>}
      </td>
    </tr>
  );
}
