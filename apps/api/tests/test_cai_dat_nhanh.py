"""Cài đặt nhanh không được ghi đè thứ đang có trong ``.env``.

Đổi ``SETTINGS_KEY`` của một máy đang chạy sẽ làm MỌI khoá API đã lưu không
giải mã được nữa — hỏng im lặng, chỉ lộ ra lúc bấm Dịch. Nên hàm này chỉ được
THÊM dòng còn thiếu, không bao giờ sửa dòng đã có.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.services import he_thong


@pytest.fixture
def san(tmp_path, monkeypatch):
    """Trỏ .env và thư mục media vào chỗ tạm, đừng chạm máy thật."""
    env = tmp_path / ".env"
    media = tmp_path / "media"
    monkeypatch.setattr(he_thong, "DUONG_DAN_ENV", env)
    monkeypatch.setattr(he_thong, "_thu_muc_media", lambda: media)
    #: Migration coi như đã xong — phần đó cần database thật.
    monkeypatch.setattr(
        he_thong,
        "_kiem_migration",
        lambda db: he_thong.MucKiemTra("migration", "Migration", True),
    )
    return env, media


def test_tao_thu_muc_media_khi_chua_co(san) -> None:
    env, media = san
    da_lam = he_thong.cai_dat_nhanh(None)

    assert media.is_dir()
    assert any("media" in v for v in da_lam)


def test_them_khoa_ma_hoa_khi_env_chua_co(san) -> None:
    env, _ = san
    he_thong.cai_dat_nhanh(None)

    dong = [d for d in env.read_text().splitlines() if d.startswith("SETTINGS_KEY=")]
    assert len(dong) == 1
    assert len(dong[0].split("=", 1)[1]) > 20


def test_khong_bao_gio_ghi_de_khoa_dang_co(san) -> None:
    """Đây là cái phải giữ bằng mọi giá."""
    env, _ = san
    env.write_text("DATABASE_URL=postgresql://x\nSETTINGS_KEY=khoa-cu-dung-doi\n")

    he_thong.cai_dat_nhanh(None)

    noi_dung = env.read_text()
    assert "SETTINGS_KEY=khoa-cu-dung-doi" in noi_dung
    assert noi_dung.count("SETTINGS_KEY=") == 1
    assert "DATABASE_URL=postgresql://x" in noi_dung


def test_chay_hai_lan_khong_doi_gi_them(san) -> None:
    env, _ = san
    he_thong.cai_dat_nhanh(None)
    lan_dau = env.read_text()

    da_lam = he_thong.cai_dat_nhanh(None)

    assert env.read_text() == lan_dau
    assert da_lam == ["Không có gì phải sửa — máy này đã sẵn sàng."]


def test_ban_moi_nhat_doc_dung_tu_thu_muc_versions() -> None:
    """Không gọi `alembic heads` mà vẫn phải ra đúng bản."""
    ban = he_thong._ban_moi_nhat()
    thu_muc = Path(he_thong.ALEMBIC_INI).parent / "alembic" / "versions"

    assert ban
    assert any(ban in f.name for f in thu_muc.glob("*.py"))
