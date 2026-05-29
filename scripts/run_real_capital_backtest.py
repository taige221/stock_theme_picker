# -*- coding: utf-8 -*-
"""Run real-capital portfolio simulation from imported backtest trades."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
PARENT_DIR = ROOT_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    from theme_picker.backtest.analysis.real_capital import (
        RealCapitalConfig,
        dumps_json,
        load_price_series_from_duckdb,
        load_trading_days_from_duckdb,
        simulate_real_capital_portfolio,
    )
    from theme_picker.backtest.analysis.signal_ranking import (
        LayeredRankingConfig,
        load_db_backtest_runs,
        normalize_trade_candidate,
        parse_iso_date,
        rank_trade_candidates,
    )
except ModuleNotFoundError:
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from src.backtest.analysis.real_capital import (  # type: ignore[no-redef]
        RealCapitalConfig,
        dumps_json,
        load_price_series_from_duckdb,
        load_trading_days_from_duckdb,
        simulate_real_capital_portfolio,
    )
    from src.backtest.analysis.signal_ranking import (  # type: ignore[no-redef]
        LayeredRankingConfig,
        load_db_backtest_runs,
        normalize_trade_candidate,
        parse_iso_date,
        rank_trade_candidates,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real-capital portfolio backtest from ranked trades")
    parser.add_argument("--db-run-id", required=True, help="Imported backtest run_id")
    parser.add_argument("--database-path", help="DuckDB path. Defaults to DATABASE_PATH or data/stock_analysis.duckdb")
    parser.add_argument("--output-dir", help="Output directory")

    parser.add_argument("--rank-mode", choices=("signal_score", "cohort_ev", "cohort_ev_walk_forward"), default="signal_score")
    parser.add_argument("--max-per-day", type=int, default=3)
    parser.add_argument("--pullback-quota", type=int, default=2)
    parser.add_argument("--breakout-quota", type=int, default=1)
    parser.add_argument("--ranking-max-open-positions", type=int, default=8)
    parser.add_argument("--min-cohort-trades", type=int, default=8)
    parser.add_argument("--min-rank-score", type=float)
    parser.add_argument("--no-fill", action="store_true")

    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--position-size-pct", type=float, default=0.10)
    parser.add_argument("--account-max-positions", type=int, default=8)
    parser.add_argument("--lot-size", type=int, default=100)
    parser.add_argument("--commission-bps", type=float, default=10.0)
    parser.add_argument("--min-commission", type=float, default=5.0)
    parser.add_argument("--stamp-tax-bps", type=float, default=5.0)
    parser.add_argument("--transfer-fee-bps", type=float, default=0.1)
    parser.add_argument("--price-adjustment", choices=("raw", "qfq"), default="qfq")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir(args.db_run_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    loaded_runs = load_db_backtest_runs([args.db_run_id], database_path=args.database_path, root_dir=ROOT_DIR)
    loaded = loaded_runs[0]
    ranking_config = LayeredRankingConfig(
        rank_mode=args.rank_mode,
        max_per_day=args.max_per_day,
        pullback_quota=args.pullback_quota,
        breakout_quota=args.breakout_quota,
        max_open_positions=args.ranking_max_open_positions,
        min_cohort_trades=args.min_cohort_trades,
        min_rank_score=args.min_rank_score,
        fill_unused_slots=not args.no_fill,
    ).normalized()
    account_config = RealCapitalConfig(
        initial_cash=args.initial_cash,
        position_size_pct=args.position_size_pct,
        max_positions=args.account_max_positions,
        lot_size=args.lot_size,
        commission_bps=args.commission_bps,
        min_commission=args.min_commission,
        stamp_tax_bps=args.stamp_tax_bps,
        transfer_fee_bps=args.transfer_fee_bps,
        price_adjustment=args.price_adjustment,
    ).normalized()

    normalized_trades = [
        normalize_trade_candidate(trade, run_name=loaded.run_name)
        for trade in loaded.trades
        if trade.get("entry_date")
    ]
    ranked_rows = rank_trade_candidates(normalized_trades, run_name=loaded.run_name, config=ranking_config)
    selected_rows = [row for row in ranked_rows if row.get("selected")]
    start_date, end_date = _selected_date_range(selected_rows, fallback_start=loaded.start_date, fallback_end=loaded.end_date)
    price_series = load_price_series_from_duckdb(
        sorted({str(row.get("stock_code") or "") for row in selected_rows if row.get("stock_code")}),
        database_path=args.database_path,
        start_date=start_date,
        end_date=end_date,
        price_adjustment=args.price_adjustment,
    )
    trading_days = load_trading_days_from_duckdb(
        database_path=args.database_path,
        start_date=start_date,
        end_date=end_date,
    )
    result = simulate_real_capital_portfolio(
        ranked_rows,
        config=account_config,
        price_series=price_series,
        trading_days=trading_days,
        run_name=loaded.run_name,
    )
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_run": {
            "run_id": loaded.run_id,
            "run_name": loaded.run_name,
            "source_path": loaded.source_path,
            "strategy": loaded.strategy,
            "start_date": loaded.start_date,
            "end_date": loaded.end_date,
            "aggregate": loaded.aggregate,
        },
        "ranking_config": ranking_config.to_dict(),
        "account_config": account_config.to_dict(),
        "price_context": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "price_adjustment": args.price_adjustment,
            "symbols_requested": len({row.get("stock_code") for row in selected_rows if row.get("stock_code")}),
            "symbols_with_prices": len(price_series),
            "trading_days": len(trading_days),
        },
        **result,
    }

    _write_csv(output_dir / "ranked_candidates.csv", ranked_rows)
    _write_csv(output_dir / "account_equity_curve.csv", result["equity_curve"])
    _write_csv(output_dir / "account_trades.csv", result["trades"])
    _write_csv(output_dir / "account_opened_trades.csv", result["opened_trades"])
    _write_csv(output_dir / "account_skipped_candidates.csv", result["skipped_candidates"])
    _write_csv(output_dir / "account_yearly_returns.csv", result["yearly_returns"])
    _write_csv(output_dir / "account_monthly_returns.csv", result["monthly_returns"])
    summary_path = output_dir / "account_summary.json"
    diagnostics_path = output_dir / "account_diagnostics.json"
    result_path = output_dir / "account_result.json"
    summary_path.write_text(
        dumps_json(
            {
                "generated_at": payload["generated_at"],
                "source_run": payload["source_run"],
                "ranking_config": payload["ranking_config"],
                "account_config": payload["account_config"],
                "price_context": payload["price_context"],
                "summary": result["summary"],
                "diagnostics": result["diagnostics"],
            }
        ),
        encoding="utf-8",
    )
    diagnostics_path.write_text(dumps_json(result["diagnostics"]), encoding="utf-8")
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("real capital summary:")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"saved_account_summary={summary_path}")
    print(f"saved_account_result={result_path}")
    print(f"saved_account_diagnostics={diagnostics_path}")
    print(f"saved_account_trades={output_dir / 'account_trades.csv'}")
    print(f"saved_account_equity_curve={output_dir / 'account_equity_curve.csv'}")
    return 0


def _selected_date_range(
    selected_rows: list[dict[str, Any]],
    *,
    fallback_start: str | None,
    fallback_end: str | None,
) -> tuple[Any, Any]:
    dates = []
    for row in selected_rows:
        for key in ("entry_date", "exit_date"):
            parsed = parse_iso_date(row.get(key))
            if parsed is not None:
                dates.append(parsed)
    if dates:
        return min(dates), max(dates)
    start = parse_iso_date(fallback_start) or datetime.today().date()
    end = parse_iso_date(fallback_end) or start
    return start, end


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = _fieldnames(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})


def _fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "trade_date",
        "stock_code",
        "stock_name",
        "entry_date",
        "exit_date",
        "account_exit_date",
        "signal_type",
        "selected_order",
        "daily_candidate_rank",
        "rank_score",
        "entry_signal_score",
        "entry_price",
        "exit_price",
        "shares",
        "entry_value",
        "exit_value",
        "entry_cash_out",
        "exit_cash_in",
        "net_pnl",
        "return_pct",
        "source_return_pct",
        "exit_reason",
        "skip_reason",
        "cash",
        "market_value",
        "equity",
        "open_positions",
        "exposure_pct",
        "period",
        "start_date",
        "end_date",
        "start_equity",
        "end_equity",
    ]
    keys = {key for row in rows for key in row}
    return [key for key in preferred if key in keys] + sorted(keys - set(preferred))


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _default_output_dir(run_id: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ROOT_DIR / "data" / "backtests" / "diagnostics" / f"real_capital_{run_id}_{timestamp}"


if __name__ == "__main__":
    raise SystemExit(main())
