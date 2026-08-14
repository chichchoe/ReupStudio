"""Endpoint ``GET /api/v1/llm/models`` — đổ ô chọn "AI dịch" bằng model THẬT.

Logic phân loại đã có test riêng ở ``test_llm_models.py`` (hàm thuần trong
``reup_core.llm_models``). Bộ này chỉ khoá phần mà API phải tự lo:

1. **Địa chỉ và khoá lấy từ cấu hình**, không hardcode.
2. **Cache 5 phút** — danh sách model hầu như không đổi, gọi mạng mỗi lần mở
   ô chọn là lãng phí hạn mức lẫn thời gian chờ của người dùng.
3. **Hỏng thì phải BÁO, không được trả danh sách rỗng.** Đây là điều dễ sai
   nhất: một ``except`` nuốt lỗi rồi ``return []`` khiến người dùng thấy ô
   chọn trống và tưởng key của mình không có model nào — thật ra là sai key.
4. **Khoá API không bao giờ lọt vào thông báo lỗi.** Nhà cung cấp hay chèn
   nguyên URL (kèm key) vào thân lỗi; bê thẳng ra là rò khoá cho người dùng
   cuối và cho cả file log.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.errors import ApiError, LlmAuthFailed, LlmUnavailable, api_error_handler
from src.routers import llm as llm_router
from src.services import llm_model_service

KHOA = "khoa-bi-mat-khong-duoc-lo"

#: Danh sách rút gọn nhưng lấy từ id THẬT do key Gemini của dự án trả về.
ID_THAT = [
    "models/gemini-3.5-flash-lite",
    "models/gemini-2.5-pro",
    "models/gemini-2.5-flash-tts",
    "models/veo-3.1-generate-preview",
    "models/gemini-embedding-001",
]


class _Response:
    """Bản giả của ``httpx.Response``, chỉ giữ đúng phần service dùng tới."""

    def __init__(self, status_code: int = 200, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self):
        if self._payload is None:
            # httpx ném JSONDecodeError (con của ValueError) khi thân không
            # phải JSON — VD proxy trả trang HTML báo lỗi.
            raise ValueError("thân trả về không phải JSON")
        return self._payload


def _ok(ids: list[str]) -> _Response:
    """Hình dạng OpenAI: ``{"data": [{"id": ...}]}`` — Gemini qua lớp tương
    thích OpenAI cũng trả đúng dạng này."""
    return _Response(200, {"object": "list", "data": [{"id": i} for i in ids]})


@pytest.fixture
def gia_lap(monkeypatch):
    """Thay ``httpx.Client`` bằng bản giả: test chạy được khi không có mạng.

    Trả về sổ ghi để bài test kiểm URL, header đã gửi và ĐẾM số lượt gọi thật
    — con số đó là cách duy nhất chứng minh cache có hoạt động hay không.
    """
    ghi_nhan: dict = {"urls": [], "headers": [], "hang_doi": []}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers=None):
            ghi_nhan["urls"].append(url)
            ghi_nhan["headers"].append(headers or {})
            ket_qua = ghi_nhan["hang_doi"].pop(0)
            if isinstance(ket_qua, Exception):
                raise ket_qua
            return ket_qua

    monkeypatch.setattr(llm_model_service.httpx, "Client", FakeClient)
    llm_model_service.xoa_cache()
    yield ghi_nhan
    llm_model_service.xoa_cache()


@pytest.fixture
def dong_ho(monkeypatch):
    """Đồng hồ giả để tua thời gian — không ai chờ 5 phút thật trong test."""
    hien_tai = {"giay": 0.0}
    monkeypatch.setattr(llm_model_service, "_bay_gio", lambda: hien_tai["giay"])
    return hien_tai


def _cau_hinh(monkeypatch, **kw):
    """Cấu hình cô lập khỏi máy đang chạy.

    ``_env_file=None`` bắt buộc: thiếu nó thì ``Settings`` đọc ``.env`` thật
    của lập trình viên, và test đỏ hay xanh tuỳ người chạy đang cắm key nào.
    """
    from src.config import Settings

    mac_dinh = {"llm_api_key": KHOA}
    monkeypatch.setattr(
        llm_model_service, "get_settings", lambda: Settings(_env_file=None, **{**mac_dinh, **kw})
    )


# --- Lọc theo mục đích -------------------------------------------------


def test_chia_hai_nhom_dich_va_tts_bo_cac_loai_khac(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_ok(ID_THAT))

    ket_qua = llm_model_service.liet_ke_models()

    assert ket_qua.translate == ["gemini-3.5-flash-lite", "gemini-2.5-pro"]
    assert ket_qua.tts == ["gemini-2.5-flash-tts"]


def test_bo_tien_to_models_khoi_id_tra_ve(gia_lap, monkeypatch) -> None:
    """API Gemini trả ``models/gemini-...``; phần đầu đó không phải tên model
    và dán nguyên vào ``LLM_MODEL`` thì lượt gọi dịch hỏng."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_ok(["models/gemini-3.5-flash-lite"]))

    ket_qua = llm_model_service.liet_ke_models()

    assert ket_qua.translate == ["gemini-3.5-flash-lite"]


def test_hieu_ca_hinh_dang_gemini_thuan(gia_lap, monkeypatch) -> None:
    """API Gemini bản gốc trả ``{"models": [{"name": ...}]}`` chứ không phải
    ``{"data": [{"id": ...}]}`` — cắm ``LLM_BASE_URL`` vào bản gốc thay vì lớp
    tương thích OpenAI là chuyện rất dễ xảy ra, không được vỡ."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(
        _Response(200, {"models": [{"name": "models/gemini-3.5-flash-lite"}]})
    )

    ket_qua = llm_model_service.liet_ke_models()

    assert ket_qua.translate == ["gemini-3.5-flash-lite"]


def test_giu_nguyen_thu_tu_nha_cung_cap_tra_ve(gia_lap, monkeypatch) -> None:
    """Nhà cung cấp thường xếp model đáng dùng lên trước; sắp lại theo bảng
    chữ cái sẽ đẩy bản cũ lên đầu ô chọn."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_ok(["gemini-2.5-pro", "gemini-3.5-flash-lite"]))

    assert llm_model_service.liet_ke_models().translate == [
        "gemini-2.5-pro",
        "gemini-3.5-flash-lite",
    ]


# --- Địa chỉ và khoá lấy từ cấu hình -----------------------------------


def test_goi_dung_dia_chi_theo_llm_base_url(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch, llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai")
    gia_lap["hang_doi"].append(_ok(ID_THAT))

    llm_model_service.liet_ke_models()

    assert gia_lap["urls"] == ["https://generativelanguage.googleapis.com/v1beta/openai/models"]


def test_dau_gach_cheo_thua_o_cuoi_khong_lam_hong_dia_chi(gia_lap, monkeypatch) -> None:
    """Địa chỉ Gemini trong tài liệu chính thức có ``/`` ở cuối — dán nguyên
    vào ``.env`` không được sinh ra ``//models``."""
    _cau_hinh(monkeypatch, llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    gia_lap["hang_doi"].append(_ok(ID_THAT))

    llm_model_service.liet_ke_models()

    assert "//models" not in gia_lap["urls"][0]


def test_gui_khoa_bang_header_bearer(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_ok(ID_THAT))

    llm_model_service.liet_ke_models()

    assert gia_lap["headers"][0]["Authorization"] == f"Bearer {KHOA}"


# --- Cache 5 phút ------------------------------------------------------


def test_goi_lan_hai_lay_tu_cache_khong_cham_mang(gia_lap, dong_ho, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_ok(ID_THAT))

    dau = llm_model_service.liet_ke_models()
    dong_ho["giay"] += 60
    sau = llm_model_service.liet_ke_models()

    assert len(gia_lap["urls"]) == 1, "lần hai phải lấy từ cache, không gọi lại mạng"
    assert sau.translate == dau.translate


def test_qua_han_cache_thi_hoi_lai_nha_cung_cap(gia_lap, dong_ho, monkeypatch) -> None:
    """Hết hạn phải hỏi lại: người dùng vừa được cấp model mới thì không phải
    khởi động lại API mới thấy."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].extend([_ok(ID_THAT), _ok(["gemini-9.9-flash-lite"])])

    llm_model_service.liet_ke_models()
    dong_ho["giay"] += llm_model_service.CACHE_TTL_SEC + 1
    sau = llm_model_service.liet_ke_models()

    assert len(gia_lap["urls"]) == 2
    assert sau.translate == ["gemini-9.9-flash-lite"]


def test_doi_base_url_thi_khong_dung_cache_cua_nha_cung_cap_cu(
    gia_lap, dong_ho, monkeypatch
) -> None:
    """Cache phải theo địa chỉ: đổi nhà cung cấp mà vẫn trả model của bên cũ
    thì người dùng chọn phải model không tồn tại."""
    _cau_hinh(monkeypatch, llm_base_url="https://a.example/v1")
    gia_lap["hang_doi"].extend([_ok(["gemini-2.5-pro"]), _ok(["qwen-3-max"])])
    llm_model_service.liet_ke_models()

    _cau_hinh(monkeypatch, llm_base_url="https://b.example/v1")
    sau = llm_model_service.liet_ke_models()

    assert sau.translate == ["qwen-3-max"]


def test_khong_cache_ket_qua_hong(gia_lap, dong_ho, monkeypatch) -> None:
    """Lỗi mạng chốc lát không được ghim 5 phút — người dùng bấm thử lại là
    phải hỏi lại nhà cung cấp ngay."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].extend([httpx.ConnectError("mạng rớt"), _ok(ID_THAT)])

    with pytest.raises(LlmUnavailable):
        llm_model_service.liet_ke_models()
    ket_qua = llm_model_service.liet_ke_models()

    assert ket_qua.translate


# --- Hỏng thì phải báo, không im lặng ----------------------------------


def test_key_sai_bao_loi_chu_khong_tra_danh_sach_rong(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_Response(401, {"error": {"message": "API key not valid"}}))

    with pytest.raises(LlmAuthFailed) as loi:
        llm_model_service.liet_ke_models()

    assert "401" in loi.value.message or "khoá" in loi.value.message.lower()


def test_chua_cau_hinh_key_thi_bao_ngay_khong_goi_mang(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch, llm_api_key="")

    with pytest.raises(LlmAuthFailed) as loi:
        llm_model_service.liet_ke_models()

    assert "LLM_API_KEY" in loi.value.message
    assert gia_lap["urls"] == [], "chưa có khoá thì gọi mạng cũng vô ích"


def test_mang_loi_bao_loi_ro_rang(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(httpx.ConnectError("không phân giải được tên miền"))

    with pytest.raises(LlmUnavailable):
        llm_model_service.liet_ke_models()


def test_than_tra_ve_khong_phai_json_thi_bao_loi(gia_lap, monkeypatch) -> None:
    """Proxy công ty hay trả trang HTML đăng nhập với mã 200 — không được coi
    đó là "không có model nào"."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_Response(200, None, text="<html>Đăng nhập proxy</html>"))

    with pytest.raises(LlmUnavailable):
        llm_model_service.liet_ke_models()


def test_nha_cung_cap_tra_danh_sach_rong_thi_bao_loi(gia_lap, monkeypatch) -> None:
    """Không model nào là chuyện bất thường (key chưa bật API, sai dự án).
    Trả ô chọn trống mà không nói gì thì người dùng ngồi đoán."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_Response(200, {"object": "list", "data": []}))

    with pytest.raises(LlmUnavailable):
        llm_model_service.liet_ke_models()


def test_co_model_nhung_khong_model_nao_dung_de_dich_van_tra_ve_binh_thuong(
    gia_lap, monkeypatch
) -> None:
    """Khác hẳn ca trên: nhà cung cấp trả về đàng hoàng, chỉ là toàn model sinh
    ảnh/video. Đó là dữ liệu THẬT, không phải lỗi — trả nhóm rỗng, đừng ném."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_ok(["veo-3.1-generate-preview", "imagen-4.0-generate-001"]))

    ket_qua = llm_model_service.liet_ke_models()

    assert ket_qua.translate == []
    assert ket_qua.tts == []


# --- Không rò khoá API -------------------------------------------------


def test_khoa_api_khong_lot_vao_thong_bao_loi_cua_nha_cung_cap(gia_lap, monkeypatch) -> None:
    """Nhiều nhà cung cấp chèn nguyên URL kèm ``?key=...`` vào thân lỗi."""
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(
        _Response(400, {"error": {"message": f"Sai tham số ở /models?key={KHOA}"}})
    )

    with pytest.raises(LlmUnavailable) as loi:
        llm_model_service.liet_ke_models()

    assert KHOA not in loi.value.message
    assert KHOA not in str(loi.value.detail)


def test_khoa_api_khong_lot_vao_thong_bao_loi_mang(gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(httpx.ConnectError(f"gọi https://x/models?key={KHOA} hỏng"))

    with pytest.raises(LlmUnavailable) as loi:
        llm_model_service.liet_ke_models()

    assert KHOA not in loi.value.message


# --- Tầng HTTP ---------------------------------------------------------


@pytest.fixture
def http_client():
    """TestClient tối giản chỉ gắn router llm — kiểm status code và mã lỗi
    THẬT sự trả ra cho frontend."""
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(llm_router.router, prefix="/api/v1")
    with TestClient(app) as client:
        yield client


def test_http_tra_ve_hai_nhom_model(http_client, gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_ok(ID_THAT))

    resp = http_client.get("/api/v1/llm/models")

    assert resp.status_code == 200
    assert resp.json() == {
        "translate": ["gemini-3.5-flash-lite", "gemini-2.5-pro"],
        "tts": ["gemini-2.5-flash-tts"],
        #: Cấu hình test không đặt LLM_MODEL nên không có gì để chọn sẵn.
        "default": "",
    }


def test_http_key_sai_tra_loi_co_ma_rieng_khong_phai_200_rong(
    http_client, gia_lap, monkeypatch
) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(_Response(403, {"error": {"message": "khoá bị từ chối"}}))

    resp = http_client.get("/api/v1/llm/models")

    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "LLM_AUTH_FAILED"


def test_http_mang_loi_tra_502_khong_phai_500(http_client, gia_lap, monkeypatch) -> None:
    _cau_hinh(monkeypatch)
    gia_lap["hang_doi"].append(httpx.ConnectError("mạng rớt"))

    resp = http_client.get("/api/v1/llm/models")

    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "LLM_UNAVAILABLE"


def test_tra_ve_model_mac_dinh_de_giao_dien_chon_san(http_client, gia_lap, monkeypatch) -> None:
    """Không nói rõ mặc định thì ô chọn lấy option ĐẦU danh sách.

    Nhìn ảnh chụp giao diện thật (2026-08-15): ô chọn hiện `gemini-2.5-flash`
    — 20 lượt/NGÀY — trong khi cấu hình để `gemini-3.5-flash-lite` với 500
    lượt/ngày. Ai bấm nhanh dính đúng model tệ nhất về hạn mức mà không biết.
    """
    _cau_hinh(monkeypatch, llm_model="gemini-3.5-flash-lite")
    gia_lap["hang_doi"].append(_ok(ID_THAT))

    ra = http_client.get("/api/v1/llm/models").json()

    assert ra["default"] == "gemini-3.5-flash-lite"


def test_mac_dinh_khong_nam_trong_danh_sach_thi_tra_ve_rong(
    http_client, gia_lap, monkeypatch
) -> None:
    """Cấu hình trỏ tới model mà khoá hiện tại không dùng được — thà để giao
    diện tự chọn option đầu còn hơn chọn sẵn một model gọi là hỏng."""
    _cau_hinh(monkeypatch, llm_model="model-khong-co-that")
    gia_lap["hang_doi"].append(_ok(ID_THAT))

    ra = http_client.get("/api/v1/llm/models").json()

    assert ra["default"] == ""
