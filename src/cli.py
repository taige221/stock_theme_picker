from __future__ import annotations

import argparse
import os
from pathlib import Path

from theme_picker.config import REPO_ROOT, ensure_local_env_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Theme Picker standalone CLI")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="初始化本地运行所需的 .env 文件")
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="即使 .env 已存在，也强制用 .env.example 重新生成",
    )
    init_parser.add_argument(
        "--env-file",
        default=os.getenv("ENV_FILE") or str(REPO_ROOT / ".env"),
        help="目标 env 文件路径，默认使用仓库根目录 .env",
    )
    init_parser.add_argument(
        "--example-file",
        default=str(REPO_ROOT / ".env.example"),
        help="示例 env 文件路径，默认使用仓库根目录 .env.example",
    )

    return parser


def _run_init(args: argparse.Namespace) -> int:
    created, env_path = ensure_local_env_file(
        env_path=Path(args.env_file),
        example_path=Path(args.example_file),
        force=args.force,
    )
    if created:
        print(f"[theme_picker] 已生成本地配置文件: {env_path}")
    else:
        print(f"[theme_picker] 本地配置文件已存在，无需生成: {env_path}")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "init":
        return _run_init(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
