# -*- coding: utf-8 -*-
"""Standalone FastAPI entrypoint for theme picker."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from theme_picker.api.endpoints import router as theme_picker_router  # noqa: E402

app = FastAPI(
    title="Theme Picker API",
    description="独立主题选股服务",
    version="0.1.0",
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

