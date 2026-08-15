"""Bản render cũ chỉ được dùng lại khi nó MỚI HƠN mọi đầu vào.

Quan sát ngày 2026-08-15: dịch lại một video, chuỗi tác vụ chạy đủ cả
``format_sub`` lẫn ``render``, hệ thống báo READY — nhưng file giao ra vẫn là
bản render từ hôm trước, mang phụ đề của bản dịch cũ. Log ghi
``render.skip_existing``.

Điều kiện bỏ qua cũ chỉ là "file tồn tại và khác rỗng". Nó đúng cho việc chạy
lại sau khi worker chết giữa chừng, nhưng sai khi bước phía trước đã sinh đầu
vào mới. Đây đúng loại hỏng tệ nhất của dự án này: hệ thống nói "xong" trong
khi thứ giao ra không phải thứ vừa dựng.

Luật số 4 CLAUDE.md nói "chạy lại phải cho CÙNG kết quả" — đầu vào đã đổi thì
kết quả cũ không còn là cùng kết quả nữa.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.pipeline.render import ban_cu_con_dung


def _ghi(p: Path, noi_dung: str, mtime: float) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(noi_dung, encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def test_khong_co_file_thi_phai_lam_lai(tmp_path: Path) -> None:
    nguon = _ghi(tmp_path / "vao.ass", "x", 1000)

    assert ban_cu_con_dung(tmp_path / "chua_co.mp4", nguon) is False


def test_file_rong_thi_phai_lam_lai(tmp_path: Path) -> None:
    """File 0 byte là dấu vết của lần render chết giữa chừng."""
    nguon = _ghi(tmp_path / "vao.ass", "x", 1000)
    rong = _ghi(tmp_path / "ra.mp4", "", 2000)

    assert ban_cu_con_dung(rong, nguon) is False


def test_ban_cu_moi_hon_dau_vao_thi_dung_lai(tmp_path: Path) -> None:
    """Worker chết rồi chạy lại: không có gì đổi, không cần render lại."""
    nguon = _ghi(tmp_path / "vao.ass", "x", 1000)
    cu = _ghi(tmp_path / "ra.mp4", "video", 2000)

    assert ban_cu_con_dung(cu, nguon) is True


def test_dau_vao_moi_hon_thi_phai_lam_lai(tmp_path: Path) -> None:
    """Đúng ca hỏng thật: phụ đề vừa được ghi lại, bản render thì từ hôm qua."""
    cu = _ghi(tmp_path / "ra.mp4", "video", 1000)
    nguon = _ghi(tmp_path / "vao.ass", "x", 2000)

    assert ban_cu_con_dung(cu, nguon) is False


def test_chi_can_MOT_dau_vao_moi_hon_la_phai_lam_lai(tmp_path: Path) -> None:
    cu = _ghi(tmp_path / "ra.mp4", "video", 2000)
    cu_hon = _ghi(tmp_path / "goc.mp4", "nguồn", 1000)
    moi_hon = _ghi(tmp_path / "vao.ass", "x", 3000)

    assert ban_cu_con_dung(cu, cu_hon, moi_hon) is False


def test_dau_vao_khong_ton_tai_thi_bo_qua_khong_no(tmp_path: Path) -> None:
    """Thiếu một đầu vào không phải việc của hàm này — bước sau sẽ báo lỗi rõ."""
    cu = _ghi(tmp_path / "ra.mp4", "video", 2000)

    assert ban_cu_con_dung(cu, tmp_path / "khong_co.ass") is True


def test_khong_khai_dau_vao_thi_ve_dung_kiem_tra_ton_tai(tmp_path: Path) -> None:
    cu = _ghi(tmp_path / "ra.mp4", "video", 2000)

    assert ban_cu_con_dung(cu) is True
