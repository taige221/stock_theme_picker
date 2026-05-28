# -*- coding: utf-8 -*-
"""Run batch daily-bar backtests and save per-symbol plus summary outputs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path
import re

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from theme_picker.backtest.data_feed import DailyBarDataFeed
from theme_picker.backtest.engine import BacktestEngine
from theme_picker.backtest.models import BacktestConfig
from theme_picker.strategy import STRATEGY_REGISTRY, StrategyParams, create_strategy
from sqlalchemy.exc import OperationalError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run batch daily-bar backtests")
    parser.add_argument(
        "--stock-codes",
        required=True,
        help="Comma-separated stock codes or a JSON file path containing stock codes",
    )
    parser.add_argument("--start-date", required=True, help="Start date in YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date in YYYY-MM-DD")
    parser.add_argument(
        "--strategy",
        default="a_share_box",
        choices=tuple(sorted(STRATEGY_REGISTRY.keys())),
        help="Strategy name, default a_share_box",
    )
    parser.add_argument("--params-file", help="Optional JSON file with StrategyParams overrides")
    parser.add_argument(
        "--price-adjustment",
        default="raw",
        choices=("raw", "qfq"),
        help="Price series used by the backtest, default raw",
    )
    parser.add_argument(
        "--trading-constraints",
        default="legacy_pct",
        choices=("legacy_pct", "daily_limits"),
        help="Constraint model for涨跌停/停牌, default legacy_pct",
    )
    parser.add_argument("--output-dir", help="Optional batch output directory")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately when any stock fails instead of continuing",
    )
    parser.add_argument(
        "--import-db",
        action="store_true",
        help="Import the generated summary.json and per-stock details into DuckDB after the batch finishes",
    )
    parser.add_argument(
        "--import-stock-pool",
        help="Optional stock pool JSON path used by the DB import; defaults to --stock-codes when it is a JSON file",
    )
    parser.add_argument(
        "--import-dry-run",
        action="store_true",
        help="Validate and count generated artifacts without writing DB rows when used with --import-db",
    )
    parser.add_argument(
        "--import-equity-mode",
        default="traded_daily",
        choices=("portfolio_only", "traded_daily", "all_daily"),
        help=(
            "DB import equity detail: portfolio_only, traded_daily "
            "(portfolio plus active symbol holding days), or all_daily"
        ),
    )
    return parser.parse_args()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_stock_codes(value: str) -> list[str]:
    candidate = Path(str(value or "").strip())
    if candidate.is_file() and candidate.suffix.lower() == ".json":
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        items = _extract_stock_codes_from_json(payload)
        if not items:
            raise ValueError(f"JSON 文件中没有可用的 stock_code: {candidate}")
        return items

    items: list[str] = []
    for raw in str(value or "").split(","):
        code = str(raw or "").strip().upper()
        if code and code not in items:
            items.append(code)
    if not items:
        raise ValueError("stock_codes 不能为空")
    return items


def _extract_stock_codes_from_json(payload) -> list[str]:
    items: list[str] = []

    def add_code(value) -> None:
        code = str(value or "").strip().upper()
        if code and code not in items:
            items.append(code)

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                add_code(item)
            elif isinstance(item, dict):
                add_code(item.get("stock_code"))
        return items

    if isinstance(payload, dict):
        stock_codes = payload.get("stock_codes")
        if isinstance(stock_codes, list):
            for item in stock_codes:
                if isinstance(item, str):
                    add_code(item)
                elif isinstance(item, dict):
                    add_code(item.get("stock_code"))

        results = payload.get("results")
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    add_code(item.get("stock_code"))

    return items


def load_strategy_params(params_file: str | None) -> StrategyParams:
    if not params_file:
        return StrategyParams()
    payload = json.loads(Path(params_file).read_text(encoding="utf-8"))
    return StrategyParams.from_dict(payload)


_LATE_START_RE = re.compile(r"缓存起始日期为\s+(\d{4}-\d{2}-\d{2})，晚于请求起点\s+(\d{4}-\d{2}-\d{2})")


def main() -> int:
    args = parse_args()
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    if end_date < start_date:
        raise ValueError("end_date 不能早于 start_date")

    stock_codes = parse_stock_codes(args.stock_codes)
    params = load_strategy_params(args.params_file)
    config = BacktestConfig(
        price_adjustment=args.price_adjustment,
        trading_constraint_mode=args.trading_constraints,
    )
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = BacktestEngine()
    data_feed = DailyBarDataFeed()
    strategy = create_strategy(args.strategy)
    summary_rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []

    for stock_code in stock_codes:
        try:
            effective_start_date = start_date
            bars = data_feed.load(
                stock_code,
                start_date=effective_start_date,
                end_date=end_date,
                price_adjustment=config.price_adjustment,
            )
        except ValueError as exc:
            adjusted_start_date = _resolve_adjusted_start_date(
                data_feed=data_feed,
                stock_code=stock_code,
                requested_start_date=start_date,
                end_date=end_date,
                price_adjustment=config.price_adjustment,
                error=exc,
            )
            if adjusted_start_date is None:
                error_row = {
                    "stock_code": stock_code,
                    "status": "error",
                    "error": str(exc),
                }
                errors.append(error_row)
                summary_rows.append(error_row)
                print(json.dumps(error_row, ensure_ascii=False))
                if args.fail_fast:
                    break
                continue
            try:
                effective_start_date = adjusted_start_date
                bars = data_feed.load(
                    stock_code,
                    start_date=effective_start_date,
                    end_date=end_date,
                    price_adjustment=config.price_adjustment,
                )
            except Exception as retry_exc:
                error_row = {
                    "stock_code": stock_code,
                    "status": "error",
                    "error": str(retry_exc),
                }
                errors.append(error_row)
                summary_rows.append(error_row)
                print(json.dumps(error_row, ensure_ascii=False))
                if args.fail_fast:
                    break
                continue

        try:
            result = engine.run(
                stock_code=stock_code,
                bars=bars,
                strategy=strategy,
                params=params,
                config=config,
            )
            output_path = output_dir / f"{stock_code.replace('.', '_')}.json"
            output_path.write_text(
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            metrics = dict(result.metrics)
            row = {
                "stock_code": stock_code,
                "status": "ok",
                "strategy": args.strategy,
                "price_adjustment": config.price_adjustment,
                "trading_constraints": config.trading_constraint_mode,
                "requested_start_date": start_date.isoformat(),
                "effective_start_date": effective_start_date.isoformat(),
                "result_path": str(output_path),
                **metrics,
            }
            summary_rows.append(row)
            print(
                json.dumps(
                    {
                        "stock_code": stock_code,
                        "status": "ok",
                        "effective_start_date": effective_start_date.isoformat(),
                        "total_return_pct": metrics.get("total_return_pct"),
                        "max_drawdown_pct": metrics.get("max_drawdown_pct"),
                        "trade_count": metrics.get("trade_count"),
                        "result_path": str(output_path),
                    },
                    ensure_ascii=False,
                )
            )
        except Exception as exc:
            error_row = {
                "stock_code": stock_code,
                "status": "error",
                "error": str(exc),
            }
            errors.append(error_row)
            summary_rows.append(error_row)
            print(json.dumps(error_row, ensure_ascii=False))
            if args.fail_fast:
                break

    summary_path = output_dir / "summary.json"
    summary_payload = {
        "generated_at": datetime.now().isoformat(),
        "strategy": args.strategy,
        "price_adjustment": config.price_adjustment,
        "trading_constraints": config.trading_constraint_mode,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "params": params.to_dict(),
        "aggregate": _build_aggregate_summary(summary_rows),
        "results": summary_rows,
    }
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_csv_path = output_dir / "summary.csv"
    _write_summary_csv(summary_csv_path, summary_rows)

    print(f"saved_summary={summary_path}")
    print(f"saved_summary_csv={summary_csv_path}")

    if args.import_db:
        try:
            import_result = _import_generated_summary(
                summary_path,
                stock_pool_path=args.import_stock_pool or _default_import_stock_pool(args.stock_codes),
                dry_run=args.import_dry_run,
                equity_mode=args.import_equity_mode,
            )
        except (RuntimeError, OperationalError) as exc:
            text = str(exc)
            if "database is locked" in text.lower() or "single-writer" in text.lower() or "conflicting lock" in text.lower():
                print(
                    "import_failed=database_locked "
                    "Backtest import writes must run one at a time; stop other theme_picker writers and retry.",
                    file=sys.stderr,
                )
                return 2
            raise
        print("import_result=" + json.dumps(import_result, ensure_ascii=False))

    if errors and args.fail_fast:
        return 1
    return 0


def _write_summary_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "stock_code",
        "status",
        "strategy",
        "price_adjustment",
        "trading_constraints",
        "requested_start_date",
        "effective_start_date",
        "initial_cash",
        "final_equity",
        "total_return_pct",
        "max_drawdown_pct",
        "trade_count",
        "win_rate_pct",
        "avg_win_pct",
        "avg_loss_pct",
        "profit_factor",
        "has_open_position",
        "open_position_market_value",
        "final_unrealized_pnl",
        "final_unrealized_pnl_pct",
        "max_trade_mfe_pct",
        "max_trade_mae_pct",
        "result_path",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            normalized = {key: row.get(key) for key in fieldnames}
            writer.writerow(normalized)


def _default_output_dir() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ROOT_DIR / "data" / "backtests" / f"batch_{timestamp}"


def _build_aggregate_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    total_symbols = len(rows)
    error_symbols = len([row for row in rows if row.get("status") == "error"])
    profitable_symbols = len([row for row in ok_rows if float(row.get("total_return_pct") or 0.0) > 0])
    losing_symbols = len([row for row in ok_rows if float(row.get("total_return_pct") or 0.0) < 0])
    flat_symbols = len(ok_rows) - profitable_symbols - losing_symbols
    total_initial_cash = sum(float(row.get("initial_cash") or 0.0) for row in ok_rows)
    total_final_equity = sum(float(row.get("final_equity") or 0.0) for row in ok_rows)
    total_pnl = total_final_equity - total_initial_cash
    total_trade_count = sum(int(row.get("trade_count") or 0) for row in ok_rows)
    total_final_unrealized_pnl = sum(float(row.get("final_unrealized_pnl") or 0.0) for row in ok_rows)
    open_position_symbols = len([row for row in ok_rows if bool(row.get("has_open_position"))])
    average_return_pct = (
        sum(float(row.get("total_return_pct") or 0.0) for row in ok_rows) / len(ok_rows) if ok_rows else 0.0
    )
    aggregate_return_pct = (total_pnl / total_initial_cash * 100.0) if total_initial_cash else 0.0
    return {
        "total_symbols": total_symbols,
        "ok_symbols": len(ok_rows),
        "error_symbols": error_symbols,
        "profitable_symbols": profitable_symbols,
        "losing_symbols": losing_symbols,
        "flat_symbols": flat_symbols,
        "total_initial_cash": round(total_initial_cash, 2),
        "total_final_equity": round(total_final_equity, 2),
        "total_pnl": round(total_pnl, 2),
        "aggregate_return_pct": round(aggregate_return_pct, 2),
        "average_return_pct": round(average_return_pct, 2),
        "total_trade_count": total_trade_count,
        "total_final_unrealized_pnl": round(total_final_unrealized_pnl, 2),
        "open_position_symbols": open_position_symbols,
    }


def _default_import_stock_pool(stock_codes_arg: str) -> str | None:
    candidate = Path(str(stock_codes_arg or "").strip())
    if candidate.is_file() and candidate.suffix.lower() == ".json":
        return str(candidate)
    return None


def _import_generated_summary(
    summary_path: Path,
    *,
    stock_pool_path: str | None,
    dry_run: bool,
    equity_mode: str,
) -> dict[str, object]:
    from theme_picker.application.backtest_import_service import BacktestImportService

    service = BacktestImportService(project_root=ROOT_DIR)
    result = service.import_artifact(
        summary_path,
        stock_pool_path=stock_pool_path,
        dry_run=dry_run,
        equity_mode=equity_mode,
    )
    return result.to_dict()


def _resolve_adjusted_start_date(
    *,
    data_feed: DailyBarDataFeed,
    stock_code: str,
    requested_start_date: date,
    end_date: date,
    price_adjustment: str,
    error: Exception,
) -> date | None:
    match = _LATE_START_RE.search(str(error))
    if not match:
        return None
    available_start_date = data_feed.resolve_available_start_date(
        stock_code,
        start_date=requested_start_date,
        end_date=end_date,
        price_adjustment=price_adjustment,
    )
    if available_start_date is None or available_start_date <= requested_start_date:
        return None
    print(
        json.dumps(
            {
                "stock_code": stock_code,
                "status": "adjusted_start_date",
                "requested_start_date": requested_start_date.isoformat(),
                "effective_start_date": available_start_date.isoformat(),
            },
            ensure_ascii=False,
        )
    )
    return available_start_date


if __name__ == "__main__":
    raise SystemExit(main())
