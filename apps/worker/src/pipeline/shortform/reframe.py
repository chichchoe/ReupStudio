"""Đổi video ngang sang dọc 9:16, không cắt mất đầu nhân vật (M4-WK-01).

Video nguồn từ nền tảng Trung Quốc phần lớn quay ngang 16:9; đích cuối luôn là
dọc 9:16 (xem CLAUDE.md — "Video dọc 9:16 là mặc định"). Hai chế độ đổi khung:

- ``reframe_blur`` (mặc định, KHÔNG cần OpenCV): scale video gốc vừa bề ngang
  và bề dọc khung đích (giữ nguyên tỉ lệ, không cắt gì), nền phía sau là chính
  video đó phóng to phủ kín khung đích rồi làm mờ (``boxblur``), ghép chồng
  bản rõ ở giữa. Không bao giờ cắt mất chủ thể vì giữ nguyên toàn bộ khung
  ngang gốc — an toàn tuyệt đối, đánh đổi bằng viền mờ hai bên (hoặc trên/dưới
  tuỳ tỉ lệ video gốc).
- ``reframe_crop`` (bám chủ thể): dò cột chứa chủ thể bằng ``subject_column``
  rồi cắt một dải dọc quanh nó, phóng to lấp đầy khung đích. Đẹp hơn ``blur``
  (không viền mờ) nhưng có rủi ro cắt hụt nếu chủ thể di chuyển ra ngoài dải
  đã chọn giữa các mốc lấy mẫu.

``subject_column`` là hàm THUẦN (không đụng ffmpeg/DB/celery): nhận sẵn mảng
khung xám (numpy, 2 chiều, dạng trích bằng
``ffmpeg/frames.py::extract_gray_frames``) — không tự trích khung, không biết
gì về file. Nhờ vậy test được bằng mảng tự sinh, không cần ffmpeg (xem
``tests/test_reframe.py``).

Cách dò chủ thể: KHÔNG dùng model học sâu (ngoài phạm vi, ngoài danh sách thư
viện đã chốt trong ``docs/01-KIEN-TRUC-VA-STACK.md``), và **KHÔNG dùng OpenCV**
dù package ``opencv-python`` có mặt trong ``pyproject.toml`` (xem comment ở đó
— thêm sẵn cho M3, chưa ai `import cv2` ở M4). ``subject_column`` chỉ dùng
numpy thuần: phương sai theo thời gian — vùng chuyển động nhiều giữa các khung
liên tiếp = chủ thể. Lý do không dùng ``cv2.saliency`` (phương án "nếu có" nêu
trong brief): module đó thuộc ``opencv-contrib-python``, ngoài danh sách đã
chốt, và bản ``opencv-python`` (không phải ``-contrib``) không có module này
(``hasattr(cv2, "saliency") is False`` — đã kiểm trên máy dev). Lấy TRUNG VỊ vị
trí trọng tâm chuyển động qua nhiều cặp khung liên tiếp (không phải trung
bình) để một vài khung nhiễu/giật không kéo lệch kết quả — camera rung nhẹ hay
có người đi ngang qua nền chỉ là ngoại lệ, trung vị bỏ qua được.

Toạ độ trả về LUÔN là phần trăm 0–1 theo bề ngang khung hình (luật số 5 của
plan M4) — không có pixel nào lọt vào giá trị trả về của hàm công khai; đổi
sang pixel chỉ xảy ra ngay sát chỗ dựng filter ffmpeg trong ``reframe_crop``.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
from reup_core.logging import get_logger
from reup_core.paths import tmp_sibling

from ...ffmpeg.frames import extract_gray_frames, sample_timestamps
from ...ffmpeg.probe import probe
from ...ffmpeg.runner import run_ffmpeg

log = get_logger(__name__)

#: Khung đích mặc định — dọc 9:16, theo quy ước "video dọc là mặc định" của dự án.
DEFAULT_OUT_WIDTH = 1080
DEFAULT_OUT_HEIGHT = 1920

#: Vị trí an toàn khi không dò được chuyển động nào (khung tĩnh hoàn toàn) —
#: giữa khung hình, không thiên về bên nào.
DEFAULT_CENTER = 0.5

#: Bán kính (``luma_radius``) của filter ``boxblur`` cho nền mờ ở chế độ blur.
#: ``boxblur`` không có khái niệm sigma (đó là thuật ngữ của Gaussian blur) —
#: chỉ có bán kính hộp trượt + số lần lặp (``luma_power``). Muốn nền mờ hơn thì
#: TĂNG BÁN KÍNH này, đừng tăng số lần lặp — mỗi lần lặp thêm là một lượt quét
#: toàn khung, tốn thời gian tuyến tính theo số lần lặp (xem lịch sử: từng để
#: ``luma_power=20`` — lặp tận 20 lần — khiến reframe_blur mất 8.88s trên clip
#: 6 giây, gấp ~8 lần reframe_crop; hạ về ``luma_power=1`` là đúng chuẩn boxblur
#: một lượt, xem số đo mới trong ``scripts/try_reframe.py`` / báo cáo).
BLUR_RADIUS = 20

#: Số khung / kích thước mỗi khung lấy mẫu để dò chuyển động cho chế độ crop.
#: 128x128 đủ để thấy vùng chuyển động lớn (chủ thể) mà vẫn nhẹ; ép vuông vẫn
#: giữ nguyên phần trăm vị trí theo bề ngang vì scale tuyến tính đều theo mỗi
#: trục, không làm lệch toạ độ tương đối.
SAMPLE_FRAME_SIZE = 128
SAMPLE_FRAME_COUNT = 10


def subject_column(frames: list[np.ndarray], *, out_aspect: float = 9 / 16) -> float:
    """Tâm cột cắt theo phần trăm bề ngang 0–1.

    Lấy trung vị vị trí chủ thể qua nhiều khung để camera không giật. Kẹp kết
    quả sao cho một dải cắt rộng ``out_aspect`` (tỉ lệ khung đích) canh giữa
    tâm này luôn nằm trọn trong khung nguồn — không bao giờ tràn mép.

    ``frames`` cần ít nhất 2 khung để so sánh chuyển động; thiếu khung hoặc
    hoàn toàn tĩnh (không có gì thay đổi giữa các khung) trả về mặc định an
    toàn ``DEFAULT_CENTER`` (giữa khung hình), không ném lỗi.
    """
    if len(frames) < 2:
        return DEFAULT_CENTER

    height, width = frames[0].shape[:2]
    if width <= 0 or height <= 0:
        return DEFAULT_CENTER

    col_idx = np.arange(width, dtype=np.float64)
    positions: list[float] = []
    for prev, curr in pairwise(frames):
        diff = np.abs(curr.astype(np.float64) - prev.astype(np.float64))
        col_energy = diff.sum(axis=0)  # tổng chênh lệch theo từng cột (mọi hàng)
        total = float(col_energy.sum())
        if total <= 0:
            continue  # cặp khung này không đổi gì — không phải chuyển động của chủ thể
        centroid_px = float((col_energy * col_idx).sum() / total)
        positions.append(centroid_px / width)

    center = float(np.median(positions)) if positions else DEFAULT_CENTER

    half_width = _crop_half_width_frac(height, width, out_aspect)
    return min(max(center, half_width), 1 - half_width)


def _crop_half_width_frac(height: int, width: int, out_aspect: float) -> float:
    """Nửa bề rộng dải cắt (phần trăm bề ngang khung nguồn) để kẹp tâm cột.

    Dải cắt cao bằng cả khung nguồn, rộng ``height * out_aspect`` pixel. Nếu
    dải rộng hơn cả khung nguồn (video quá hẹp so với tỉ lệ đích — hiếm, vì
    reframe chỉ áp dụng cho video ngang) thì không có chỗ để kẹp, trả ``0.5``
    để tâm luôn bị ép về giữa (dải chiếm trọn bề ngang khung).
    """
    crop_width_px = height * out_aspect
    half = (crop_width_px / 2) / width
    return min(half, 0.5)


def reframe_blur(
    src: Path,
    dst: Path,
    *,
    out_width: int = DEFAULT_OUT_WIDTH,
    out_height: int = DEFAULT_OUT_HEIGHT,
    timeout: int | None = None,
) -> Path:
    """Đổi ngang sang dọc bằng nền mờ — KHÔNG cần OpenCV, không bao giờ cắt chủ thể.

    Nền: chính video đó phóng to phủ kín khung đích rồi ``boxblur``. Lớp trên:
    video gốc scale vừa bề ngang/dọc khung đích (giữ nguyên tỉ lệ, không cắt
    gì), ghép chồng giữa nền. Idempotent: ghi ra file tạm rồi ``rename``, chạy
    lại cho cùng kết quả (đầu vào không đổi thì đầu ra không đổi).
    """
    fg = f"[0:v]scale={out_width}:{out_height}:force_original_aspect_ratio=decrease,setsar=1[fg]"
    bg = (
        f"[0:v]scale={out_width}:{out_height}:force_original_aspect_ratio=increase,"
        f"crop={out_width}:{out_height},"
        f"boxblur=luma_radius={BLUR_RADIUS}:luma_power=1[bg]"
    )
    overlay = "[bg][fg]overlay=(W-w)/2:(H-h)/2[outv]"
    filter_complex = ";".join([fg, bg, overlay])

    tmp = tmp_sibling(dst)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-i",
        str(src),
        "-filter_complex",
        filter_complex,
        "-map",
        "[outv]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    log.info("reframe.blur", src=src.name, out=f"{out_width}x{out_height}")
    run_ffmpeg(args, timeout=timeout)
    tmp.replace(dst)
    return dst


def reframe_crop(
    src: Path,
    dst: Path,
    *,
    out_width: int = DEFAULT_OUT_WIDTH,
    out_height: int = DEFAULT_OUT_HEIGHT,
    timeout: int | None = None,
) -> Path:
    """Đổi ngang sang dọc bằng cắt bám chủ thể — dùng numpy để dò vị trí, KHÔNG dùng OpenCV.

    Trích một loạt khung xám nhỏ (``SAMPLE_FRAME_SIZE``) rải đều trên video để
    dò cột chứa chủ thể (``subject_column``, chỉ numpy — xem docstring module),
    rồi cắt một dải dọc cao bằng cả khung nguồn quanh cột đó, cuối cùng scale
    lấp đầy khung đích. Toạ độ phần trăm trả về từ ``subject_column`` chỉ được
    đổi sang pixel NGAY TẠI ĐÂY, sát chỗ dựng filter ffmpeg — không có chỗ nào
    khác đổi pixel.
    """
    info = probe(src)
    out_aspect = out_width / out_height

    timestamps = sample_timestamps(info.duration_sec, SAMPLE_FRAME_COUNT)
    raw_frames = extract_gray_frames(src, timestamps, SAMPLE_FRAME_SIZE, timeout=timeout)
    frames = [
        np.frombuffer(raw, dtype=np.uint8).reshape(SAMPLE_FRAME_SIZE, SAMPLE_FRAME_SIZE)
        for raw in raw_frames
    ]
    center = subject_column(frames, out_aspect=out_aspect)

    crop_w = min(round(info.height * out_aspect), info.width)
    crop_x = round(center * info.width - crop_w / 2)
    crop_x = max(0, min(crop_x, info.width - crop_w))

    vf = f"crop={crop_w}:{info.height}:{crop_x}:0,scale={out_width}:{out_height},setsar=1"

    tmp = tmp_sibling(dst)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-i",
        str(src),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    log.info(
        "reframe.crop",
        src=src.name,
        out=f"{out_width}x{out_height}",
        subject_column=round(center, 3),
        crop_x=crop_x,
        crop_w=crop_w,
    )
    run_ffmpeg(args, timeout=timeout)
    tmp.replace(dst)
    return dst
