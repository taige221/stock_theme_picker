# -*- coding: utf-8 -*-
"""Import strategy backtest JSON artifacts into the local DuckDB database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from theme_picker.application.backtest_import_service import BacktestImportService  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import backtest summary.json and per-stock JSON detail files")
    parser.add_argument(
        "--source",
        required=True,
        help="summary.json path, its parent directory, or a directory scanned recursively with --recursive",
    )
    parser.add_argument("--stock-pool", help="Optional stock pool JSON path")
    parser.add_argument("--mode", default="upsert", choices=("upsert",), help="Import mode")
    parser.add_argument(
        "--equity-mode",
        default="traded_daily",
        choices=("portfolio_only", "traded_daily", "all_daily"),
        help=(
            "How much equity-curve detail to persist: portfolio_only stores only the portfolio curve; "
            "traded_daily stores portfolio plus active symbol holding days; all_daily stores every symbol day"
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and count rows without writing")
    parser.add_argument("--recursive", action="store_true", help="Import every summary.json under --source")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt used by recursive imports",
    )
    return parser.parse_args()


def find_sources(source: Path, recursive: bool) -> list[Path]:
    if recursive:
        root = source
        if root.is_file():
            root = root.parent
        return sorted(root.rglob("summary.json"))
    if source.is_dir():
        direct_summary = source / "summary.json"
        if not direct_summary.exists():
            nested_summaries = sorted(source.rglob("summary.json"))
            if nested_summaries:
                print(
                    f"Found {len(nested_summaries)} nested summary.json files under {source}. "
                    "Use --recursive to import them.",
                    file=sys.stderr,
                )
                return []
        return [direct_summary]
    return [source]


def confirm_recursive_import(sources: list[Path], *, assume_yes: bool) -> None:
    if assume_yes or len(sources) <= 1:
        return
    print(
        f"Recursive import will write {len(sources)} backtest summaries into DuckDB. "
        "Close other import/server writers if you see a lock.",
        file=sys.stderr,
    )
    if not sys.stdin.isatty():
        print("Non-interactive shell detected; continuing. Pass --yes to silence this message.", file=sys.stderr)
        return
    answer = input("Continue recursive import? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise SystemExit("Cancelled.")


def main() -> int:
    args = parse_args()
    service = BacktestImportService(project_root=ROOT_DIR)
    source = Path(args.source)
    sources = find_sources(source, args.recursive)
    if not sources:
        print(f"No summary.json found at {source}.", file=sys.stderr)
        return 1
    confirm_recursive_import(sources, assume_yes=args.yes)

    results = []
    for item in sources:
        try:
            result = service.import_artifact(
                item,
                stock_pool_path=args.stock_pool,
                mode=args.mode,
                dry_run=args.dry_run,
                equity_mode=args.equity_mode,
            )
        except (RuntimeError, OperationalError) as exc:
            text = str(exc)
            if "database is locked" in text.lower() or "single-writer" in text.lower() or "conflicting lock" in text.lower():
                print(
                    "Import failed: DuckDB database is locked. Backtest import writes must run one at a time; "
                    "stop other theme_picker servers/import jobs or retry after the current write finishes.",
                    file=sys.stderr,
                )
                return 2
            raise
        results.append(result.to_dict())
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    if len(results) > 1:
        total = {
            "imports": len(results),
            "finished": sum(1 for item in results if item["status"] in {"finished", "dry_run"}),
            "symbols_imported": sum(item["counts"].get("symbols_imported", 0) for item in results),
            "trades_imported": sum(item["counts"].get("trades_imported", 0) for item in results),
            "symbol_equity_points_imported": sum(
                item["counts"].get("symbol_equity_points_imported", 0) for item in results
            ),
            "portfolio_equity_points_imported": sum(
                item["counts"].get("portfolio_equity_points_imported", 0) for item in results
            ),
        }
        print(json.dumps({"total": total}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
