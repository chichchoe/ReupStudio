#!/usr/bin/env python3
"""Vá thật một đoạn video rồi xuất ảnh GHÉP trước/sau để mắt người kiểm.

Đây là phép kiểm quyết định của M3. Hai câu hỏi nó trả lời:

1. **Chữ có biến mất không, và hình phía sau có còn nguyên không?**
   Nhìn ảnh ghép: nửa trái là bản gốc, nửa phải là bản đã vá.

2. **Vá một khung mất bao lâu?** Con số này quyết định M3 có dùng được cho
   video dài hay không. Ước lượng trong spec dựa trên giả định MỘT vùng mỗi
   khung; video thật có nhiều vùng chồng nhau nên đắt hơn hẳn.

    python scripts/try_va_chu.py <video.mp4>
    python scripts/try_va_chu.py <video.mp4> --giay 60 --so-khung 10
    python scripts/try_va_chu.py <video.mp4> --cv2      # so với phương án dự phòng

Lần chạy đầu tiên tải model LaMa (~200 MB). Nếu hỏng với
CERTIFICATE_VERIFY_FAILED thì chạy kèm:

    SSL_CERT_FILE=$(python -c "import certifi; print(certifi.where())") \\
        python scripts/try_va_chu.py ...
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "worker"))

from src.pipeline.masking.loc import NguongLoc, loc_vung_can_xoa
from src.pipeline.masking.ocr import doc_khung, lay_mau_khung
from src.pipeline.masking.timeline import dung_mask
from src.pipeline.masking.vaa import mask_dang_hien, va_khung

THU_MUC_RA = REPO / "media" / "tmp" / "try_va_chu"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--giay", type=float, default=0.0)
    parser.add_argument("--so-khung", type=int, default=6)
    parser.add_argument("--cv2", action="store_true", help="dùng cv2.inpaint thay LaMa")
    args = parser.parse_args()

    if not args.video.exists():
        raise SystemExit(f"Không thấy video: {args.video}")

    import cv2
    import numpy as np

    # --- Dò trên một đoạn dài hơn phần sẽ vá: mask cần vài khung liên tiếp mới
    #     đủ tín hiệu bền vị trí, dò đúng bằng số khung sẽ vá thì mask nào cũng
    #     quá ngắn để qua được bộ lọc.
    print(f"1/3  Dò chữ từ giây {args.giay:.0f}…")
    boxes = []
    khung: list[tuple[float, object]] = []
    for thoi_diem, anh in lay_mau_khung(args.video):
        if thoi_diem < args.giay:
            continue
        if thoi_diem > args.giay + 12:
            break
        boxes.extend(doc_khung(anh, thoi_diem))
        if len(khung) < args.so_khung:
            khung.append((thoi_diem, anh))

    if not boxes:
        raise SystemExit("Không đọc được vùng chữ nào — thử đoạn khác bằng --giay.")

    masks = dung_mask(loc_vung_can_xoa(boxes, NguongLoc()))
    print(f"2/3  {len(boxes)} vùng chữ -> {len(masks)} mask")
    for m in masks:
        print(
            f"       {m.bat_dau:6.2f}-{m.ket_thuc:6.2f}s  y={m.y:.0%}  {m.w * m.h:.1%} khung"
        )

    if not masks:
        raise SystemExit("Bộ lọc không giữ lại mask nào — không có gì để vá.")

    print(f"3/3  Vá {len(khung)} khung bằng {'cv2.inpaint' if args.cv2 else 'LaMa'}…")
    THU_MUC_RA.mkdir(parents=True, exist_ok=True)

    thoi_gian: list[float] = []
    for chi_so, (thoi_diem, anh) in enumerate(khung, start=1):
        dang_hien = mask_dang_hien(masks, thoi_diem)

        bat_dau = time.perf_counter()
        da_va = va_khung(anh, masks, thoi_diem, dung_lama=not args.cv2)
        het = time.perf_counter() - bat_dau
        thoi_gian.append(het)

        #: Ghép dọc trước/sau, kèm vạch ngăn để mắt bắt ngay ranh giới.
        vach = np.full((6, anh.shape[1], 3), 40, dtype=np.uint8)
        ghep = np.vstack([anh, vach, da_va])
        ra = THU_MUC_RA / f"va_{chi_so:02d}_{thoi_diem:07.1f}s.png"
        cv2.imwrite(str(ra), ghep)
        print(f"       giây {thoi_diem:6.1f}  {len(dang_hien)} mask  {het:5.2f}s")

    # --- Con số quyết định M3 có dùng được cho video dài hay không.
    #
    #     BỎ khung đầu tiên: lần gọi đầu còn gánh phần nạp model và khởi động
    #     Metal, gấp 3-4 lần các khung sau. Tính cả vào thì ước lượng cho video
    #     dài sai hẳn về phía bi quan.
    #
    #     Dùng FPS THẬT của video, không mặc định 30: video Douyin đo được là
    #     25 fps, chênh 20% so với giả định.
    thuc = thoi_gian[1:] or thoi_gian
    tb = sum(thuc) / len(thuc)
    fps = cv2.VideoCapture(str(args.video)).get(cv2.CAP_PROP_FPS) or 30.0
    print(f"\nTrung bình {tb:.3f} s/khung ({fps:.0f} fps, đã bỏ khung khởi động)")
    for phut, ten in ((3, "video 3 phút"), (34, "video 34 phút")):
        giay = phut * 60 * fps * tb
        print(
            f"   {ten:14} ~{giay / 60:6.1f} phút xử lý   ({giay / (phut * 60):.1f}x thời lượng)"
        )

    print("\nTRÊN = bản gốc · DƯỚI = đã vá")
    print(f"Mở thư mục để soi: {THU_MUC_RA}")


if __name__ == "__main__":
    main()
