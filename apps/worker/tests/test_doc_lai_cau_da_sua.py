"""Sửa vài câu rồi đọc lại thì CHỈ đọc lại những câu đã đổi.

Người dùng sửa 3 câu trong bảng đối chiếu 137 câu. Không có chốt vân tay thì
bước TTS gọi nhà cung cấp đủ 137 lượt — mất vài phút và tốn tiền cho 134 câu
chẳng đổi chữ nào. Luật số 4 CLAUDE.md: bước nào cũng phải idempotent.

Vân tay tính từ CHỮ + GIỌNG + BÊN ĐỌC + MODEL: đổi bất kỳ thứ nào trong bốn
thứ đó cũng ra tiếng khác, nên đều phải đọc lại.
"""

from __future__ import annotations

from src.pipeline.cues import Cue
from src.tasks.video import _con_dung_duoc, _doc_tuan_tu, _van_tay_cau


class ProviderDem:
    """Đếm số câu thật sự phải đọc."""

    ten = "gia"

    def __init__(self) -> None:
        self.da_doc: list[str] = []

    def doc(self, text, dst, *, giong):
        self.da_doc.append(text)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"RIFF" + text.encode())
        return dst


def _cues(texts: list[str]) -> list[Cue]:
    return [Cue(i, i * 2.0, i * 2.0 + 1.8, t) for i, t in enumerate(texts)]


def test_lan_dau_doc_het(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("src.tasks.video.voice_parts_dir", lambda vid: tmp_path)
    p = ProviderDem()

    _doc_tuan_tu(p, _cues(["một", "hai", "ba"]), "vid", "nova", "model-x")

    assert p.da_doc == ["một", "hai", "ba"]


def test_chay_lai_khong_doi_gi_thi_khong_goi_lan_nao(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("src.tasks.video.voice_parts_dir", lambda vid: tmp_path)
    cues = _cues(["một", "hai", "ba"])
    _doc_tuan_tu(ProviderDem(), cues, "vid", "nova", "model-x")

    lan_hai = ProviderDem()
    ra = _doc_tuan_tu(lan_hai, cues, "vid", "nova", "model-x")

    assert lan_hai.da_doc == []
    assert len(ra) == 3  # vẫn trả đủ đường dẫn để dựng dải tiếng


def test_sua_mot_cau_thi_chi_doc_lai_cau_do(monkeypatch, tmp_path) -> None:
    """Đây là điều người dùng thật sự cần."""
    monkeypatch.setattr("src.tasks.video.voice_parts_dir", lambda vid: tmp_path)
    _doc_tuan_tu(ProviderDem(), _cues(["một", "hai", "ba"]), "vid", "nova", "model-x")

    lan_hai = ProviderDem()
    _doc_tuan_tu(lan_hai, _cues(["một", "HAI ĐÃ SỬA", "ba"]), "vid", "nova", "model-x")

    assert lan_hai.da_doc == ["HAI ĐÃ SỬA"]


def test_doi_giong_thi_doc_lai_het(monkeypatch, tmp_path) -> None:
    """Chữ y nguyên nhưng giọng khác thì tiếng cũng khác — không dùng lại được."""
    monkeypatch.setattr("src.tasks.video.voice_parts_dir", lambda vid: tmp_path)
    cues = _cues(["một", "hai"])
    _doc_tuan_tu(ProviderDem(), cues, "vid", "nova", "model-x")

    lan_hai = ProviderDem()
    _doc_tuan_tu(lan_hai, cues, "vid", "onyx", "model-x")

    assert lan_hai.da_doc == ["một", "hai"]


def test_doi_model_hay_doi_ben_doc_cung_phai_doc_lai() -> None:
    goc = _van_tay_cau("xin chào", "nova", "openrouter", "gpt-audio-mini")

    assert _van_tay_cau("xin chào", "nova", "openrouter", "gpt-audio") != goc
    assert _van_tay_cau("xin chào", "nova", "edge", "gpt-audio-mini") != goc
    assert _van_tay_cau("xin chào", "nova", "openrouter", "gpt-audio-mini") == goc


def test_mau_giong_rong_thi_khong_dung_lai(tmp_path) -> None:
    """File 0 byte là lần trước hỏng — dùng lại là cắm một khoảng câm vào dải."""
    wav = tmp_path / "cau_00000.wav"
    wav.write_bytes(b"")
    wav.with_suffix(".vantay").write_text("abc")

    assert _con_dung_duoc(wav, "abc") is False


def test_mat_van_tay_thi_doc_lai(tmp_path) -> None:
    """Mẩu giọng từ bản cũ chưa có vân tay — đọc lại còn hơn dùng nhầm."""
    wav = tmp_path / "cau_00000.wav"
    wav.write_bytes(b"RIFF")

    assert _con_dung_duoc(wav, "abc") is False


class ProviderSongSong:
    """Giả edge-tts: có ``doc_nhieu``, đặt tên file theo VỊ TRÍ, bỏ qua câu rỗng."""

    ten = "edge"

    def __init__(self) -> None:
        self.da_doc: list[str] = []

    def doc_nhieu(self, cac_cau, thu_muc, *, giong, progress_cb=None):
        thu_muc.mkdir(parents=True, exist_ok=True)
        ra = {}
        for i, cau in enumerate(cac_cau):
            if not cau:
                continue  # đúng cách edge.py bỏ qua chuỗi rỗng
            self.da_doc.append(cau)
            dst = thu_muc / f"cau_{i:05d}.mp3"
            dst.write_bytes(b"ID3" + cau.encode())
            ra[i] = dst
        return ra


def test_duong_song_song_cung_dung_lai_mau_cu(monkeypatch, tmp_path) -> None:
    """edge-tts đi đường `doc_nhieu`, KHÔNG qua `_doc_tuan_tu`.

    Bản đầu chỉ chốt ở đường tuần tự nên edge — bên miễn phí hay dùng nhất —
    vẫn đọc lại sạch 137 câu mỗi lần sửa một chữ.
    """
    from src.tasks.video import _doc_song_song

    monkeypatch.setattr("src.tasks.video.voice_parts_dir", lambda vid: tmp_path)
    cues = _cues(["một", "hai", "ba"])
    _doc_song_song(ProviderSongSong(), cues, "vid", "hoai-my", "")

    lan_hai = ProviderSongSong()
    ra = _doc_song_song(lan_hai, _cues(["một", "HAI ĐÃ SỬA", "ba"]), "vid", "hoai-my", "")

    assert lan_hai.da_doc == ["HAI ĐÃ SỬA"]
    #: Vẫn phải trả đủ 3 đường dẫn — thiếu một cái là dải tiếng hụt một câu.
    assert sorted(ra) == [0, 1, 2]


def test_duong_song_song_giu_dung_ten_file_theo_vi_tri(monkeypatch, tmp_path) -> None:
    """Cắt bớt danh sách là lệch tên file của mọi câu phía sau — phải đưa chuỗi
    rỗng thay vì bỏ phần tử."""
    from src.tasks.video import _doc_song_song

    monkeypatch.setattr("src.tasks.video.voice_parts_dir", lambda vid: tmp_path)
    cues = _cues(["một", "hai", "ba"])
    _doc_song_song(ProviderSongSong(), cues, "vid", "hoai-my", "")
    ra = _doc_song_song(ProviderSongSong(), _cues(["một", "hai", "BA MỚI"]), "vid", "hoai-my", "")

    assert ra[2].name == "cau_00002.mp3"
    assert ra[2].read_bytes() == b"ID3" + "BA MỚI".encode()
