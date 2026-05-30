# -*- coding: utf-8 -*-
"""Run walk-forward, parameter sensitivity, and Monte Carlo robustness diagnostics."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
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
    from theme_picker.backtest.analysis.robustness import (
        MarketRegimeConfig,
        MarketRegimeOverrideConfig,
        RegimeProfileMap,
        RobustnessVariant,
        apply_market_regime_overrides,
        build_market_regime_series,
        compare_profile_variants,
        monte_carlo_equity_bootstrap,
        run_regime_aware_profile,
        run_parameter_sensitivity,
        run_walk_forward_windows,
        summarize_daily_rank_filters,
        summarize_profiles_by_market_regime,
        summarize_rank_score_bins,
        summarize_rank_filters_by_period_regime,
        summarize_selected_by_period_regime,
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
    from src.backtest.analysis.robustness import (  # type: ignore[no-redef]
        MarketRegimeConfig,
        MarketRegimeOverrideConfig,
        RegimeProfileMap,
        RobustnessVariant,
        apply_market_regime_overrides,
        build_market_regime_series,
        compare_profile_variants,
        monte_carlo_equity_bootstrap,
        run_regime_aware_profile,
        run_parameter_sensitivity,
        run_walk_forward_windows,
        summarize_daily_rank_filters,
        summarize_profiles_by_market_regime,
        summarize_rank_score_bins,
        summarize_rank_filters_by_period_regime,
        summarize_selected_by_period_regime,
    )
    from src.backtest.analysis.signal_ranking import (  # type: ignore[no-redef]
        LayeredRankingConfig,
        load_db_backtest_runs,
        normalize_trade_candidate,
        parse_iso_date,
        rank_trade_candidates,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run P3 robustness diagnostics for an imported backtest run")
    parser.add_argument("--db-run-id", required=True, help="Imported DuckDB backtest run_id")
    parser.add_argument("--database-path", help="DuckDB path. Defaults to DATABASE_PATH or data/stock_analysis.duckdb")
    parser.add_argument("--output-dir", help="Output directory")

    parser.add_argument(
        "--rank-mode",
        choices=("signal_score", "cohort_ev", "cohort_ev_walk_forward", "stock_quality", "stock_quality_walk_forward"),
        default="signal_score",
    )
    parser.add_argument("--max-per-day", type=int, default=3)
    parser.add_argument("--pullback-quota", type=int, default=2)
    parser.add_argument("--breakout-quota", type=int, default=1)
    parser.add_argument("--ranking-max-open-positions", type=int, default=8)
    parser.add_argument("--min-cohort-trades", type=int, default=8)
    parser.add_argument("--min-rank-score", type=float)
    parser.add_argument("--heat-score-cap", type=float)
    parser.add_argument("--max-heat-score", dest="legacy_max_heat_score", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--bull-min-rank-score", type=float, help="Override min rank score for bull_active.")
    parser.add_argument("--range-min-rank-score", type=float, help="Override min rank score for range_neutral.")
    parser.add_argument("--weak-min-rank-score", type=float, help="Override min rank score for weak_defensive.")
    parser.add_argument("--bear-min-rank-score", type=float, help="Override min rank score for bear_pause soft mode.")
    parser.add_argument("--unknown-min-rank-score", type=float, help="Override min rank score for unknown.")
    parser.add_argument(
        "--bull-heat-score",
        help="Override heat cap for bull_active. Use a number, none, or omit to inherit --heat-score-cap.",
    )
    parser.add_argument(
        "--range-heat-score",
        help="Override heat cap for range_neutral. Use a number, none, or omit to inherit --heat-score-cap.",
    )
    parser.add_argument(
        "--weak-heat-score",
        help="Override heat cap for weak_defensive. Use a number, none, or omit to inherit --heat-score-cap.",
    )
    parser.add_argument(
        "--unknown-heat-score",
        help="Override heat cap for unknown. Use a number, none, or omit to inherit --heat-score-cap.",
    )
    parser.add_argument(
        "--unknown-regime-action",
        choices=("trade", "pause"),
        default="trade",
        help="How regime-aware profile handles unknown data coverage. Default trade with unknown_max2.",
    )
    parser.add_argument(
        "--bear-regime-action",
        choices=("pause", "soft"),
        default="pause",
        help="How regime-aware profile handles bear_pause. Default pause; soft allows a max1 pullback-only profile.",
    )
    parser.add_argument(
        "--bear-heat-score",
        help="Override heat cap for bear_pause when --bear-regime-action=soft. Use a number, none, or omit to inherit --heat-score-cap.",
    )
    parser.add_argument(
        "--bear-position-size-pct",
        type=float,
        help="Position size for bear_pause soft mode. Defaults to half of --position-size-pct.",
    )
    parser.add_argument("--bull-position-size-pct", type=float, help="Position size for bull_active.")
    parser.add_argument("--range-position-size-pct", type=float, help="Position size for range_neutral.")
    parser.add_argument("--weak-position-size-pct", type=float, help="Position size for weak_defensive.")
    parser.add_argument("--unknown-position-size-pct", type=float, help="Position size for unknown.")
    parser.add_argument("--no-fill", action="store_true")

    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--position-size-pct", type=float, default=0.08)
    parser.add_argument("--account-max-positions", type=int, default=8)
    parser.add_argument("--lot-size", type=int, default=100)
    parser.add_argument("--commission-bps", type=float, default=10.0)
    parser.add_argument("--min-commission", type=float, default=5.0)
    parser.add_argument("--stamp-tax-bps", type=float, default=5.0)
    parser.add_argument("--transfer-fee-bps", type=float, default=0.1)
    parser.add_argument("--price-adjustment", choices=("raw", "qfq"), default="qfq")

    parser.add_argument("--walk-forward-period", choices=("year", "quarter", "month"), default="year")
    parser.add_argument("--rank-diagnostics-period", choices=("year", "quarter", "month"), default="month")
    parser.add_argument("--skip-walk-forward", action="store_true")
    parser.add_argument("--skip-sensitivity", action="store_true")
    parser.add_argument("--skip-monte-carlo", action="store_true")
    parser.add_argument("--sensitivity-position-size-pcts", default="0.05,0.08,0.10,0.125")
    parser.add_argument("--sensitivity-account-max-positions", default="4,6,8")
    parser.add_argument("--sensitivity-max-per-day", default="2,3,4")
    parser.add_argument("--sensitivity-min-rank-scores", default="")
    parser.add_argument("--monte-carlo-iterations", type=int, default=1000)
    parser.add_argument("--monte-carlo-block-size", type=int, default=5)
    parser.add_argument("--monte-carlo-seed", type=int, default=42)
    parser.add_argument("--skip-market-regime", action="store_true")
    parser.add_argument("--market-regime-lag-days", type=int, default=1)
    parser.add_argument("--market-regime-short-window", type=int, default=20)
    parser.add_argument("--market-regime-long-window", type=int, default=60)
    parser.add_argument("--market-regime-min-symbols", type=int, default=20)
    parser.add_argument(
        "--market-regime-risk-override",
        action="store_true",
        help="Enable optional bull/range risk downgrades based on regime metrics.",
    )
    parser.add_argument(
        "--risk-override-target-regime",
        choices=("risk_pause", "risk_defensive", "bear_pause", "weak_defensive", "range_neutral"),
        default="risk_pause",
        help="Target regime when risk override is triggered. Default risk_pause, which is paused.",
    )
    parser.add_argument("--risk-breadth-ma60-pct", type=float)
    parser.add_argument("--risk-fragile-return-60d-pct", type=float)
    parser.add_argument("--risk-fragile-breadth-ma60-pct", type=float)
    parser.add_argument("--risk-fragile-return-20d-pct", type=float)
    parser.add_argument("--risk-cooling-breadth-ma20-pct", type=float)
    parser.add_argument("--risk-cooling-return-20d-pct", type=float)
    parser.add_argument("--risk-euphoric-return-60d-pct", type=float)
    parser.add_argument("--risk-euphoric-breadth-ma60-pct", type=float)
    parser.add_argument("--risk-heat-score", help="Override heat cap for risk_defensive. Use a number or none.")
    parser.add_argument("--risk-min-rank-score", type=float, help="Override min rank score for risk_defensive.")
    parser.add_argument("--risk-position-size-pct", type=float, help="Position size for risk_defensive.")
    parser.add_argument("--skip-regime-aware", action="store_true")
    parser.add_argument(
        "--regime-heat-grid",
        default="",
        help=(
            "Optional regime heat grid, e.g. "
            "'bull=55,60,65,none;range=55,60;weak=50,52,55;bear=pause,55;unknown=50,52,pause'."
        ),
    )
    parser.add_argument(
        "--compare-max-per-day",
        action="append",
        default=[],
        type=int,
        help="Add a profile comparison variant by changing max_per_day and scaling pullback/breakout quotas. Can repeat.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir(args.db_run_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    loaded = load_db_backtest_runs([args.db_run_id], database_path=args.database_path, root_dir=ROOT_DIR)[0]
    ranking_config = LayeredRankingConfig(
        rank_mode=args.rank_mode,
        max_per_day=args.max_per_day,
        pullback_quota=args.pullback_quota,
        breakout_quota=args.breakout_quota,
        max_open_positions=args.ranking_max_open_positions,
        min_cohort_trades=args.min_cohort_trades,
        min_rank_score=args.min_rank_score,
        heat_score_cap=_resolve_heat_score_cap(args),
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
    start_date, end_date = _trade_date_range(normalized_trades, fallback_start=loaded.start_date, fallback_end=loaded.end_date)
    market_regime_config = _market_regime_config(args)
    price_start_date = start_date
    if not args.skip_market_regime:
        price_start_date = start_date - timedelta(days=max(90, market_regime_config.long_window * 3))
    stock_codes = sorted({str(row.get("stock_code") or "") for row in normalized_trades if row.get("stock_code")})
    price_series = load_price_series_from_duckdb(
        stock_codes,
        database_path=args.database_path,
        start_date=price_start_date,
        end_date=end_date,
        price_adjustment=args.price_adjustment,
    )
    trading_days = load_trading_days_from_duckdb(
        database_path=args.database_path,
        start_date=start_date,
        end_date=end_date,
    )

    ranked_rows = rank_trade_candidates(normalized_trades, run_name=loaded.run_name, config=ranking_config)
    baseline_result = simulate_real_capital_portfolio(
        ranked_rows,
        config=account_config,
        price_series=price_series,
        trading_days=trading_days,
        run_name=loaded.run_name,
    )
    baseline_summary = baseline_result["summary"]

    walk_forward_rows = [] if args.skip_walk_forward else run_walk_forward_windows(
        ranked_rows,
        account_config=account_config,
        price_series=price_series,
        trading_days=trading_days,
        period=args.walk_forward_period,
        run_name=loaded.run_name,
    )
    sensitivity_rows = [] if args.skip_sensitivity else run_parameter_sensitivity(
        normalized_trades,
        run_name=loaded.run_name,
        variants=_build_sensitivity_variants(args, ranking_config, account_config),
        price_series=price_series,
        trading_days=trading_days,
        baseline_summary=baseline_summary,
    )
    monte_carlo = {"summary": {}, "paths": []}
    if not args.skip_monte_carlo:
        monte_carlo = monte_carlo_equity_bootstrap(
            baseline_result["equity_curve"],
            initial_cash=account_config.initial_cash,
            iterations=args.monte_carlo_iterations,
            block_size=args.monte_carlo_block_size,
            seed=args.monte_carlo_seed,
        )
    profile_comparison = _build_profile_comparison(
        args,
        normalized_trades=normalized_trades,
        run_name=loaded.run_name,
        ranking_config=ranking_config,
        account_config=account_config,
        price_series=price_series,
        trading_days=trading_days,
    )
    market_regime = _build_market_regime_analysis(
        args,
        ranked_rows=ranked_rows,
        baseline_result=baseline_result,
        ranking_config=ranking_config,
        account_config=account_config,
        profile_comparison=profile_comparison,
        price_series=price_series,
        trading_days=trading_days,
    )
    regime_aware = _build_regime_aware_result(
        args,
        normalized_trades=normalized_trades,
        run_name=loaded.run_name,
        ranking_config=ranking_config,
        account_config=account_config,
        regime_by_date=market_regime["regime_by_date"],
        price_series=price_series,
        trading_days=trading_days,
    )
    regime_aware_selected_by_period = summarize_selected_by_period_regime(
        regime_aware["ranked_rows"],
        period=args.rank_diagnostics_period,
    )
    regime_aware_rank_filter_summary = summarize_rank_filters_by_period_regime(
        regime_aware["ranked_rows"],
        period=args.rank_diagnostics_period,
    )
    regime_aware_daily_rank_filter = summarize_daily_rank_filters(regime_aware["ranked_rows"])
    regime_aware_rank_score_bins = summarize_rank_score_bins(
        regime_aware["ranked_rows"],
        period=args.rank_diagnostics_period,
    )
    regime_heat_grid = _build_regime_heat_grid(
        args,
        normalized_trades=normalized_trades,
        run_name=loaded.run_name,
        ranking_config=ranking_config,
        account_config=account_config,
        regime_by_date=market_regime["regime_by_date"],
        price_series=price_series,
        trading_days=trading_days,
    )

    ranked_candidates_path = output_dir / "baseline_ranked_candidates.csv"
    baseline_summary_path = output_dir / "baseline_account_summary.json"
    walk_forward_path = output_dir / "walk_forward.csv"
    sensitivity_path = output_dir / "parameter_sensitivity.csv"
    monte_carlo_paths_path = output_dir / "monte_carlo_paths.csv"
    monte_carlo_summary_path = output_dir / "monte_carlo_summary.json"
    profile_comparison_path = output_dir / "profile_comparison.csv"
    profile_walk_forward_path = output_dir / "profile_walk_forward.csv"
    profile_monte_carlo_path = output_dir / "profile_monte_carlo.csv"
    profile_incremental_trades_path = output_dir / "profile_incremental_trades.csv"
    market_regime_daily_path = output_dir / "market_regime_daily.csv"
    market_regime_profile_summary_path = output_dir / "market_regime_profile_summary.csv"
    market_regime_trades_path = output_dir / "market_regime_trades.csv"
    regime_aware_candidates_path = output_dir / "regime_aware_candidates.csv"
    regime_aware_trades_path = output_dir / "regime_aware_trades.csv"
    regime_aware_equity_path = output_dir / "regime_aware_equity_curve.csv"
    regime_aware_yearly_path = output_dir / "regime_aware_yearly_returns.csv"
    regime_aware_summary_path = output_dir / "regime_aware_account_summary.json"
    regime_aware_monte_carlo_path = output_dir / "regime_aware_monte_carlo_summary.json"
    regime_aware_selected_period_path = output_dir / "regime_aware_selected_by_period_regime.csv"
    regime_aware_rank_filter_summary_path = output_dir / "regime_aware_rank_filter_summary.csv"
    regime_aware_daily_rank_filter_path = output_dir / "regime_aware_daily_rank_filter.csv"
    regime_aware_rank_score_bins_path = output_dir / "regime_aware_rank_score_bins.csv"
    regime_heat_grid_path = output_dir / "regime_heat_grid.csv"
    regime_heat_grid_by_regime_path = output_dir / "regime_heat_grid_by_regime.csv"
    robustness_summary_path = output_dir / "robustness_summary.json"

    _write_csv(ranked_candidates_path, ranked_rows)
    baseline_summary_path.write_text(dumps_json({"summary": baseline_summary, "diagnostics": baseline_result["diagnostics"]}), encoding="utf-8")
    _write_csv(walk_forward_path, walk_forward_rows)
    _write_csv(sensitivity_path, sensitivity_rows)
    _write_csv(monte_carlo_paths_path, monte_carlo["paths"])
    monte_carlo_summary_path.write_text(dumps_json(monte_carlo["summary"]), encoding="utf-8")
    _write_csv(profile_comparison_path, profile_comparison["summary_rows"])
    _write_csv(profile_walk_forward_path, profile_comparison["walk_forward_rows"])
    _write_csv(profile_monte_carlo_path, profile_comparison["monte_carlo_rows"])
    _write_csv(profile_incremental_trades_path, profile_comparison["incremental_trade_rows"])
    _write_csv(market_regime_daily_path, market_regime["daily_rows"])
    _write_csv(market_regime_profile_summary_path, market_regime["summary_rows"])
    _write_csv(market_regime_trades_path, market_regime["trade_rows"])
    _write_csv(regime_aware_candidates_path, regime_aware["ranked_rows"])
    _write_csv(regime_aware_trades_path, regime_aware["account_result"].get("trades") or [])
    _write_csv(regime_aware_equity_path, regime_aware["account_result"].get("equity_curve") or [])
    _write_csv(regime_aware_yearly_path, regime_aware["account_result"].get("yearly_returns") or [])
    _write_csv(regime_aware_selected_period_path, regime_aware_selected_by_period)
    _write_csv(regime_aware_rank_filter_summary_path, regime_aware_rank_filter_summary)
    _write_csv(regime_aware_daily_rank_filter_path, regime_aware_daily_rank_filter)
    _write_csv(regime_aware_rank_score_bins_path, regime_aware_rank_score_bins)
    _write_csv(regime_heat_grid_path, regime_heat_grid["summary_rows"])
    _write_csv(regime_heat_grid_by_regime_path, regime_heat_grid["by_regime_rows"])
    regime_aware_summary_path.write_text(
        dumps_json(
            {
                "profile_map": regime_aware["profile_map"],
                "summary": regime_aware["account_result"].get("summary") or {},
                "diagnostics": regime_aware["account_result"].get("diagnostics") or {},
                "monte_carlo": regime_aware["monte_carlo"],
            }
        ),
        encoding="utf-8",
    )
    regime_aware_monte_carlo_path.write_text(dumps_json(regime_aware["monte_carlo"]), encoding="utf-8")

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
            "start_date": price_start_date.isoformat(),
            "trade_start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "price_adjustment": args.price_adjustment,
            "symbols_requested": len(stock_codes),
            "symbols_with_prices": len(price_series),
            "trading_days": len(trading_days),
        },
        "baseline_summary": baseline_summary,
        "walk_forward": walk_forward_rows,
        "parameter_sensitivity": sensitivity_rows,
        "monte_carlo": monte_carlo["summary"],
        "profile_comparison": profile_comparison["summary_rows"],
        "market_regime_config": market_regime["config"],
        "market_regime_override_config": market_regime["override_config"],
        "market_regime_profile_summary": market_regime["summary_rows"],
        "regime_aware": {
            "config": {
                "bear_regime_action": args.bear_regime_action,
                "unknown_regime_action": args.unknown_regime_action,
                "regime_min_rank_scores": _regime_rank_floors_from_args(args, ranking_config),
                "regime_position_size_pcts": _regime_position_sizes_from_args(args, account_config),
            },
            "profile_map": regime_aware["profile_map"],
            "summary": regime_aware["account_result"].get("summary") or {},
            "monte_carlo": regime_aware["monte_carlo"],
            "selected_by_period_regime": regime_aware_selected_by_period,
            "rank_filter_summary": regime_aware_rank_filter_summary,
            "rank_score_bins": regime_aware_rank_score_bins,
        },
        "regime_heat_grid": regime_heat_grid["summary_rows"],
        "output_files": {
            "baseline_ranked_candidates": str(ranked_candidates_path),
            "baseline_account_summary": str(baseline_summary_path),
            "walk_forward": str(walk_forward_path),
            "parameter_sensitivity": str(sensitivity_path),
            "monte_carlo_paths": str(monte_carlo_paths_path),
            "monte_carlo_summary": str(monte_carlo_summary_path),
            "profile_comparison": str(profile_comparison_path),
            "profile_walk_forward": str(profile_walk_forward_path),
            "profile_monte_carlo": str(profile_monte_carlo_path),
            "profile_incremental_trades": str(profile_incremental_trades_path),
            "market_regime_daily": str(market_regime_daily_path),
            "market_regime_profile_summary": str(market_regime_profile_summary_path),
            "market_regime_trades": str(market_regime_trades_path),
            "regime_aware_candidates": str(regime_aware_candidates_path),
            "regime_aware_trades": str(regime_aware_trades_path),
            "regime_aware_equity_curve": str(regime_aware_equity_path),
            "regime_aware_yearly_returns": str(regime_aware_yearly_path),
            "regime_aware_account_summary": str(regime_aware_summary_path),
            "regime_aware_monte_carlo": str(regime_aware_monte_carlo_path),
            "regime_aware_selected_by_period_regime": str(regime_aware_selected_period_path),
            "regime_aware_rank_filter_summary": str(regime_aware_rank_filter_summary_path),
            "regime_aware_daily_rank_filter": str(regime_aware_daily_rank_filter_path),
            "regime_aware_rank_score_bins": str(regime_aware_rank_score_bins_path),
            "regime_heat_grid": str(regime_heat_grid_path),
            "regime_heat_grid_by_regime": str(regime_heat_grid_by_regime_path),
        },
    }
    robustness_summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("robustness baseline summary:")
    print(json.dumps(baseline_summary, ensure_ascii=False, indent=2))
    if monte_carlo["summary"]:
        print("monte carlo summary:")
        print(json.dumps(monte_carlo["summary"], ensure_ascii=False, indent=2))
    print(f"saved_robustness_summary={robustness_summary_path}")
    print(f"saved_walk_forward={walk_forward_path}")
    print(f"saved_parameter_sensitivity={sensitivity_path}")
    print(f"saved_monte_carlo_summary={monte_carlo_summary_path}")
    print(f"saved_profile_comparison={profile_comparison_path}")
    print(f"saved_market_regime_profile_summary={market_regime_profile_summary_path}")
    if regime_aware["account_result"].get("summary"):
        print("regime-aware summary:")
        print(json.dumps(regime_aware["account_result"]["summary"], ensure_ascii=False, indent=2))
    print(f"saved_regime_aware_candidates={regime_aware_candidates_path}")
    print(f"saved_regime_aware_account_summary={regime_aware_summary_path}")
    print(f"saved_regime_aware_selected_by_period_regime={regime_aware_selected_period_path}")
    print(f"saved_regime_aware_rank_filter_summary={regime_aware_rank_filter_summary_path}")
    print(f"saved_regime_aware_rank_score_bins={regime_aware_rank_score_bins_path}")
    if regime_heat_grid["summary_rows"]:
        print(f"saved_regime_heat_grid={regime_heat_grid_path}")
        print(f"saved_regime_heat_grid_by_regime={regime_heat_grid_by_regime_path}")
    return 0


def _build_market_regime_analysis(
    args: argparse.Namespace,
    *,
    ranked_rows: list[dict[str, Any]],
    baseline_result: dict[str, Any],
    ranking_config: LayeredRankingConfig,
    account_config: RealCapitalConfig,
    profile_comparison: dict[str, Any],
    price_series: dict[str, dict[date, float]],
    trading_days: list[date],
) -> dict[str, Any]:
    config = _market_regime_config(args)
    if args.skip_market_regime:
        return {
            "config": config.to_dict(),
            "override_config": _market_regime_override_config(args).to_dict(),
            "regime_by_date": {},
            "daily_rows": [],
            "summary_rows": [],
            "trade_rows": [],
        }

    regime_by_date = build_market_regime_series(price_series, trading_days, config=config)
    override_config = _market_regime_override_config(args)
    regime_by_date = apply_market_regime_overrides(regime_by_date, config=override_config)
    evaluations = profile_comparison.get("evaluations") or [
        {
            "variant": RobustnessVariant("baseline", ranking_config, account_config).to_dict(),
            "ranked_rows": ranked_rows,
            "account_result": baseline_result,
        }
    ]
    summary = summarize_profiles_by_market_regime(
        evaluations,
        regime_by_date=regime_by_date,
        price_series=price_series,
        trading_days=trading_days,
    )
    return {
        "config": config.to_dict(),
        "override_config": override_config.to_dict(),
        "regime_by_date": regime_by_date,
        "daily_rows": list(regime_by_date.values()),
        "summary_rows": summary["summary_rows"],
        "trade_rows": summary["trade_rows"],
    }


def _market_regime_config(args: argparse.Namespace) -> MarketRegimeConfig:
    return MarketRegimeConfig(
        short_window=args.market_regime_short_window,
        long_window=args.market_regime_long_window,
        lag_days=args.market_regime_lag_days,
        min_symbols=args.market_regime_min_symbols,
    ).normalized()


def _market_regime_override_config(args: argparse.Namespace) -> MarketRegimeOverrideConfig:
    return MarketRegimeOverrideConfig(
        enabled=args.market_regime_risk_override,
        target_regime=args.risk_override_target_regime,
        risk_breadth_ma60_pct=args.risk_breadth_ma60_pct,
        fragile_return_60d_pct=args.risk_fragile_return_60d_pct,
        fragile_breadth_ma60_pct=args.risk_fragile_breadth_ma60_pct,
        fragile_return_20d_pct=args.risk_fragile_return_20d_pct,
        cooling_breadth_ma20_pct=args.risk_cooling_breadth_ma20_pct,
        cooling_return_20d_pct=args.risk_cooling_return_20d_pct,
        euphoric_return_60d_pct=args.risk_euphoric_return_60d_pct,
        euphoric_breadth_ma60_pct=args.risk_euphoric_breadth_ma60_pct,
    ).normalized()


def _build_regime_aware_result(
    args: argparse.Namespace,
    *,
    normalized_trades: list[dict[str, Any]],
    run_name: str,
    ranking_config: LayeredRankingConfig,
    account_config: RealCapitalConfig,
    regime_by_date: dict[date, dict[str, Any]],
    price_series: dict[str, dict[date, float]],
    trading_days: list[date],
) -> dict[str, Any]:
    if args.skip_regime_aware or args.skip_market_regime or not regime_by_date:
        return {"profile_map": {}, "ranked_rows": [], "account_result": {}, "monte_carlo": {}}
    profile_map = _default_regime_profile_map(
        ranking_config,
        account_config,
        heat_caps=_regime_heat_caps_from_args(args, ranking_config),
        rank_floors=_regime_rank_floors_from_args(args, ranking_config),
        position_sizes=_regime_position_sizes_from_args(args, account_config),
        pause_unknown=args.unknown_regime_action == "pause",
        bear_action=args.bear_regime_action,
    )
    result = run_regime_aware_profile(
        normalized_trades,
        run_name=run_name,
        profile_map=profile_map,
        regime_by_date=regime_by_date,
        price_series=price_series,
        trading_days=trading_days,
    )
    result["monte_carlo"] = monte_carlo_equity_bootstrap(
        result["account_result"]["equity_curve"],
        initial_cash=account_config.initial_cash,
        iterations=args.monte_carlo_iterations,
        block_size=args.monte_carlo_block_size,
        seed=args.monte_carlo_seed,
    )["summary"]
    return result


def _default_regime_profile_map(
    ranking_config: LayeredRankingConfig,
    account_config: RealCapitalConfig,
    *,
    heat_caps: dict[str, float | None] | None = None,
    rank_floors: dict[str, float | None] | None = None,
    position_sizes: dict[str, float] | None = None,
    pause_unknown: bool = False,
    bear_action: str = "pause",
) -> RegimeProfileMap:
    heat_caps = {**_default_regime_heat_caps(ranking_config), **(heat_caps or {})}
    rank_floors = {**_default_regime_rank_floors(ranking_config), **(rank_floors or {})}
    position_sizes = {**_default_regime_position_sizes(account_config), **(position_sizes or {})}
    bull_pullback_quota, bull_breakout_quota = _scaled_signal_quotas(4, ranking_config)
    range_pullback_quota, range_breakout_quota = _scaled_signal_quotas(3, ranking_config)
    weak_pullback_quota, weak_breakout_quota = _scaled_signal_quotas(2, ranking_config)
    bull_account = replace(account_config, position_size_pct=position_sizes["bull_active"]).normalized()
    range_account = replace(account_config, position_size_pct=position_sizes["range_neutral"]).normalized()
    weak_account = replace(account_config, position_size_pct=position_sizes["weak_defensive"]).normalized()
    unknown_account = replace(account_config, position_size_pct=position_sizes["unknown"]).normalized()
    bear_ranking = replace(
        ranking_config,
        max_per_day=1,
        pullback_quota=1,
        breakout_quota=0,
        max_open_positions=1,
        min_rank_score=rank_floors.get("bear_pause"),
        heat_score_cap=heat_caps.get("bear_pause"),
        fill_unused_slots=False,
    ).normalized()
    risk_ranking = replace(
        ranking_config,
        max_per_day=1,
        pullback_quota=1,
        breakout_quota=0,
        min_rank_score=rank_floors.get("risk_defensive"),
        heat_score_cap=heat_caps.get("risk_defensive"),
        fill_unused_slots=False,
    ).normalized()
    bear_account = replace(
        account_config,
        position_size_pct=position_sizes["bear_pause"],
    ).normalized()
    risk_account = replace(
        account_config,
        position_size_pct=position_sizes["risk_defensive"],
    ).normalized()
    bull_ranking = replace(
        ranking_config,
        max_per_day=4,
        pullback_quota=bull_pullback_quota,
        breakout_quota=bull_breakout_quota,
        min_rank_score=rank_floors.get("bull_active"),
        heat_score_cap=heat_caps.get("bull_active"),
    ).normalized()
    range_ranking = replace(
        ranking_config,
        max_per_day=3,
        pullback_quota=range_pullback_quota,
        breakout_quota=range_breakout_quota,
        min_rank_score=rank_floors.get("range_neutral"),
        heat_score_cap=heat_caps.get("range_neutral"),
    ).normalized()
    weak_ranking = replace(
        ranking_config,
        max_per_day=2,
        pullback_quota=weak_pullback_quota,
        breakout_quota=weak_breakout_quota,
        min_rank_score=rank_floors.get("weak_defensive"),
        heat_score_cap=heat_caps.get("weak_defensive"),
    ).normalized()
    unknown_ranking = replace(
        ranking_config,
        max_per_day=2,
        pullback_quota=1,
        breakout_quota=1 if ranking_config.breakout_quota > 0 else 0,
        min_rank_score=rank_floors.get("unknown"),
        heat_score_cap=heat_caps.get("unknown"),
    ).normalized()
    paused_regimes = {"bear_pause", "risk_pause"}
    if pause_unknown:
        paused_regimes.add("unknown")
    regime_variants = {
            "bull_active": RobustnessVariant(
                "bull_active_max4_pullback3",
                bull_ranking,
                bull_account,
            ),
            "range_neutral": RobustnessVariant(
                "range_neutral_max3",
                range_ranking,
                range_account,
            ),
            "weak_defensive": RobustnessVariant(
                "weak_defensive_max2",
                weak_ranking,
                weak_account,
            ),
        "unknown": RobustnessVariant(
            "unknown_max2",
            unknown_ranking,
            unknown_account,
        ),
        "risk_defensive": RobustnessVariant(
            "risk_defensive_max1_pullback_only",
            risk_ranking,
            risk_account,
        ),
    }
    if bear_action == "soft":
        paused_regimes.discard("bear_pause")
        regime_variants["bear_pause"] = RobustnessVariant(
            "bear_soft_max1_pullback_only",
            bear_ranking,
            bear_account,
        )
    return RegimeProfileMap(
        default_variant=RobustnessVariant(
            "range_neutral_max3",
            range_ranking,
            range_account,
        ),
        regime_variants=regime_variants,
        paused_regimes=paused_regimes,
    )


def _build_regime_heat_grid(
    args: argparse.Namespace,
    *,
    normalized_trades: list[dict[str, Any]],
    run_name: str,
    ranking_config: LayeredRankingConfig,
    account_config: RealCapitalConfig,
    regime_by_date: dict[date, dict[str, Any]],
    price_series: dict[str, dict[date, float]],
    trading_days: list[date],
) -> dict[str, list[dict[str, Any]]]:
    if args.skip_regime_aware or args.skip_market_regime or not regime_by_date or not args.regime_heat_grid:
        return {"summary_rows": [], "by_regime_rows": []}

    grid = _parse_regime_heat_grid(
        args.regime_heat_grid,
        ranking_config=ranking_config,
        bear_regime_action=args.bear_regime_action,
        bear_heat_score=args.bear_heat_score,
    )
    rank_floors = _regime_rank_floors_from_args(args, ranking_config)
    position_sizes = _regime_position_sizes_from_args(args, account_config)
    summary_rows: list[dict[str, Any]] = []
    by_regime_rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for values in itertools.product(
        grid["bull_active"],
        grid["range_neutral"],
        grid["weak_defensive"],
        grid["bear_pause"],
        grid["unknown"],
    ):
        bull_heat, range_heat, weak_heat, bear_value, unknown_value = values
        pause_bear = bear_value == "pause"
        bear_heat = None if pause_bear else bear_value
        pause_unknown = unknown_value == "pause"
        unknown_heat = None if pause_unknown else unknown_value
        key = (bull_heat, range_heat, weak_heat, bear_value, unknown_value)
        if key in seen:
            continue
        seen.add(key)
        heat_caps = {
            "bull_active": bull_heat,
            "range_neutral": range_heat,
            "weak_defensive": weak_heat,
            "bear_pause": bear_heat,
            "unknown": unknown_heat,
        }
        variant_name = _regime_heat_grid_variant_name(
            heat_caps,
            pause_bear=pause_bear,
            pause_unknown=pause_unknown,
        )
        profile_map = _default_regime_profile_map(
            ranking_config,
            account_config,
            heat_caps=heat_caps,
            rank_floors=rank_floors,
            position_sizes=position_sizes,
            pause_unknown=pause_unknown,
            bear_action="pause" if pause_bear else "soft",
        )
        result = run_regime_aware_profile(
            normalized_trades,
            run_name=run_name,
            profile_map=profile_map,
            regime_by_date=regime_by_date,
            price_series=price_series,
            trading_days=trading_days,
        )
        summary = result["account_result"]["summary"]
        total_return = _optional_float_value(summary.get("total_return_pct"))
        max_drawdown = _optional_float_value(summary.get("max_drawdown_pct"))
        selected_rows = [row for row in result["ranked_rows"] if row.get("selected")]
        summary_rows.append(
            {
                "variant": variant_name,
                "bull_heat_score": _heat_label(bull_heat),
                "range_heat_score": _heat_label(range_heat),
                "weak_heat_score": _heat_label(weak_heat),
                "bull_min_rank_score": _score_label(rank_floors.get("bull_active")),
                "range_min_rank_score": _score_label(rank_floors.get("range_neutral")),
                "weak_min_rank_score": _score_label(rank_floors.get("weak_defensive")),
                "bear_min_rank_score": _score_label(rank_floors.get("bear_pause")),
                "unknown_min_rank_score": _score_label(rank_floors.get("unknown")),
                "bull_position_size_pct": position_sizes["bull_active"],
                "range_position_size_pct": position_sizes["range_neutral"],
                "weak_position_size_pct": position_sizes["weak_defensive"],
                "bear_position_size_pct": position_sizes["bear_pause"] if not pause_bear else None,
                "unknown_position_size_pct": position_sizes["unknown"],
                "bear_heat_score": "pause" if pause_bear else _heat_label(bear_heat),
                "bear_regime_action": "pause" if pause_bear else "soft",
                "unknown_heat_score": "pause" if pause_unknown else _heat_label(unknown_heat),
                "unknown_regime_action": "pause" if pause_unknown else "trade",
                **_account_summary_projection(summary),
                "return_to_drawdown": round(total_return / max_drawdown, 4)
                if total_return is not None and max_drawdown
                else None,
                **_trade_group_stats(selected_rows),
            }
        )
        by_regime_rows.extend(
            _regime_heat_grid_by_regime_rows(
                selected_rows,
                variant_name=variant_name,
                heat_caps=heat_caps,
                position_sizes=position_sizes,
                pause_bear=pause_bear,
                pause_unknown=pause_unknown,
            )
        )

    summary_rows.sort(
        key=lambda row: (
            -(_optional_float_value(row.get("total_return_pct")) or 0.0),
            _optional_float_value(row.get("max_drawdown_pct")) or 999.0,
        )
    )
    return {
        "summary_rows": summary_rows,
        "by_regime_rows": by_regime_rows,
    }


def _regime_heat_grid_by_regime_rows(
    selected_rows: list[dict[str, Any]],
    *,
    variant_name: str,
    heat_caps: dict[str, float | None],
    position_sizes: dict[str, float],
    pause_bear: bool,
    pause_unknown: bool,
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in selected_rows:
        regime = str(row.get("market_regime") or "unknown")
        groups.setdefault(regime, []).append(row)
    rows: list[dict[str, Any]] = []
    for regime in ("bull_active", "range_neutral", "weak_defensive", "risk_defensive", "bear_pause", "risk_pause", "unknown"):
        regime_rows = groups.get(regime, [])
        rows.append(
            {
                "variant": variant_name,
                "market_regime": regime,
                "bull_heat_score": _heat_label(heat_caps.get("bull_active")),
                "range_heat_score": _heat_label(heat_caps.get("range_neutral")),
                "weak_heat_score": _heat_label(heat_caps.get("weak_defensive")),
                "bear_heat_score": "pause" if pause_bear else _heat_label(heat_caps.get("bear_pause")),
                "bear_regime_action": "pause" if pause_bear else "soft",
                "bull_position_size_pct": position_sizes["bull_active"],
                "range_position_size_pct": position_sizes["range_neutral"],
                "weak_position_size_pct": position_sizes["weak_defensive"],
                "bear_position_size_pct": position_sizes["bear_pause"] if not pause_bear else None,
                "unknown_position_size_pct": position_sizes["unknown"],
                "unknown_heat_score": "pause" if pause_unknown else _heat_label(heat_caps.get("unknown")),
                "unknown_regime_action": "pause" if pause_unknown else "trade",
                **_trade_group_stats(regime_rows),
            }
        )
    return rows


def _default_regime_heat_caps(ranking_config: LayeredRankingConfig) -> dict[str, float | None]:
    return {
        "bull_active": ranking_config.heat_score_cap,
        "range_neutral": ranking_config.heat_score_cap,
        "weak_defensive": ranking_config.heat_score_cap,
        "risk_defensive": ranking_config.heat_score_cap,
        "bear_pause": ranking_config.heat_score_cap,
        "unknown": ranking_config.heat_score_cap,
    }


def _default_regime_rank_floors(ranking_config: LayeredRankingConfig) -> dict[str, float | None]:
    return {
        "bull_active": ranking_config.min_rank_score,
        "range_neutral": ranking_config.min_rank_score,
        "weak_defensive": ranking_config.min_rank_score,
        "risk_defensive": ranking_config.min_rank_score,
        "bear_pause": ranking_config.min_rank_score,
        "unknown": ranking_config.min_rank_score,
    }


def _regime_rank_floors_from_args(
    args: argparse.Namespace,
    ranking_config: LayeredRankingConfig,
) -> dict[str, float | None]:
    floors = _default_regime_rank_floors(ranking_config)
    for regime, attr in (
        ("bull_active", "bull_min_rank_score"),
        ("range_neutral", "range_min_rank_score"),
        ("weak_defensive", "weak_min_rank_score"),
        ("risk_defensive", "risk_min_rank_score"),
        ("bear_pause", "bear_min_rank_score"),
        ("unknown", "unknown_min_rank_score"),
    ):
        raw_value = getattr(args, attr, None)
        if raw_value is not None:
            floors[regime] = float(raw_value)
    return floors


def _default_regime_position_sizes(account_config: RealCapitalConfig) -> dict[str, float]:
    base_position_size = account_config.normalized().position_size_pct
    return {
        "bull_active": base_position_size,
        "range_neutral": base_position_size,
        "weak_defensive": base_position_size,
        "risk_defensive": round(base_position_size * 0.5, 6),
        "bear_pause": round(base_position_size * 0.5, 6),
        "unknown": base_position_size,
    }


def _regime_position_sizes_from_args(
    args: argparse.Namespace,
    account_config: RealCapitalConfig,
) -> dict[str, float]:
    sizes = _default_regime_position_sizes(account_config)
    for regime, attr in (
        ("bull_active", "bull_position_size_pct"),
        ("range_neutral", "range_position_size_pct"),
        ("weak_defensive", "weak_position_size_pct"),
        ("risk_defensive", "risk_position_size_pct"),
        ("bear_pause", "bear_position_size_pct"),
        ("unknown", "unknown_position_size_pct"),
    ):
        raw_value = getattr(args, attr, None)
        if raw_value is not None:
            sizes[regime] = float(raw_value)
    return sizes


def _regime_heat_caps_from_args(
    args: argparse.Namespace,
    ranking_config: LayeredRankingConfig,
) -> dict[str, float | None]:
    caps = _default_regime_heat_caps(ranking_config)
    for regime, attr in (
        ("bull_active", "bull_heat_score"),
        ("range_neutral", "range_heat_score"),
        ("weak_defensive", "weak_heat_score"),
        ("risk_defensive", "risk_heat_score"),
        ("bear_pause", "bear_heat_score"),
        ("unknown", "unknown_heat_score"),
    ):
        raw_value = getattr(args, attr, None)
        if raw_value is not None and str(raw_value).strip() != "":
            caps[regime] = _parse_heat_cap(raw_value)
    return caps


def _build_profile_comparison(
    args: argparse.Namespace,
    *,
    normalized_trades: list[dict[str, Any]],
    run_name: str,
    ranking_config: LayeredRankingConfig,
    account_config: RealCapitalConfig,
    price_series: dict[str, dict[date, float]],
    trading_days: list[date],
) -> dict[str, Any]:
    comparison_variants: list[RobustnessVariant] = []
    for max_per_day in args.compare_max_per_day:
        pullback_quota, breakout_quota = _scaled_signal_quotas(max_per_day, ranking_config)
        if (
            max_per_day == ranking_config.max_per_day
            and pullback_quota == ranking_config.pullback_quota
            and breakout_quota == ranking_config.breakout_quota
        ):
            continue
        comparison_variants.append(
            RobustnessVariant(
                name=f"candidate_max_per_day={max_per_day},pullback={pullback_quota},breakout={breakout_quota}",
                ranking_config=replace(
                    ranking_config,
                    max_per_day=max_per_day,
                    pullback_quota=pullback_quota,
                    breakout_quota=breakout_quota,
                ),
                account_config=account_config,
            )
        )
    if not comparison_variants:
        return {
            "summary_rows": [],
            "walk_forward_rows": [],
            "monte_carlo_rows": [],
            "incremental_trade_rows": [],
            "evaluations": [],
        }
    return compare_profile_variants(
        normalized_trades,
        run_name=run_name,
        baseline_variant=RobustnessVariant("baseline", ranking_config, account_config),
        comparison_variants=comparison_variants,
        price_series=price_series,
        trading_days=trading_days,
        period=args.walk_forward_period,
        monte_carlo_iterations=args.monte_carlo_iterations,
        monte_carlo_block_size=args.monte_carlo_block_size,
        monte_carlo_seed=args.monte_carlo_seed,
    )


def _build_sensitivity_variants(
    args: argparse.Namespace,
    base_ranking: LayeredRankingConfig,
    base_account: RealCapitalConfig,
) -> list[RobustnessVariant]:
    variants: list[RobustnessVariant] = [
        RobustnessVariant("baseline", base_ranking, base_account),
    ]
    seen = {"baseline"}

    def add(name: str, ranking: LayeredRankingConfig, account: RealCapitalConfig) -> None:
        if name in seen:
            return
        seen.add(name)
        variants.append(RobustnessVariant(name, ranking.normalized(), account.normalized()))

    for value in _parse_float_list(args.sensitivity_position_size_pcts):
        if abs(value - base_account.position_size_pct) < 1e-12:
            continue
        name = f"position_size_pct={value:g}"
        add(name, base_ranking, replace(base_account, position_size_pct=value))

    for value in _parse_int_list(args.sensitivity_account_max_positions):
        if value == base_account.max_positions:
            continue
        name = f"account_max_positions={value}"
        add(name, base_ranking, replace(base_account, max_positions=value))

    for value in _parse_int_list(args.sensitivity_max_per_day):
        pullback_quota, breakout_quota = _scaled_signal_quotas(value, base_ranking)
        if (
            value == base_ranking.max_per_day
            and pullback_quota == base_ranking.pullback_quota
            and breakout_quota == base_ranking.breakout_quota
        ):
            continue
        name = f"max_per_day={value},pullback={pullback_quota},breakout={breakout_quota}"
        add(
            name,
            replace(
                base_ranking,
                max_per_day=value,
                pullback_quota=pullback_quota,
                breakout_quota=breakout_quota,
            ),
            base_account,
        )

    for value in _parse_float_list(args.sensitivity_min_rank_scores):
        if base_ranking.min_rank_score is not None and abs(value - base_ranking.min_rank_score) < 1e-12:
            continue
        name = f"min_rank_score={value:g}"
        add(name, replace(base_ranking, min_rank_score=value), base_account)

    return variants


def _scaled_signal_quotas(max_per_day: int, base_ranking: LayeredRankingConfig) -> tuple[int, int]:
    max_per_day = max(1, int(max_per_day))
    if base_ranking.breakout_quota <= 0:
        return max_per_day, 0
    breakout_quota = 1 if max_per_day >= 2 else 0
    pullback_quota = max(0, max_per_day - breakout_quota)
    return pullback_quota, breakout_quota


def _parse_regime_heat_grid(
    raw: str,
    *,
    ranking_config: LayeredRankingConfig,
    bear_regime_action: str = "pause",
    bear_heat_score: str | None = None,
) -> dict[str, list[float | None | str]]:
    default_caps = _default_regime_heat_caps(ranking_config)
    default_bear_value: float | None | str = "pause"
    if bear_regime_action == "soft":
        default_bear_value = _parse_heat_cap(bear_heat_score) if bear_heat_score else default_caps["bear_pause"]
    grid: dict[str, list[float | None | str]] = {
        "bull_active": [default_caps["bull_active"]],
        "range_neutral": [default_caps["range_neutral"]],
        "weak_defensive": [default_caps["weak_defensive"]],
        "bear_pause": [default_bear_value],
        "unknown": [default_caps["unknown"]],
    }
    aliases = {
        "bull": "bull_active",
        "bull_active": "bull_active",
        "range": "range_neutral",
        "range_neutral": "range_neutral",
        "weak": "weak_defensive",
        "weak_defensive": "weak_defensive",
        "bear": "bear_pause",
        "bear_pause": "bear_pause",
        "unknown": "unknown",
    }
    for chunk in str(raw or "").split(";"):
        text = chunk.strip()
        if not text:
            continue
        if "=" not in text:
            raise ValueError(f"invalid regime heat grid segment: {text}")
        key, values_text = text.split("=", 1)
        regime = aliases.get(key.strip().lower())
        if regime is None:
            raise ValueError(f"unsupported regime in heat grid: {key}")
        values = [_parse_heat_grid_value(value, regime=regime) for value in values_text.split(",")]
        values = _dedupe_heat_values([value for value in values if value != ""])
        if not values:
            raise ValueError(f"empty heat grid values for {key}")
        grid[regime] = values
    return grid


def _parse_heat_grid_value(raw: str, *, regime: str) -> float | None | str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    if text in {"none", "null", "off", "no_cap", "nocap"}:
        return None
    if text == "pause":
        if regime not in {"unknown", "bear_pause"}:
            raise ValueError("pause is only supported for unknown or bear_pause regime heat grid")
        return "pause"
    return float(text)


def _resolve_heat_score_cap(args: argparse.Namespace) -> float | None:
    if args.heat_score_cap is not None:
        return float(args.heat_score_cap)
    if getattr(args, "legacy_max_heat_score", None) is not None:
        return float(args.legacy_max_heat_score)
    return None


def _parse_heat_cap(raw: str) -> float | None:
    value = _parse_heat_grid_value(raw, regime="range_neutral")
    if value == "pause":
        raise ValueError("use --unknown-regime-action pause instead of heat cap pause")
    if value == "":
        return None
    return value  # type: ignore[return-value]


def _dedupe_heat_values(values: list[float | None | str]) -> list[float | None | str]:
    seen: set[str] = set()
    result: list[float | None | str] = []
    for value in values:
        key = _heat_label(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _regime_heat_grid_variant_name(
    heat_caps: dict[str, float | None],
    *,
    pause_bear: bool,
    pause_unknown: bool,
) -> str:
    return ",".join(
        [
            f"bull={_heat_label(heat_caps.get('bull_active'))}",
            f"range={_heat_label(heat_caps.get('range_neutral'))}",
            f"weak={_heat_label(heat_caps.get('weak_defensive'))}",
            f"bear={'pause' if pause_bear else _heat_label(heat_caps.get('bear_pause'))}",
            f"unknown={'pause' if pause_unknown else _heat_label(heat_caps.get('unknown'))}",
        ]
    )


def _heat_label(value: float | None | str) -> str:
    if value is None:
        return "none"
    if isinstance(value, str):
        return value
    return f"{float(value):g}"


def _score_label(value: float | None) -> str:
    if value is None:
        return "none"
    return f"{float(value):g}"


def _account_summary_projection(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "initial_cash": summary.get("initial_cash"),
        "final_equity": summary.get("final_equity"),
        "total_return_pct": summary.get("total_return_pct"),
        "max_drawdown_pct": summary.get("max_drawdown_pct"),
        "selected_candidate_count": summary.get("selected_candidate_count"),
        "opened_trade_count": summary.get("opened_trade_count"),
        "closed_trade_count": summary.get("closed_trade_count"),
        "skipped_candidate_count": summary.get("skipped_candidate_count"),
        "max_consecutive_losses": summary.get("max_consecutive_losses"),
        "avg_exposure_pct": summary.get("avg_exposure_pct"),
        "max_exposure_pct": summary.get("max_exposure_pct"),
        "mark_price_fallback_count": summary.get("mark_price_fallback_count"),
        "mark_price_fallback_symbol_count": summary.get("mark_price_fallback_symbol_count"),
        "warnings": summary.get("warnings") or [],
    }


def _trade_group_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [_optional_float_value(row.get("return_pct")) or 0.0 for row in rows]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    gross_loss = abs(sum(losses))
    return {
        "selected_trade_count": len(rows),
        "pullback_count": len([row for row in rows if row.get("signal_type") == "pullback_bounce"]),
        "breakout_count": len([row for row in rows if row.get("signal_type") == "breakout_long"]),
        "win_rate_pct": round(len(wins) / len(rows) * 100.0, 4) if rows else 0.0,
        "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
        "sum_return_pct": round(sum(returns), 4),
        "profit_factor": round(sum(wins) / gross_loss, 4) if gross_loss else None,
        "avg_mae_pct": round(_average_present([_optional_float_value(row.get("max_adverse_excursion_pct")) for row in rows]), 4),
        "avg_holding_days": round(_average_present([_optional_float_value(row.get("holding_days")) for row in rows]), 4),
    }


def _optional_float_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _average_present(values: list[float | None]) -> float:
    present = [float(value) for value in values if value is not None]
    return sum(present) / len(present) if present else 0.0


def _parse_float_list(raw: str | None) -> list[float]:
    values: list[float] = []
    for part in str(raw or "").split(","):
        text = part.strip()
        if not text or text.lower() in {"none", "null"}:
            continue
        values.append(float(text))
    return values


def _parse_int_list(raw: str | None) -> list[int]:
    values: list[int] = []
    for part in str(raw or "").split(","):
        text = part.strip()
        if not text:
            continue
        values.append(int(text))
    return values


def _trade_date_range(
    rows: list[dict[str, Any]],
    *,
    fallback_start: str | None,
    fallback_end: str | None,
) -> tuple[date, date]:
    dates: list[date] = []
    for row in rows:
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
        "variant",
        "period",
        "entry_date",
        "window_start",
        "window_end",
        "rank_mode",
        "max_per_day",
        "pullback_quota",
        "breakout_quota",
        "ranking_max_open_positions",
        "min_rank_score",
        "heat_score_cap",
        "bull_heat_score",
        "range_heat_score",
        "weak_heat_score",
        "bull_min_rank_score",
        "range_min_rank_score",
        "weak_min_rank_score",
        "bear_min_rank_score",
        "unknown_min_rank_score",
        "bull_position_size_pct",
        "range_position_size_pct",
        "weak_position_size_pct",
        "bear_heat_score",
        "bear_regime_action",
        "bear_position_size_pct",
        "unknown_position_size_pct",
        "unknown_heat_score",
        "unknown_regime_action",
        "position_size_pct",
        "account_max_positions",
        "initial_cash",
        "final_equity",
        "total_return_pct",
        "max_drawdown_pct",
        "return_to_drawdown",
        "delta_return_pct",
        "delta_drawdown_pct",
        "mc_return_p05_pct",
        "mc_return_median_pct",
        "mc_loss_probability_pct",
        "mc_drawdown_p95_pct",
        "delta_mc_return_p05_pct",
        "delta_mc_loss_probability_pct",
        "delta_mc_drawdown_p95_pct",
        "selected_candidate_count",
        "opened_trade_count",
        "closed_trade_count",
        "skipped_candidate_count",
        "candidate_count",
        "eligible_count",
        "filtered_count",
        "selected_count",
        "passed_count",
        "filtered_above_heat_score_cap_count",
        "filtered_below_min_rank_score_count",
        "paused_regime_count",
        "win_rate_pct",
        "avg_return_pct",
        "sum_return_pct",
        "profit_factor",
        "max_consecutive_losses",
        "avg_exposure_pct",
        "max_exposure_pct",
        "mark_price_fallback_count",
        "mark_price_fallback_symbol_count",
        "warnings",
        "market_regime",
        "raw_market_regime",
        "market_regime_override_reason",
        "selected_profile",
        "rank_filter_reason",
        "signal_type",
        "asof_date",
        "regime_asof_date",
        "available_symbol_count",
        "regime_available_symbol_count",
        "breadth_ma20_pct",
        "breadth_ma60_pct",
        "avg_return_20d_pct",
        "avg_return_60d_pct",
        "avg_breadth_ma20_pct",
        "avg_breadth_ma60_pct",
        "avg_market_return_20d_pct",
        "avg_market_return_60d_pct",
        "source_avg_return_pct",
        "source_sum_return_pct",
        "selected_trade_count",
        "pullback_count",
        "breakout_count",
        "rank_score_bin",
        "scope",
        "avg_rank_score",
        "avg_heat_score",
        "avg_raw_daily_rank",
        "avg_eligible_daily_rank",
        "avg_signal_quality_trade_count",
        "avg_signal_quality_win_rate_pct",
        "avg_signal_quality_avg_return_pct",
        "avg_signal_quality_profit_factor",
        "avg_quality_signal_confidence",
        "avg_stock_quality_trade_count",
        "avg_stock_quality_win_rate_pct",
        "avg_stock_quality_avg_return_pct",
        "avg_stock_quality_profit_factor",
        "avg_quality_stock_confidence",
        "avg_stock_signal_quality_trade_count",
        "avg_stock_signal_quality_win_rate_pct",
        "avg_stock_signal_quality_avg_return_pct",
        "avg_stock_signal_quality_profit_factor",
        "avg_quality_stock_signal_confidence",
        "avg_quality_signal_score",
        "avg_quality_stock_score",
        "avg_quality_stock_signal_score",
        "avg_mfe_pct",
        "avg_mae_pct",
        "avg_holding_days",
        "selected_avg_return_pct",
        "selected_sum_return_pct",
        "filtered_avg_return_pct",
        "filtered_sum_return_pct",
        "iteration",
        "sampled_days",
        "min_equity",
        "change_type",
        "candidate_id",
        "trade_id",
        "exit_date",
        "stock_code",
        "stock_name",
        "signal_type",
        "selected",
        "selected_profile",
        "selected_layer",
        "entry_signal_score",
        "rank_score",
        "daily_candidate_rank",
        "selected_order",
        "return_pct",
        "exit_reason",
        "max_favorable_excursion_pct",
        "max_adverse_excursion_pct",
    ]
    keys = {key for row in rows for key in row}
    return [key for key in preferred if key in keys] + sorted(keys - set(preferred))


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _default_output_dir(run_id: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ROOT_DIR / "data" / "backtests" / "diagnostics" / f"robustness_{run_id}_{timestamp}"


if __name__ == "__main__":
    raise SystemExit(main())
