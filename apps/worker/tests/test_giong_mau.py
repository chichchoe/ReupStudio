"""Chuẩn hoá đoạn giọng mẫu — mẫu tồi thì MỌI video về sau đều tồi.

Fish S2-Pro nhân bản giọng theo ngữ cảnh: nó chép lại đoạn mẫu, kể cả nhiễu,
tiếng vọng và mức âm lượng. Chất lượng đầu ra không bao giờ vượt được chất
lượng đoạn mẫu — nên đây là chỗ đáng đo kỹ nhất của cả thư viện giọng.

Test tách phần DỰNG LỆNH và phần ĐỌC SỐ ĐO khỏi phần chạy ffmpeg: chạy ffmpeg
thật thì phải có file âm thanh thật, mà theo CLAUDE.md ffmpeg thuộc diện kiểm
tay bằng script, không test tự động.
"""

from __future__ import annotations

from pathlib import Path

from src.pipeline.giong_mau import DAI_NHAT_GIAY, doc_so_do, lenh_chuan_hoa


class TestLenhChuanHoa:
    def test_ra_mono_44100(self) -> None:
        cmd = lenh_chuan_hoa(Path("vao.m4a"), Path("ra.wav"))
        assert "-ac" in cmd and cmd[cmd.index("-ac") + 1] == "1"
        assert "-ar" in cmd and cmd[cmd.index("-ar") + 1] == "44100"

    def test_luon_cat_ngan_toi_da(self) -> None:
        #: Đoạn mẫu dài hơn 15 giây chỉ tổ phí ngữ cảnh và làm chậm mỗi câu.
        cmd = lenh_chuan_hoa(Path("vao.wav"), Path("ra.wav"))
        assert "-t" in cmd and float(cmd[cmd.index("-t") + 1]) == DAI_NHAT_GIAY

    def test_cat_khoang_thoi_gian_khi_lay_tu_file_co_san(self) -> None:
        cmd = lenh_chuan_hoa(Path("vao.mp4"), Path("ra.wav"), tu_giay=12.5, den_giay=24.0)
        #: -ss phải đứng TRƯỚC -i mới tua nhanh được; đứng sau là giải mã từ
        #: đầu file, video một tiếng thì chờ rất lâu.
        assert cmd.index("-ss") < cmd.index("-i")
        assert cmd[cmd.index("-ss") + 1] == "12.5"
        assert float(cmd[cmd.index("-t") + 1]) == 11.5

    def test_cat_dai_hon_toi_da_thi_van_bi_khong_che(self) -> None:
        cmd = lenh_chuan_hoa(Path("vao.mp4"), Path("ra.wav"), tu_giay=0.0, den_giay=60.0)
        assert float(cmd[cmd.index("-t") + 1]) == DAI_NHAT_GIAY

    def test_can_am_luong_va_cat_im_lang_hai_dau(self) -> None:
        cmd = lenh_chuan_hoa(Path("vao.wav"), Path("ra.wav"))
        loc = cmd[cmd.index("-af") + 1]
        assert "silenceremove" in loc
        assert "loudnorm" in loc

    def test_khong_dung_shell_va_moi_phan_tu_la_chuoi(self) -> None:
        #: CLAUDE.md cấm shell=True; danh sách lẫn số là lỗi khi truyền subprocess.
        cmd = lenh_chuan_hoa(Path("vao.wav"), Path("ra.wav"), tu_giay=1.0, den_giay=9.0)
        assert all(isinstance(x, str) for x in cmd)

    def test_ghi_de_khong_hoi(self) -> None:
        assert "-y" in lenh_chuan_hoa(Path("a.wav"), Path("b.wav"))


class TestDocSoDo:
    #: Trích đúng dạng ffmpeg in ra thật.
    VOL = (
        "[Parsed_volumedetect_0 @ 0x0] mean_volume: -21.4 dB\n"
        "[Parsed_volumedetect_0 @ 0x0] max_volume: -3.1 dB\n"
    )

    def test_doi_dB_sang_bien_do(self) -> None:
        do = doc_so_do(self.VOL, 12.0, "")
        #: -3,1 dB ≈ 0,70 biên độ; -21,4 dB ≈ 0,085.
        assert 0.69 < do.dinh < 0.71
        assert 0.08 < do.rms < 0.09
        assert do.do_dai_giay == 12.0

    def test_khong_co_im_lang_thi_ti_le_bang_khong(self) -> None:
        assert doc_so_do(self.VOL, 10.0, "").ti_le_im_lang == 0.0

    def test_cong_don_moi_doan_im_lang(self) -> None:
        im = (
            "[silencedetect @ 0x0] silence_start: 1.0\n"
            "[silencedetect @ 0x0] silence_end: 3.0 | silence_duration: 2\n"
            "[silencedetect @ 0x0] silence_start: 6.0\n"
            "[silencedetect @ 0x0] silence_end: 8.0 | silence_duration: 2\n"
        )
        assert doc_so_do(self.VOL, 10.0, im).ti_le_im_lang == 0.4

    def test_thieu_so_lieu_thi_ve_khong_chu_khong_no(self) -> None:
        #: ffmpeg đổi định dạng in ra là chuyện có thật. Nổ ở đây thì thêm
        #: giọng nào cũng hỏng; về 0 thì cổng chất lượng cảnh báo "quá nhỏ"
        #: và người dùng vẫn đi tiếp được.
        do = doc_so_do("không có gì", 5.0, "")
        assert do.rms == 0.0 and do.dinh == 0.0

    def test_do_dai_bang_khong_khong_chia_cho_khong(self) -> None:
        im = "[silencedetect @ 0x0] silence_duration: 2\n"
        assert doc_so_do(self.VOL, 0.0, im).ti_le_im_lang == 0.0


class TestRunFfmpegPhanTich:
    """Khoá lại một lỗi đã xảy ra thật ngày 2026-08-20.

    Số đo về TOÀN 0 trên file có tiếng rõ ràng, vì hai chỗ cùng lúc: ``_run``
    ép ``-loglevel error`` (nuốt kết quả của bộ lọc phân tích, vốn in ở mức
    ``info``), và ``run_ffmpeg`` trả **stdout** trong khi các bộ lọc đó in ra
    **stderr**.

    Hậu quả nếu để lọt: MỌI giọng người dùng thêm vào đều ăn cảnh báo "quá
    nhỏ". Test đơn vị cũ không bắt được vì chúng không chạy ffmpeg thật.
    """

    def test_dung_loglevel_info_chu_khong_phai_error(self, monkeypatch) -> None:
        ghi: dict = {}

        class KetQua:
            returncode = 0
            stdout = "khong dung stdout"
            stderr = "mean_volume: -21.4 dB"

        def bat(cmd, **kw):
            ghi["cmd"] = cmd
            return KetQua()

        monkeypatch.setattr("src.ffmpeg.runner.subprocess.run", bat)
        from src.ffmpeg.runner import run_ffmpeg_phan_tich

        ra = run_ffmpeg_phan_tich(["-i", "a.wav", "-af", "volumedetect", "-f", "null", "-"])

        assert ghi["cmd"][ghi["cmd"].index("-loglevel") + 1] == "info"
        #: Phải trả STDERR. Trả stdout là số đo về 0 và mọi giọng bị chê.
        assert ra == "mean_volume: -21.4 dB"

    def test_khong_dung_shell_va_co_timeout(self, monkeypatch) -> None:
        ghi: dict = {}

        class KetQua:
            returncode = 0
            stdout = ""
            stderr = ""

        def bat(cmd, **kw):
            ghi["cmd"], ghi["kw"] = cmd, kw
            return KetQua()

        monkeypatch.setattr("src.ffmpeg.runner.subprocess.run", bat)
        from src.ffmpeg.runner import run_ffmpeg_phan_tich

        run_ffmpeg_phan_tich(["-i", "a.wav"])
        assert isinstance(ghi["cmd"], list)
        assert ghi["kw"].get("shell") in (None, False)
        assert ghi["kw"].get("timeout") is not None
