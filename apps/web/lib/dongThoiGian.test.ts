import { describe, expect, it } from "vitest";
import {
  biEpNhanh,
  cauDangPhat,
  coTran,
  daiGiongSauEp,
  demVanDe,
  nhanGiay,
  pxSangGiay,
  viTriKhoi,
  type CapDoiChieu,
} from "./dongThoiGian";

const c = (i: number, start: number, end: number, extra: Partial<CapDoiChieu> = {}): CapDoiChieu => ({
  i, start, end, dich: `câu ${i}`, goc: "", sua_tay: false,
  giong_giay: null, cho_trong_giay: 0, he_so_toc_do: 1, tran_giay: 0, ...extra,
});

// Ba câu, CÓ khoảng lặng giữa câu 1 và câu 2 — phụ đề thật luôn có khoảng hở.
const CUES = [c(0, 0, 1), c(1, 1, 2), c(2, 3, 4)];

describe("cauDangPhat", () => {
  it("trả câu đang phát", () => {
    expect(cauDangPhat(CUES, 0.5)).toBe(0);
    expect(cauDangPhat(CUES, 1.5)).toBe(1);
    expect(cauDangPhat(CUES, 3.5)).toBe(2);
  });

  it("trong khoảng lặng thì không câu nào", () => {
    expect(cauDangPhat(CUES, 2.5)).toBe(-1);
  });

  it("trước câu đầu và sau câu cuối thì không câu nào", () => {
    expect(cauDangPhat(CUES, -1)).toBe(-1);
    expect(cauDangPhat(CUES, 99)).toBe(-1);
  });

  it("đúng biên: start tính vào câu, end thì không", () => {
    // Không thế thì ở giây 1.0 cả hai câu cùng sáng.
    expect(cauDangPhat(CUES, 1)).toBe(1);
    expect(cauDangPhat(CUES, 2)).toBe(-1);
  });

  it("danh sách rỗng", () => {
    expect(cauDangPhat([], 1)).toBe(-1);
  });

  it("tua ngược vẫn đúng — không giữ trạng thái giữa các lần gọi", () => {
    expect(cauDangPhat(CUES, 3.5)).toBe(2);
    expect(cauDangPhat(CUES, 0.5)).toBe(0);
  });
});

describe("viTriKhoi", () => {
  it("đổi giây sang pixel theo mức phóng to", () => {
    expect(viTriKhoi(2, 1.5, 40)).toEqual({ left: 80, width: 60 });
  });

  it("câu rất ngắn vẫn còn bề rộng nhìn thấy được", () => {
    // 0,3 giây ở 2px/giây ra 0,6px — làm tròn xuống 0 là khối biến mất và
    // người dùng tưởng mất câu.
    expect(viTriKhoi(0, 0.3, 2).width).toBe(2);
  });

  it("đi và về khớp nhau", () => {
    const px = viTriKhoi(7.25, 1, 40).left;
    expect(pxSangGiay(px, 40)).toBeCloseTo(7.25);
  });

  it("pxMoiGiay bằng 0 thì không chia cho 0", () => {
    expect(pxSangGiay(100, 0)).toBe(0);
  });

  it("pixel âm không cho ra giây âm", () => {
    expect(pxSangGiay(-50, 40)).toBe(0);
  });
});

describe("daiGiongSauEp", () => {
  it("chưa lồng tiếng thì bằng 0", () => {
    expect(daiGiongSauEp(c(0, 0, 1))).toBe(0);
  });

  it("ép nhanh 1,5 lần thì ngắn lại tương ứng", () => {
    // Vẽ độ dài GỐC sẽ báo tràn ở cả những câu đã được ép cho vừa.
    expect(daiGiongSauEp(c(0, 0, 1, { giong_giay: 3, he_so_toc_do: 1.5 }))).toBe(2);
  });

  it("hệ số dưới 1 không kéo dài câu ra", () => {
    expect(daiGiongSauEp(c(0, 0, 1, { giong_giay: 2, he_so_toc_do: 0.5 }))).toBe(2);
  });
});

describe("cảnh báo", () => {
  it("tràn nhỏ hơn ngưỡng thì không tính — lệch vài phần trăm giây không ai nghe ra", () => {
    expect(coTran(c(0, 0, 1, { tran_giay: 0.02 }))).toBe(false);
    expect(coTran(c(0, 0, 1, { tran_giay: 0.4 }))).toBe(true);
  });

  it("chạm trần tốc độ thì báo ép nhanh", () => {
    expect(biEpNhanh(c(0, 0, 1, { he_so_toc_do: 1.5 }))).toBe(true);
    expect(biEpNhanh(c(0, 0, 1, { he_so_toc_do: 1.2 }))).toBe(false);
  });

  it("đếm được số câu có vấn đề", () => {
    const ds = [
      c(0, 0, 1, { tran_giay: 0.4, he_so_toc_do: 1.5 }),
      c(1, 1, 2, { he_so_toc_do: 1.5 }),
      c(2, 2, 3),
    ];
    expect(demVanDe(ds)).toEqual({ tran: 1, epNhanh: 2 });
  });
});

describe("nhanGiay", () => {
  it("định dạng m:ss", () => {
    expect(nhanGiay(0)).toBe("0:00");
    expect(nhanGiay(65)).toBe("1:05");
    expect(nhanGiay(603)).toBe("10:03");
  });
});
