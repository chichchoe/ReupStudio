#!/usr/bin/env python3
"""Chuyển cấu hình từ ``.env`` vào bảng ``app_settings`` MỘT LẦN.

Vì sao: ``.env`` nằm cạnh mã nguồn nên chỉ cần một lần ``git add -A`` bất cẩn
là khoá API lên GitHub. Chuyện đó suýt xảy ra ngày 2026-08-16.

    python scripts/chuyen_env_vao_db.py           # xem trước, không ghi gì
    python scripts/chuyen_env_vao_db.py --ghi     # ghi thật

Sau khi ghi xong, XOÁ TAY các dòng đã chuyển khỏi ``.env``. Script cố ý không
tự xoá: mất khoá API vì một script chạy nhầm thì không lấy lại được, còn xoá
tay thì bạn nhìn thấy mình đang xoá gì.

Ba biến KHÔNG chuyển và phải giữ nguyên trong ``.env``: ``DATABASE_URL``,
``REDIS_URL``, ``SETTINGS_KEY``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "api"))

from reup_core.db import session_scope
from reup_core.settings_store import ENV_KEY_MA_HOA, KHOA_BOOTSTRAP, ghi, la_bi_mat


def doc_env(f: Path) -> dict[str, str]:
    ra: dict[str, str] = {}
    for dong in f.read_text(encoding="utf-8").splitlines():
        dong = dong.strip()
        if not dong or dong.startswith("#") or "=" not in dong:
            continue
        key, _, value = dong.partition("=")
        ra[key.strip().upper()] = value.strip()
    return ra


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ghi", action="store_true", help="ghi thật vào DB")
    parser.add_argument("--env", type=Path, default=REPO / ".env")
    args = parser.parse_args()

    if not args.env.exists():
        raise SystemExit(f"Không thấy {args.env}")

    tat_ca = doc_env(args.env)

    #: Nạp SETTINGS_KEY vào biến môi trường trước khi ghi. Script này không đi
    #: qua lớp Settings của pydantic (thứ vẫn nạp .env), mà settings_store lại
    #: đọc bằng os.getenv — không nối lại thì mọi bí mật ném KhoaMaHoaThieu.
    if tat_ca.get(ENV_KEY_MA_HOA):
        os.environ[ENV_KEY_MA_HOA] = tat_ca[ENV_KEY_MA_HOA]
    #: DATABASE_URL cũng vậy: session_scope() đọc từ môi trường.
    if tat_ca.get("DATABASE_URL"):
        os.environ.setdefault("DATABASE_URL", tat_ca["DATABASE_URL"])
    chuyen = {k: v for k, v in tat_ca.items() if k not in KHOA_BOOTSTRAP and v}
    giu_lai = {k for k in tat_ca if k in KHOA_BOOTSTRAP}

    print(f"{'KHOÁ':<32}{'KIỂU':<10}GIÁ TRỊ")
    for k, v in sorted(chuyen.items()):
        kieu = "bí mật" if la_bi_mat(k) else "thường"
        hien = "••••••" if la_bi_mat(k) else (v[:40] + ("…" if len(v) > 40 else ""))
        print(f"  {k:<30}{kieu:<10}{hien}")

    print(f"\n{len(chuyen)} biến sẽ chuyển vào DB.")
    print(f"{len(giu_lai)} biến GIỮ NGUYÊN trong .env: {', '.join(sorted(giu_lai))}")

    if not args.ghi:
        print("\nXem trước, chưa ghi gì. Thêm --ghi để ghi thật.")
        return

    with session_scope() as db:
        for k, v in chuyen.items():
            ghi(db, k, v)

    print(f"\nĐã ghi {len(chuyen)} biến vào bảng app_settings.")
    print("Giờ XOÁ TAY các dòng đó khỏi .env, giữ lại đúng ba biến bootstrap.")


if __name__ == "__main__":
    main()
