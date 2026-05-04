# -*- coding: utf-8 -*-
"""Local launcher for standalone theme picker service."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from theme_picker.config import ensure_local_env_file

DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8765
DEFAULT_WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 5183
WEB_DIR = CURRENT_DIR / "web"


def _backend_base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _run_backend(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=False,
        app_dir=str(CURRENT_DIR),
    )


def _ensure_web_runtime() -> str:
    npm_path = shutil.which("npm")
    if not npm_path:
        raise RuntimeError("未找到 npm，请先安装 Node.js / npm 后再运行前端。")
    if not WEB_DIR.is_dir():
        raise RuntimeError(f"前端目录不存在: {WEB_DIR}")
    return npm_path


def _run_web(host: str, port: int, *, backend_url: str) -> None:
    npm_path = _ensure_web_runtime()
    env = os.environ.copy()
    env["VITE_API_URL"] = backend_url
    env["VITE_DEV_PROXY_TARGET"] = backend_url
    subprocess.run(
        [npm_path, "run", "dev", "--", "--host", host, "--port", str(port)],
        cwd=str(WEB_DIR),
        env=env,
        check=True,
    )


def _terminate_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _run_all(host: str, port: int, *, web_host: str, web_port: int) -> None:
    npm_path = _ensure_web_runtime()
    backend_process: subprocess.Popen[bytes] | None = None
    frontend_process: subprocess.Popen[bytes] | None = None
    backend_url = _backend_base_url(host, port)

    env = os.environ.copy()
    env["VITE_API_URL"] = backend_url
    env["VITE_DEV_PROXY_TARGET"] = backend_url

    try:
        backend_process = subprocess.Popen(
            [sys.executable, "main.py", "--serve", "--host", host, "--port", str(port)],
            cwd=str(CURRENT_DIR),
            env=os.environ.copy(),
        )
        frontend_process = subprocess.Popen(
            [npm_path, "run", "dev", "--", "--host", web_host, "--port", str(web_port)],
            cwd=str(WEB_DIR),
            env=env,
        )
        print(f"[theme_picker] backend: {backend_url}")
        print(f"[theme_picker] web: http://{web_host}:{web_port}/theme-picker")

        while True:
            backend_code = backend_process.poll()
            frontend_code = frontend_process.poll()
            if backend_code is not None:
                raise RuntimeError(f"后端进程已退出，code={backend_code}")
            if frontend_code is not None:
                raise RuntimeError(f"前端进程已退出，code={frontend_code}")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        _terminate_process(frontend_process)
        _terminate_process(backend_process)


def main() -> None:
    parser = argparse.ArgumentParser(description="Theme Picker standalone launcher")
    parser.add_argument("--init-env", action="store_true", help="从 .env.example 初始化本地 .env")
    parser.add_argument("--serve", action="store_true", help="启动 FastAPI 服务")
    parser.add_argument("--serve-web", action="store_true", help="启动前端开发服务")
    parser.add_argument("--serve-all", action="store_true", help="同时启动前后端")
    parser.add_argument("--host", default=DEFAULT_BACKEND_HOST, help="后端监听地址")
    parser.add_argument("--port", type=int, default=DEFAULT_BACKEND_PORT, help="后端监听端口")
    parser.add_argument("--web-host", default=DEFAULT_WEB_HOST, help="前端监听地址")
    parser.add_argument("--web-port", type=int, default=DEFAULT_WEB_PORT, help="前端监听端口")
    args = parser.parse_args()

    if args.init_env:
        created, env_path = ensure_local_env_file()
        if created:
            print(f"[theme_picker] 已生成本地配置文件: {env_path}")
        else:
            print(f"[theme_picker] 本地配置文件已存在，无需生成: {env_path}")
        return

    if args.serve:
        _run_backend(args.host, args.port)
        return

    backend_url = _backend_base_url(args.host, args.port)

    if args.serve_web:
        _run_web(args.web_host, args.web_port, backend_url=backend_url)
        return

    if args.serve_all:
        _run_all(args.host, args.port, web_host=args.web_host, web_port=args.web_port)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
