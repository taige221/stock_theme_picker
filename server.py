# -*- coding: utf-8 -*-
"""Standalone FastAPI entrypoint for theme picker."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from theme_picker.api.endpoints import router as theme_picker_router  # noqa: E402
from theme_picker.api.market_endpoints import router as market_router  # noqa: E402
from theme_picker.api.stock_query_endpoints import router as stock_query_router  # noqa: E402
from theme_picker.api.watchlist_endpoints import router as watchlist_router  # noqa: E402
from theme_picker.application.stock_alert_loop_service import StockAlertLoopService  # noqa: E402
from theme_picker.config import get_config  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    alert_loop = None
    if bool(getattr(cfg, "stock_alert_loop_enabled", False)):
        alert_loop = StockAlertLoopService(
            base_tick_seconds=int(getattr(cfg, "stock_alert_loop_base_tick_seconds", 60) or 60),
        )
        alert_loop.start()
        app.state.stock_alert_loop = alert_loop
    try:
        yield
    finally:
        if alert_loop is not None:
            alert_loop.stop()

app = FastAPI(
    title="Theme Picker API",
    description="独立主题选股服务",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    theme_picker_router,
    prefix="/api/v1/theme-picker",
    tags=["theme-picker"],
)

app.include_router(
    stock_query_router,
    prefix="/api/v1/stock-query",
    tags=["stock-query"],
)

app.include_router(
    market_router,
    prefix="/api/v1/market",
    tags=["market"],
)

app.include_router(
    watchlist_router,
    prefix="/api/v1/watchlist",
    tags=["watchlist"],
)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def run() -> None:
    import uvicorn

    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
        app_dir=str(CURRENT_DIR),
    )


if __name__ == "__main__":
    run()
