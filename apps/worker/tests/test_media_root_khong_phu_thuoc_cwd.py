"""``MEDIA_ROOT`` tương đối phải trỏ CÙNG một chỗ dù chạy từ thư mục nào.

Quan sát ngày 2026-08-16: endpoint nghe thử giọng trả 404 trong khi file có
thật trên đĩa. Nguyên nhân: ``.env`` đặt ``MEDIA_ROOT=./media``, mà API chạy từ
``apps/api`` còn worker chạy từ ``apps/worker`` — hai tiến trình nhìn vào hai
thư mục khác nhau.

Lỗi này im lặng: worker ghi file thành công, API tìm không thấy, và không bên
nào báo gì sai. Nó chỉ lộ ra khi có một endpoint tự dựng đường dẫn media —
trước đó mọi endpoint đều đọc đường dẫn TUYỆT ĐỐI đã lưu sẵn trong DB.
"""

from __future__ import annotations

import os
from pathlib import Path

from reup_core.paths import media_root


def test_duong_dan_tuong_doi_khong_doi_theo_thu_muc_dang_dung(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MEDIA_ROOT", "./media")

    monkeypatch.chdir(tmp_path)
    tu_tmp = media_root()

    goc_repo = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(goc_repo)
    tu_goc = media_root()

    assert tu_tmp == tu_goc


def test_duong_dan_tuyet_doi_duoc_ton_trong(monkeypatch, tmp_path) -> None:
    """Đặt đường dẫn tuyệt đối là cách khai báo rõ ràng nhất — không được đụng."""
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "kho-media"))

    assert media_root() == tmp_path / "kho-media"


def test_khong_dat_bien_thi_van_ra_mot_cho_co_dinh(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MEDIA_ROOT", raising=False)

    monkeypatch.chdir(tmp_path)
    a = media_root()
    monkeypatch.chdir(os.path.expanduser("~"))
    b = media_root()

    assert a == b
