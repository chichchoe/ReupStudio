/**
 * Hàm thuần cho dòng thời gian ở màn duyệt bản dịch.
 *
 * Tách khỏi React để test được: đây là chỗ dễ sai nhất — biên câu, khoảng lặng
 * giữa hai câu, tua ngược, và phép đổi giây ↔ pixel khi phóng to thu nhỏ.
 * CLAUDE.md bắt buộc test tự động cho mọi phép chuyển đổi toạ độ.
 */

/** Một dòng bảng đối chiếu, đúng hình dạng `/videos/{id}/doi-chieu` trả về. */
export interface CapDoiChieu {
  i: number;
  start: number;
  end: number;
  dich: string;
  goc: string;
  sua_tay: boolean;
  /** Độ dài thật của giọng đã đọc, giây. `null` khi chưa lồng tiếng. */
  giong_giay: number | null;
  /** Chỗ trống tới lúc câu SAU bắt đầu — không phải tới lúc câu này kết thúc. */
  cho_trong_giay: number;
  /** Phải đọc nhanh gấp bao nhiêu mới vừa. Chạm 1,5 là đã hết cỡ. */
  he_so_toc_do: number;
  /** Còn tràn bao nhiêu giây sang câu sau sau khi ép hết cỡ. 0 là vừa. */
  tran_giay: number;
}

/** Tràn dưới mức này thì không bôi đỏ — lệch vài phần trăm giây không ai nghe ra. */
export const NGUONG_TRAN_GIAY = 0.05;

/** Hệ số ép từ mức này trở lên là đã chạm trần, câu đọc nhanh tới mức khó nghe. */
export const NGUONG_EP_NHANH = 1.49;

/**
 * Chỉ số MẢNG của câu đang phát ở giây `giay`, hoặc -1 nếu không câu nào.
 *
 * Trả chỉ số mảng chứ không trả `i`: dòng thời gian cần lấy ra đúng phần tử,
 * mà `i` có thể không liên tục sau khi dịch lại.
 *
 * Biên: `start` tính vào câu, `end` thì KHÔNG. Không thế thì ở đúng giây giao
 * nhau hai câu cùng sáng.
 *
 * Tìm nhị phân vì hàm này chạy mỗi `timeupdate` (khoảng 4 lần/giây) trên danh
 * sách tới 672 câu, và KHÔNG giữ trạng thái giữa các lần gọi — tua ngược phải
 * cho kết quả đúng như tua tới.
 */
export function cauDangPhat(cues: CapDoiChieu[], giay: number): number {
  let thap = 0;
  let cao = cues.length - 1;

  while (thap <= cao) {
    const giua = (thap + cao) >> 1;
    const cue = cues[giua];
    if (giay < cue.start) cao = giua - 1;
    else if (giay >= cue.end) thap = giua + 1;
    else return giua;
  }

  return -1;
}

/** Vị trí và bề rộng của một khối trên dòng thời gian, đơn vị pixel. */
export interface ViTriKhoi {
  left: number;
  width: number;
}

/**
 * Đổi khoảng thời gian thành vị trí pixel.
 *
 * Bề rộng tối thiểu 2px: câu 0,3 giây ở mức thu nhỏ chỉ ra 0,6px — làm tròn
 * xuống 0 là khối biến mất và người dùng tưởng mất câu.
 */
export function viTriKhoi(batDau: number, dai: number, pxMoiGiay: number): ViTriKhoi {
  return {
    left: batDau * pxMoiGiay,
    width: Math.max(2, dai * pxMoiGiay),
  };
}

/** Đổi vị trí pixel trên dòng thời gian ngược lại thành giây. */
export function pxSangGiay(px: number, pxMoiGiay: number): number {
  return pxMoiGiay > 0 ? Math.max(0, px / pxMoiGiay) : 0;
}

/**
 * Độ dài giọng SAU KHI ép nhanh — đây mới là thứ nghe thấy trên video.
 *
 * Vẽ độ dài gốc lên dòng thời gian sẽ báo tràn ở cả những câu bước xếp lịch
 * đã ép cho vừa rồi.
 */
export function daiGiongSauEp(cue: CapDoiChieu): number {
  if (!cue.giong_giay) return 0;
  return cue.giong_giay / Math.max(1, cue.he_so_toc_do);
}

/** Câu này có tràn sang câu sau không, sau khi đã ép nhanh hết cỡ. */
export function coTran(cue: CapDoiChieu): boolean {
  return cue.tran_giay > NGUONG_TRAN_GIAY;
}

/** Câu này có đang bị đọc nhanh tới mức khó nghe không. */
export function biEpNhanh(cue: CapDoiChieu): boolean {
  return cue.he_so_toc_do >= NGUONG_EP_NHANH;
}

/** Đếm số câu có vấn đề, để hiện ngay trên đầu dòng thời gian. */
export function demVanDe(cues: CapDoiChieu[]): { tran: number; epNhanh: number } {
  return {
    tran: cues.filter(coTran).length,
    epNhanh: cues.filter(biEpNhanh).length,
  };
}

/** Đổi giây thành `m:ss` để hiện trên thước thời gian. */
export function nhanGiay(giay: number): string {
  const phut = Math.floor(giay / 60);
  const giay_le = Math.floor(giay % 60);
  return `${phut}:${String(giay_le).padStart(2, "0")}`;
}
