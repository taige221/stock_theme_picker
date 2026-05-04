# -*- coding: utf-8 -*-
"""Local launcher for standalone theme picker service."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))


def main() -> None:
    parser = argparse.ArgumentParser(description="Theme Picker standalone launcher")
    parser.add_argument("--serve", action="store_true", help="启动 FastAPI 服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    args = parser.parse_args()

    if args.serve:
        import uvicorn

        uvicorn.run(
            "server:app",
            host=args.host,
            port=args.port,
            reload=False,
            app_dir=str(CURRENT_DIR),
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()

