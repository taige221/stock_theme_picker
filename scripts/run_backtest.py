# -*- coding: utf-8 -*-
"""Run the minimal A-share backtest loop from the command line."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from theme_picker.backtest.data_feed import DailyBarDataFeed
from theme_picker.backtest.engine import BacktestEngine
from theme_picker.backtest.models import BacktestConfig
from theme_picker.strategy import STRATEGY_REGISTRY, StrategyParams, create_strategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run minimal daily-bar backtest")
    parser.add_argument("--stock-code", required=True, help="Stock code such as 000001.SZ")
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
    parser.add_argument("--output", help="Optional output JSON path")
    return parser.parse_args()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_strategy_params(params_file: str | None) -> StrategyParams:
    if not params_file:
        return StrategyParams()
    payload = json.loads(Path(params_file).read_text(encoding="utf-8"))
    return StrategyParams.from_dict(payload)


def main() -> int:
    args = parse_args()
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    if end_date < start_date:
        raise ValueError("end_date 不能早于 start_date")

    params = load_strategy_params(args.params_file)
    config = BacktestConfig(
        price_adjustment=args.price_adjustment,
        trading_constraint_mode=args.trading_constraints,
    )
    data_feed = DailyBarDataFeed()
    bars = data_feed.load(
        args.stock_code,
        start_date=start_date,
        end_date=end_date,
        price_adjustment=config.price_adjustment,
    )

    engine = BacktestEngine()
    strategy = create_strategy(args.strategy)
    result = engine.run(
        stock_code=args.stock_code,
        bars=bars,
        strategy=strategy,
        params=params,
        config=config,
    )

    output_path = Path(args.output) if args.output else _default_output_path(args.stock_code)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "stock_code": args.stock_code,
                "strategy": args.strategy,
                "price_adjustment": config.price_adjustment,
                "trading_constraints": config.trading_constraint_mode,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(json.dumps(result.metrics, ensure_ascii=False, indent=2))
    print(f"saved_result={output_path}")
    return 0


def _default_output_path(stock_code: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_code = stock_code.replace(".", "_")
    return ROOT_DIR / "data" / "backtests" / f"{timestamp}-{safe_code}.json"


if __name__ == "__main__":
    raise SystemExit(main())
