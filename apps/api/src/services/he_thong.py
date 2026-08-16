"""Kiểm tra máy đang chạy và cài đặt nhanh khi chuyển sang máy khác.

Vì sao cần: dựng lại dự án trên máy mới là chuỗi thao tác dài — tạo ``.env``,
sinh khoá mã hoá, chạy migration, tạo thư mục media, cài ffmpeg — và mỗi bước
thiếu lại hỏng ở một chỗ khác nhau, thông báo lỗi thì chẳng chỉ về nguyên nhân.
Gom hết thành một danh sách kiểm và một nút bấm.

Thứ tự các mục đi theo đúng thứ tự phụ thuộc: mục dưới chỉ có nghĩa khi mục
trên đã xanh.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import redis
import sqlalchemy as sa
from reup_core.settings_store import sinh_khoa
from sqlalchemy.orm import Session

from ..config import get_settings

#: ``src/services/he_thong.py`` → services → src → api → apps → gốc repo.
GOC_REPO = Path(__file__).resolve().parents[4]
DUONG_DAN_ENV = GOC_REPO / ".env"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

#: Lệnh ngoài luôn có timeout (CLAUDE.md). Migration trên DB rỗng chạy vài giây.
TIMEOUT_LENH_SEC = 20
TIMEOUT_MIGRATION_SEC = 180


@dataclass
class MucKiemTra:
    ma: str
    ten: str
    ok: bool
    #: Câu ngắn nói TÌNH TRẠNG THẬT: phiên bản đọc được, đường dẫn, dung lượng.
    chi_tiet: str = ""
    #: Chỉ điền khi ``ok`` sai — nói làm gì để sửa, dán chạy được luôn thì tốt.
    cach_sua: str = ""
    #: Nút "Cài đặt nhanh" tự sửa được mục này hay không.
    tu_sua_duoc: bool = False


@dataclass
class ThongTinMay:
    ten_may: str
    he_dieu_hanh: str
    kien_truc: str
    python: str
    thu_muc_du_an: str
    thu_muc_media: str
    dung_luong_trong_gb: float = 0.0
    muc: list[MucKiemTra] = field(default_factory=list)


def _chay(cmd: list[str], timeout: int = TIMEOUT_LENH_SEC) -> tuple[int, str]:
    """Chạy lệnh ngoài, trả ``(mã, output)``. Không ``shell=True`` (CLAUDE.md)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return 127, f"không tìm thấy {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"{cmd[0]} chạy quá {timeout}s"
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def _thu_muc_media() -> Path:
    return Path(os.getenv("MEDIA_ROOT") or get_settings().media_root).expanduser().resolve()


def _kiem_env() -> MucKiemTra:
    co = DUONG_DAN_ENV.exists()
    return MucKiemTra(
        ma="env",
        ten="File .env",
        ok=co,
        chi_tiet=str(DUONG_DAN_ENV) if co else "chưa có",
        cach_sua="" if co else f"Chép .env.example thành .env ở {GOC_REPO}",
        tu_sua_duoc=not co,
    )


def _kiem_khoa_ma_hoa() -> MucKiemTra:
    #: Đọc qua ``get_settings()`` chứ không ``os.getenv``: pydantic mới là chỗ
    #: nạp ``.env``, đọc thẳng biến môi trường thì báo "chưa đặt" dù đã có.
    co = bool(getattr(get_settings(), "settings_key", "") or os.getenv("SETTINGS_KEY"))
    return MucKiemTra(
        ma="settings_key",
        ten="Khoá mã hoá bí mật",
        ok=co,
        chi_tiet="đã đặt" if co else "chưa đặt — khoá API sẽ không lưu được",
        cach_sua="" if co else "Bấm Cài đặt nhanh để sinh và ghi vào .env",
        tu_sua_duoc=not co,
    )


def _kiem_postgres(db: Session) -> MucKiemTra:
    try:
        ban = db.execute(sa.text("SHOW server_version")).scalar()
        return MucKiemTra("postgres", "PostgreSQL", True, f"phiên bản {ban}")
    except Exception as exc:  # noqa: BLE001 - mọi kiểu hỏng đều là "không tới được"
        return MucKiemTra(
            "postgres",
            "PostgreSQL",
            False,
            str(exc)[:160],
            "Chạy `docker compose up -d db` rồi kiểm lại DATABASE_URL trong .env",
        )


def _ban_moi_nhat() -> str:
    """Bản migration mới nhất, đọc THẲNG từ thư mục ``versions``.

    Không gọi ``alembic heads``: lệnh đó nạp cả ``env.py``, tức nạp lại toàn bộ
    ứng dụng trong một tiến trình con — mất vài giây cho một câu trả lời đọc
    được bằng cách so hai tập hợp. Bản mới nhất là bản không bị bản nào khác
    trỏ ngược về.
    """
    thu_muc = ALEMBIC_INI.parent / "alembic" / "versions"
    if not thu_muc.exists():
        return ""

    ban: set[str] = set()
    da_bi_tro: set[str] = set()
    for f in thu_muc.glob("*.py"):
        noi_dung = f.read_text(encoding="utf-8")
        for ten, gom in (("revision", ban), ("down_revision", da_bi_tro)):
            khop = re.search(rf"^{ten}(?::\s*[^=]+)?\s*=\s*[\"']([^\"']+)[\"']", noi_dung, re.M)
            if khop:
                gom.add(khop.group(1))

    con_lai = ban - da_bi_tro
    return next(iter(con_lai)) if len(con_lai) == 1 else ""


def _kiem_migration(db: Session) -> MucKiemTra:
    """So bản migration DB đang ở với bản mới nhất trong mã nguồn."""
    try:
        hien = db.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        hien = None

    moi_nhat = _ban_moi_nhat()
    if not moi_nhat:
        return MucKiemTra("migration", "Migration", bool(hien), hien or "không đọc được")
    khop = bool(hien) and bool(moi_nhat) and hien == moi_nhat
    return MucKiemTra(
        ma="migration",
        ten="Migration database",
        ok=khop,
        chi_tiet=f"đang ở {hien or 'chưa chạy lần nào'}"
        + (f", mới nhất {moi_nhat}" if moi_nhat and not khop else ""),
        cach_sua="" if khop else "Bấm Cài đặt nhanh để chạy `alembic upgrade head`",
        tu_sua_duoc=not khop,
    )


def _kiem_redis() -> MucKiemTra:
    try:
        r = redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
        ban = r.info("server").get("redis_version", "?")
        return MucKiemTra("redis", "Redis", True, f"phiên bản {ban}")
    except Exception as exc:  # noqa: BLE001
        return MucKiemTra(
            "redis",
            "Redis",
            False,
            str(exc)[:160],
            "Chạy `docker compose up -d redis`",
        )


def _kiem_worker() -> MucKiemTra:
    """Có worker Celery nào đang nghe không — không có thì video đứng im mãi."""
    from . import task_bridge

    try:
        tra_loi = task_bridge.celery().control.ping(timeout=1.5) or []
    except Exception:  # noqa: BLE001
        tra_loi = []
    so = len(tra_loi)
    return MucKiemTra(
        ma="worker",
        ten="Worker Celery",
        ok=so > 0,
        chi_tiet=f"{so} worker đang nghe" if so else "không có worker nào — video sẽ đứng im",
        cach_sua=""
        if so
        else "Mở terminal khác: cd apps/worker && celery -A src.celery_app worker "
        "-Q download,media,gpu,upload -l info",
    )


def _kiem_ffmpeg() -> MucKiemTra:
    duong = shutil.which("ffmpeg")
    if not duong:
        return MucKiemTra(
            "ffmpeg",
            "FFmpeg",
            False,
            "không có trong PATH",
            "macOS: brew install ffmpeg · Ubuntu: sudo apt install ffmpeg",
        )
    _, ra = _chay(["ffmpeg", "-version"])
    ban = ra.split("\n")[0].replace("ffmpeg version ", "")[:60] if ra else duong
    return MucKiemTra("ffmpeg", "FFmpeg", True, ban)


def _kiem_media() -> MucKiemTra:
    thu_muc = _thu_muc_media()
    if not thu_muc.exists():
        return MucKiemTra(
            "media",
            "Thư mục media",
            False,
            f"{thu_muc} chưa có",
            "Bấm Cài đặt nhanh để tạo",
            tu_sua_duoc=True,
        )
    ghi_duoc = os.access(thu_muc, os.W_OK)
    trong = shutil.disk_usage(thu_muc).free / 1024**3
    return MucKiemTra(
        ma="media",
        ten="Thư mục media",
        ok=ghi_duoc,
        chi_tiet=f"{thu_muc} · còn {trong:.1f} GB",
        cach_sua="" if ghi_duoc else f"Không ghi được vào {thu_muc} — sửa quyền thư mục",
    )


def kiem_tra_may(db: Session) -> ThongTinMay:
    """Toàn bộ tình trạng máy đang chạy, xếp theo thứ tự phụ thuộc."""
    thu_muc = _thu_muc_media()
    trong = shutil.disk_usage(thu_muc if thu_muc.exists() else GOC_REPO).free / 1024**3

    return ThongTinMay(
        ten_may=socket.gethostname(),
        he_dieu_hanh=f"{platform.system()} {platform.release()}",
        kien_truc=platform.machine(),
        python=platform.python_version(),
        thu_muc_du_an=str(GOC_REPO),
        thu_muc_media=str(thu_muc),
        dung_luong_trong_gb=round(trong, 1),
        muc=[
            _kiem_env(),
            _kiem_khoa_ma_hoa(),
            _kiem_postgres(db),
            _kiem_migration(db),
            _kiem_redis(),
            _kiem_worker(),
            _kiem_ffmpeg(),
            _kiem_media(),
        ],
    )


def _them_dong_env(dong: str) -> None:
    """Thêm MỘT dòng vào ``.env``. Không bao giờ sửa hay xoá dòng đang có."""
    cu = DUONG_DAN_ENV.read_text(encoding="utf-8") if DUONG_DAN_ENV.exists() else ""
    ngan = "" if not cu or cu.endswith("\n") else "\n"
    DUONG_DAN_ENV.write_text(f"{cu}{ngan}{dong}\n", encoding="utf-8")


def cai_dat_nhanh(db: Session) -> list[str]:
    """Làm hộ những bước tự làm được, trả về danh sách việc ĐÃ làm.

    Cố ý KHÔNG chạy qua Celery dù mất vài giây (ngoại lệ của luật số 1
    CLAUDE.md): đây đúng là lúc worker chưa chạy được — máy mới thì migration
    chưa chạy, thư mục media chưa có. Bắt nó qua hàng đợi là bắt người dùng
    dựng xong mọi thứ trước khi được giúp dựng.

    KHÔNG bao giờ ghi đè giá trị đang có trong ``.env``. Đổi ``SETTINGS_KEY``
    của một máy đang chạy sẽ làm mọi bí mật đã lưu không giải mã được nữa, nên
    chỉ thêm khi trong file chưa có dòng nào.
    """
    da_lam: list[str] = []

    thu_muc = _thu_muc_media()
    if not thu_muc.exists():
        thu_muc.mkdir(parents=True, exist_ok=True)
        da_lam.append(f"Tạo thư mục media: {thu_muc}")

    if not DUONG_DAN_ENV.exists():
        DUONG_DAN_ENV.write_text("", encoding="utf-8")
        da_lam.append(f"Tạo file .env rỗng: {DUONG_DAN_ENV}")

    noi_dung = DUONG_DAN_ENV.read_text(encoding="utf-8")
    if not any(d.strip().startswith("SETTINGS_KEY=") for d in noi_dung.splitlines()):
        _them_dong_env(f"SETTINGS_KEY={sinh_khoa()}")
        da_lam.append(
            "Sinh khoá mã hoá mới và ghi vào .env. "
            "Nếu bạn chuyển từ máy cũ sang và muốn đọc lại khoá API đã lưu, "
            "hãy chép SETTINGS_KEY của máy cũ đè lên dòng này."
        )

    if _kiem_migration(db).ok is False:
        ma, ra = _chay(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
            timeout=TIMEOUT_MIGRATION_SEC,
        )
        da_lam.append(
            "Chạy migration database (alembic upgrade head)"
            if ma == 0
            else f"Migration KHÔNG chạy được: {ra[-300:]}"
        )

    if not da_lam:
        da_lam.append("Không có gì phải sửa — máy này đã sẵn sàng.")
    return da_lam
