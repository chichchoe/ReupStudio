"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { api } from "@/lib/api";
import { TARGET_PLATFORM_LABEL, type TargetPlatform } from "@/lib/types";

interface Props {
  selectedCount: number;
  /** true khi đang chờ một bulk mutation khác trả lời — chặn bấm chồng thao tác. */
  pending?: boolean;
  onApprove: () => void;
  onRetry: () => void;
  onDelete: () => void;
  onApplyPreset: (presetId: string) => void;
  /**
   * Đánh dấu TAY những video người dùng đã tự đăng lên nền tảng. Chặng đăng tự
   * động (M5) chưa có, nên đây là chỗ duy nhất ghi lại việc đó.
   *
   * Không truyền thì nút không hiện — tab "Chờ dịch" chưa có bản dựng nên
   * không đăng được gì.
   */
  onMarkPosted?: (platforms: TargetPlatform[]) => void;
  /**
   * Chỉ tab "Chờ dịch" truyền hai prop dưới đây. Không truyền thì phần dịch
   * hàng loạt không hiện — video ở trạng thái khác `review` không dịch được.
   */
  translateModels?: string[];
  onTranslate?: (llmModel: string) => void;
}

/** Thanh hành động hàng loạt sticky ở đáy trang Thư viện, hiện khi có video được chọn. */
export function BulkActionBar({
  selectedCount,
  pending,
  onApprove,
  onRetry,
  onDelete,
  onApplyPreset,
  onMarkPosted,
  translateModels = [],
  onTranslate,
}: Props) {
  // Preset áp cho video chỉ lấy kind="process" — backend từ chối kind khác.
  const { data: presets } = useQuery({
    queryKey: ["presets", "process"],
    queryFn: () => api.listPresets("process"),
  });
  const [presetId, setPresetId] = useState("");
  // Giống dropdown ở từng dòng: mặc định model đầu danh sách, tính khi render để
  // không phải đồng bộ state khi danh sách model về muộn.
  const [chosenModel, setChosenModel] = useState("");
  const llmModel = chosenModel || translateModels[0] || "";

  //: Hộp tích nền tảng mở ra ngay trên thanh, không phải modal: đánh dấu là
  //: thao tác nhanh làm liên tục, bắt qua một hộp thoại toàn màn hình mỗi lần
  //: là quá nặng tay.
  const [moChonNenTang, setMoChonNenTang] = useState(false);
  const [nenTang, setNenTang] = useState<Set<TargetPlatform>>(new Set());
  const tichNenTang = (ma: TargetPlatform) =>
    setNenTang((cu) => {
      const moi = new Set(cu);
      if (moi.has(ma)) moi.delete(ma);
      else moi.add(ma);
      return moi;
    });

  if (selectedCount === 0) return null;

  return (
    <div className="sticky bottom-0 mt-3">
      {/* Hộp tích nền tảng nằm TRÊN thanh hành động: mở xuống dưới thì nó rơi
          ra ngoài đáy màn hình vì thanh đã dính đáy. */}
      {onMarkPosted && moChonNenTang && (
        <div className="mb-2 rounded-xl border border-accent/30 bg-panel2 px-4 py-3">
          <div className="text-[12.5px] font-medium">
            Đã đăng {selectedCount} video này lên đâu?
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
            {(Object.keys(TARGET_PLATFORM_LABEL) as TargetPlatform[]).map((ma) => (
              <label key={ma} className="flex items-center gap-1.5 text-[12px]">
                <input
                  type="checkbox"
                  checked={nenTang.has(ma)}
                  onChange={() => tichNenTang(ma)}
                  className="h-3.5 w-3.5 accent-[color:var(--accent,#5B8CFF)]"
                />
                {TARGET_PLATFORM_LABEL[ma]}
              </label>
            ))}
            <button
              className="btn btn-primary btn-sm ml-auto"
              disabled={pending || nenTang.size === 0}
              onClick={() => {
                onMarkPosted([...nenTang]);
                setNenTang(new Set());
                setMoChonNenTang(false);
              }}
            >
              Đánh dấu đã đăng
            </button>
          </div>
          {/* Đánh dấu lần hai GỘP thêm nền tảng chứ không ghi đè — nói rõ để
              người dùng dám bấm lại khi đăng nốt nơi còn thiếu. */}
          <p className="mt-2 text-[11px] text-muted">
            Đánh dấu lại lần nữa sẽ cộng thêm nền tảng, không xoá dấu cũ.
          </p>
        </div>
      )}

      <div className="flex items-center gap-2.5 bg-panel2 border border-accent/30 rounded-xl px-4 py-3 shadow-[0_-6px_26px_rgba(0,0,0,0.4)] flex-wrap">
      <span className="text-[13px] font-medium">Đã chọn {selectedCount} video</span>

      {onTranslate && (
        <>
          <select
            className="input py-1"
            value={llmModel}
            disabled={translateModels.length === 0}
            onChange={(e) => setChosenModel(e.target.value)}
            aria-label="Chọn model AI để dịch các video đã chọn"
          >
            {translateModels.length === 0 && <option value="">Chưa có model</option>}
            {translateModels.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <button
            className="btn btn-primary btn-sm"
            disabled={pending || !llmModel}
            onClick={() => onTranslate(llmModel)}
          >
            Dịch với AI…
          </button>
        </>
      )}

      <button className="btn btn-sm" disabled={pending} onClick={onApprove}>
        ✓ Duyệt
      </button>

      <button className="btn btn-sm" disabled={pending} onClick={onRetry}>
        Xử lý lại
      </button>

      {onMarkPosted && (
        <button
          className={clsx("btn btn-sm", moChonNenTang && "btn-primary")}
          disabled={pending}
          onClick={() => setMoChonNenTang((v) => !v)}
        >
          📤 Đã đăng…
        </button>
      )}

      <select
        className="input py-1"
        value={presetId}
        onChange={(e) => setPresetId(e.target.value)}
        aria-label="Chọn preset xử lý để áp cho video đã chọn"
      >
        <option value="">Chọn preset xử lý…</option>
        {presets?.map((preset) => (
          <option key={preset.id} value={preset.id}>
            {preset.name}
          </option>
        ))}
      </select>
      <button
        className="btn btn-sm"
        disabled={pending || !presetId}
        onClick={() => {
          onApplyPreset(presetId);
          setPresetId("");
        }}
      >
        Áp preset
      </button>

      <button
        className="btn btn-sm text-err border-err/35 ml-auto"
        disabled={pending}
        onClick={onDelete}
      >
        Xoá
      </button>
      </div>
    </div>
  );
}
