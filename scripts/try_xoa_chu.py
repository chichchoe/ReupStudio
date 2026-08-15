#!/usr/bin/env python3
"""Dò chữ trên video thật rồi VẼ KHUNG lên ảnh để mắt người kiểm bộ lọc.

Bộ lọc quyết định vùng nào bị xoá. Test tự động chỉ khoá được hành vi trên dữ
liệu tự bịa; cái duy nhất nói được nó đúng hay sai trên video thật là nhìn ảnh.

    python scripts/try_xoa_chu.py <video.mp4>
    python scripts/try_xoa_chu.py <video.mp4> --giay 60 --so-khung 8
    python scripts/try_xoa_chu.py <video.mp4> --diem-can-xoa 2.2   # thử ngưỡng khác

Quy ước màu trên ảnh xuất ra:

    ĐỎ    vùng SẼ BỊ XOÁ      — soi kỹ: có vùng nào là mặt người, hoạ tiết áo,
                                biển hiệu, bao bì không?
    XANH  vùng OCR đọc được nhưng bộ lọc GIỮ LẠI — có phụ đề nào lọt lưới không?

Hai câu hỏi đó là toàn bộ mục đích của script này. Xoá sót thì người dùng thấy
ngay và sửa tay được; xoá nhầm thì hỏng video mà không ai biết cho tới khi đã
đăng — nên nhìn kỹ vùng ĐỎ hơn vùng xanh.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "worker"))

from src.pipeline.masking.kieu import TextBox
from src.pipeline.masking.loc import NguongLoc, loc_vung_can_xoa
from src.pipeline.masking.ocr import doc_khung, lay_mau_khung

THU_MUC_RA = REPO / "media" / "tmp" / "try_xoa_chu"

DO = (60, 60, 220)
XANH = (120, 190, 120)


def _ve_khung(anh, vung, mau, nhan: str) -> None:
    import cv2

    cao, rong = anh.shape[:2]
    x1 = int(vung[0] * rong)
    y1 = int(vung[1] * cao)
    x2 = int((vung[0] + vung[2]) * rong)
    y2 = int((vung[1] + vung[3]) * cao)

    cv2.rectangle(anh, (x1, y1), (x2, y2), mau, 2)
    #: Nhãn đặt PHÍA TRÊN khung, tụt xuống trong khung nếu chạm mép trên —
    #: nhãn nằm ngoài ảnh thì coi như không có nhãn.
    y_nhan = y1 - 6 if y1 > 20 else y2 + 16
    cv2.putText(
        anh, nhan, (x1, y_nhan), cv2.FONT_HERSHEY_SIMPLEX, 0.45, mau, 1, cv2.LINE_AA
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument(
        "--giay", type=float, default=0.0, help="bắt đầu từ giây thứ mấy"
    )
    parser.add_argument("--so-khung", type=int, default=6, help="xuất bao nhiêu ảnh")
    parser.add_argument(
        "--diem-can-xoa", type=float, default=None, help="thử ngưỡng khác"
    )
    args = parser.parse_args()

    if not args.video.exists():
        raise SystemExit(f"Không thấy video: {args.video}")

    nguong = NguongLoc()
    if args.diem_can_xoa is not None:
        nguong = NguongLoc(diem_can_xoa=args.diem_can_xoa)

    import cv2

    # --- Dò trên một đoạn, KHÔNG dò cả video: 0,11 giây mỗi khung, video 34
    #     phút mất hàng giờ mà không thêm thông tin gì cho việc soi bằng mắt.
    print(f"Dò chữ từ giây {args.giay:.0f}, {args.so_khung} khung…")
    khung: list[tuple[float, object]] = []
    boxes: list[TextBox] = []
    for thoi_diem, anh in lay_mau_khung(args.video):
        if thoi_diem < args.giay:
            continue
        if len(khung) >= args.so_khung:
            break
        doc_duoc = doc_khung(anh, thoi_diem)
        boxes.extend(doc_duoc)
        khung.append((thoi_diem, anh))
        print(f"  giây {thoi_diem:6.1f}  {len(doc_duoc)} vùng chữ")

    if not boxes:
        raise SystemExit("Không đọc được vùng chữ nào — thử đoạn khác bằng --giay.")

    can_xoa = loc_vung_can_xoa(boxes, nguong)

    print(
        f"\nTổng {len(boxes)} vùng chữ đọc được -> {len(can_xoa)} vùng bị lọc là ĐÁNG XOÁ"
    )
    for v in can_xoa:
        print(f"  điểm {v.diem:.2f}  y={v.y:.0%}  {v.bat_dau:.1f}-{v.ket_thuc:.1f}s")
        for ly_do in v.ly_do:
            print(f"      · {ly_do}")

    THU_MUC_RA.mkdir(parents=True, exist_ok=True)
    for chi_so, (thoi_diem, anh) in enumerate(khung, start=1):
        ve = anh.copy()

        for b in boxes:
            if abs(b.time - thoi_diem) > 0.01:
                continue
            trong_vung_xoa = any(
                v.bat_dau - 0.01 <= b.time <= v.ket_thuc + 0.01
                and b.giao_nhau(TextBox(b.time, v.x, v.y, v.w, v.h, "", 1.0)) > 0.3
                for v in can_xoa
            )
            mau = DO if trong_vung_xoa else XANH
            nhan = f"{b.confidence:.2f} {b.text[:14]}"
            _ve_khung(ve, (b.x, b.y, b.w, b.h), mau, nhan)

        ra = THU_MUC_RA / f"khung_{chi_so:02d}_{thoi_diem:07.1f}s.png"
        cv2.imwrite(str(ra), ve)

    print("\nĐỎ = sẽ bị xoá · XANH = giữ lại")
    print(f"Mở thư mục để soi: {THU_MUC_RA}")


if __name__ == "__main__":
    main()
