"""Điểm vào của API.

Router chỉ validate input, gọi service, trả response — không chứa logic nghiệp vụ.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from reup_core.logging import get_logger, setup_logging

from .config import get_settings
from .errors import ApiError, api_error_handler
from .routers import ai_providers as ai_providers_router
from .routers import (
    giong_doc,
    health,
    llm,
    platform_limits,
    presets,
    render,
    source_channels,
    videos,
    ws,
)
from .routers import settings as settings_router
from .ws.manager import WsManager

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    app.state.ws_manager = WsManager(settings.redis_url)
    await app.state.ws_manager.start()
    log.info("api.started")
    yield
    await app.state.ws_manager.stop()


app = FastAPI(
    title="ReupStudio API",
    version="0.1.0",
    description="Tự động lấy video Trung Quốc, dịch sang tiếng Việt và đăng lên nền tảng video ngắn.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(ApiError, api_error_handler)

API_PREFIX = "/api/v1"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(videos.router, prefix=API_PREFIX)
app.include_router(presets.router, prefix=API_PREFIX)
app.include_router(source_channels.router, prefix=API_PREFIX)
app.include_router(platform_limits.router, prefix=API_PREFIX)
app.include_router(render.router, prefix=API_PREFIX)
app.include_router(llm.router, prefix=API_PREFIX)
app.include_router(settings_router.router, prefix=API_PREFIX)
app.include_router(ai_providers_router.router, prefix=API_PREFIX)
app.include_router(giong_doc.router, prefix=API_PREFIX)
app.include_router(ws.router)


@app.get("/")
def root() -> dict:
    return {"name": "ReupStudio API", "docs": "/docs", "health": f"{API_PREFIX}/health"}
