# -*- coding: utf-8 -*-
"""Robustness diagnostics for ranked real-capital backtests."""

from __future__ import annotations

import bisect
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from statistics import mean, median
from typing import Any

from theme_picker.backtest.analysis.real_capital import RealCapitalConfig, simulate_real_capital_portfolio
from theme_picker.backtest.analysis.signal_ranking import (
    LayeredRankingConfig,
    _base_rank_mode,
    _build_scorer,
    _is_walk_forward_rank_mode,
    _rank_filter_reason,
    _rank_filter_passes,
    _rank_sort_key,
    parse_iso_date,
    rank_trade_candidates,
    round_float,
    to_float,
)


@dataclass(slots=True)
class RobustnessVariant:
    name: str
    ranking_config: LayeredRankingConfig
    account_config: RealCapitalConfig

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ranking_config": self.ranking_config.normalized().to_dict(),
            "account_config": self.account_config.normalized().to_dict(),
        }


@dataclass(slots=True)
class MarketRegimeConfig:
    short_window: int = 20
    long_window: int = 60
    lag_days: int = 1
    min_symbols: int = 20
    bull_breadth_ma20_pct: float = 60.0
    bull_breadth_ma60_pct: float = 55.0
    bull_return_20d_pct: float = 2.0
    bull_return_60d_pct: float = 0.0
    bear_breadth_ma20_pct: float = 35.0
    bear_breadth_ma60_pct: float = 35.0
    bear_return_20d_pct: float = -3.0
    bear_return_60d_pct: float = -8.0
    weak_breadth_ma20_pct: float = 45.0
    weak_breadth_ma60_pct: float = 45.0
    weak_return_20d_pct: float = -2.0

    def normalized(self) -> "MarketRegimeConfig":
        short_window = max(2, int(self.short_window))
        long_window = max(short_window + 1, int(self.long_window))
        return MarketRegimeConfig(
            short_window=short_window,
            long_window=long_window,
            lag_days=max(0, int(self.lag_days)),
            min_symbols=max(1, int(self.min_symbols)),
            bull_breadth_ma20_pct=float(self.bull_breadth_ma20_pct),
            bull_breadth_ma60_pct=float(self.bull_breadth_ma60_pct),
            bull_return_20d_pct=float(self.bull_return_20d_pct),
            bull_return_60d_pct=float(self.bull_return_60d_pct),
            bear_breadth_ma20_pct=float(self.bear_breadth_ma20_pct),
            bear_breadth_ma60_pct=float(self.bear_breadth_ma60_pct),
            bear_return_20d_pct=float(self.bear_return_20d_pct),
            bear_return_60d_pct=float(self.bear_return_60d_pct),
            weak_breadth_ma20_pct=float(self.weak_breadth_ma20_pct),
            weak_breadth_ma60_pct=float(self.weak_breadth_ma60_pct),
            weak_return_20d_pct=float(self.weak_return_20d_pct),
        )

    def to_dict(self) -> dict[str, Any]:
        config = self.normalized()
        return {
            "short_window": config.short_window,
            "long_window": config.long_window,
            "lag_days": config.lag_days,
            "min_symbols": config.min_symbols,
            "bull_breadth_ma20_pct": config.bull_breadth_ma20_pct,
            "bull_breadth_ma60_pct": config.bull_breadth_ma60_pct,
            "bull_return_20d_pct": config.bull_return_20d_pct,
            "bull_return_60d_pct": config.bull_return_60d_pct,
            "bear_breadth_ma20_pct": config.bear_breadth_ma20_pct,
            "bear_breadth_ma60_pct": config.bear_breadth_ma60_pct,
            "bear_return_20d_pct": config.bear_return_20d_pct,
            "bear_return_60d_pct": config.bear_return_60d_pct,
            "weak_breadth_ma20_pct": config.weak_breadth_ma20_pct,
            "weak_breadth_ma60_pct": config.weak_breadth_ma60_pct,
            "weak_return_20d_pct": config.weak_return_20d_pct,
        }


@dataclass(slots=True)
class MarketRegimeOverrideConfig:
    enabled: bool = False
    target_regime: str = "risk_pause"
    risk_breadth_ma60_pct: float | None = None
    fragile_return_60d_pct: float | None = None
    fragile_breadth_ma60_pct: float | None = None
    fragile_return_20d_pct: float | None = None
    cooling_breadth_ma20_pct: float | None = None
    cooling_return_20d_pct: float | None = None
    euphoric_return_60d_pct: float | None = None
    euphoric_breadth_ma60_pct: float | None = None
    source_regimes: tuple[str, ...] = ("bull_active", "range_neutral")

    def normalized(self) -> "MarketRegimeOverrideConfig":
        return MarketRegimeOverrideConfig(
            enabled=bool(self.enabled),
            target_regime=str(self.target_regime or "risk_pause"),
            risk_breadth_ma60_pct=_optional_config_float(self.risk_breadth_ma60_pct),
            fragile_return_60d_pct=_optional_config_float(self.fragile_return_60d_pct),
            fragile_breadth_ma60_pct=_optional_config_float(self.fragile_breadth_ma60_pct),
            fragile_return_20d_pct=_optional_config_float(self.fragile_return_20d_pct),
            cooling_breadth_ma20_pct=_optional_config_float(self.cooling_breadth_ma20_pct),
            cooling_return_20d_pct=_optional_config_float(self.cooling_return_20d_pct),
            euphoric_return_60d_pct=_optional_config_float(self.euphoric_return_60d_pct),
            euphoric_breadth_ma60_pct=_optional_config_float(self.euphoric_breadth_ma60_pct),
            source_regimes=tuple(str(regime) for regime in self.source_regimes if str(regime)),
        )

    def to_dict(self) -> dict[str, Any]:
        config = self.normalized()
        return {
            "enabled": config.enabled,
            "target_regime": config.target_regime,
            "risk_breadth_ma60_pct": config.risk_breadth_ma60_pct,
            "fragile_return_60d_pct": config.fragile_return_60d_pct,
            "fragile_breadth_ma60_pct": config.fragile_breadth_ma60_pct,
            "fragile_return_20d_pct": config.fragile_return_20d_pct,
            "cooling_breadth_ma20_pct": config.cooling_breadth_ma20_pct,
            "cooling_return_20d_pct": config.cooling_return_20d_pct,
            "euphoric_return_60d_pct": config.euphoric_return_60d_pct,
            "euphoric_breadth_ma60_pct": config.euphoric_breadth_ma60_pct,
            "source_regimes": list(config.source_regimes),
        }


@dataclass(slots=True)
class RegimeProfileMap:
    default_variant: RobustnessVariant
    regime_variants: dict[str, RobustnessVariant]
    paused_regimes: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_variant": self.default_variant.to_dict(),
            "regime_variants": {
                regime: variant.to_dict()
                for regime, variant in sorted(self.regime_variants.items())
            },
            "paused_regimes": sorted(self.paused_regimes),
        }


def run_walk_forward_windows(
    ranked_rows: list[dict[str, Any]],
    *,
    account_config: RealCapitalConfig,
    price_series: dict[str, dict[date, float]],
    trading_days: list[date],
    period: str = "year",
    run_name: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate selected candidates by calendar window with capital reset per window."""

    selected_rows = [row for row in ranked_rows if row.get("selected") and parse_iso_date(row.get("entry_date"))]
    by_period: dict[str, list[dict[str, Any]]] = {}
    for row in selected_rows:
        entry_day = parse_iso_date(row.get("entry_date"))
        if entry_day is None:
            continue
        by_period.setdefault(_period_key(entry_day, period), []).append(row)

    rows: list[dict[str, Any]] = []
    for period_key in sorted(by_period):
        period_rows = by_period[period_key]
        result = simulate_real_capital_portfolio(
            period_rows,
            config=account_config,
            price_series=price_series,
            trading_days=trading_days,
            run_name=f"{run_name or 'walk_forward'}:{period_key}",
        )
        rows.append(
            {
                "period": period_key,
                "window_start": _min_date_str(period_rows, "entry_date"),
                "window_end": _max_date_str(period_rows, "exit_date"),
                **_summary_projection(result["summary"]),
            }
        )
    return rows


def run_parameter_sensitivity(
    normalized_trades: list[dict[str, Any]],
    *,
    run_name: str,
    variants: list[RobustnessVariant],
    price_series: dict[str, dict[date, float]],
    trading_days: list[date],
    baseline_summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run one-axis or grid variants through ranking and real-capital simulation."""

    rows: list[dict[str, Any]] = []
    baseline_return = to_float((baseline_summary or {}).get("total_return_pct"), default=None)
    baseline_drawdown = to_float((baseline_summary or {}).get("max_drawdown_pct"), default=None)

    for variant in variants:
        ranking_config = variant.ranking_config.normalized()
        account_config = variant.account_config.normalized()
        ranked_rows = rank_trade_candidates(normalized_trades, run_name=run_name, config=ranking_config)
        result = simulate_real_capital_portfolio(
            ranked_rows,
            config=account_config,
            price_series=price_series,
            trading_days=trading_days,
            run_name=f"{run_name}:{variant.name}",
        )
        summary = result["summary"]
        total_return = to_float(summary.get("total_return_pct"), default=0.0) or 0.0
        max_drawdown = to_float(summary.get("max_drawdown_pct"), default=0.0) or 0.0
        rows.append(
            {
                "variant": variant.name,
                "rank_mode": ranking_config.rank_mode,
                "max_per_day": ranking_config.max_per_day,
                "pullback_quota": ranking_config.pullback_quota,
                "breakout_quota": ranking_config.breakout_quota,
                "ranking_max_open_positions": ranking_config.max_open_positions,
                "min_rank_score": ranking_config.min_rank_score,
                "heat_score_cap": ranking_config.heat_score_cap,
                "fill_unused_slots": ranking_config.fill_unused_slots,
                "position_size_pct": account_config.position_size_pct,
                "account_max_positions": account_config.max_positions,
                **_summary_projection(summary),
                "return_to_drawdown": round_float(total_return / max_drawdown) if max_drawdown else None,
                "delta_return_pct": round_float(total_return - baseline_return) if baseline_return is not None else None,
                "delta_drawdown_pct": round_float(max_drawdown - baseline_drawdown) if baseline_drawdown is not None else None,
            }
        )
    return rows


def compare_profile_variants(
    normalized_trades: list[dict[str, Any]],
    *,
    run_name: str,
    baseline_variant: RobustnessVariant,
    comparison_variants: list[RobustnessVariant],
    price_series: dict[str, dict[date, float]],
    trading_days: list[date],
    period: str = "year",
    monte_carlo_iterations: int = 1000,
    monte_carlo_block_size: int = 5,
    monte_carlo_seed: int = 42,
) -> dict[str, Any]:
    """Compare named profiles on deterministic, walk-forward, and Monte Carlo axes."""

    variants = [baseline_variant, *comparison_variants]
    evaluations = [
        evaluate_robustness_variant(
            normalized_trades,
            run_name=run_name,
            variant=variant,
            price_series=price_series,
            trading_days=trading_days,
            period=period,
            monte_carlo_iterations=monte_carlo_iterations,
            monte_carlo_block_size=monte_carlo_block_size,
            monte_carlo_seed=monte_carlo_seed,
        )
        for variant in variants
    ]
    baseline = evaluations[0]
    baseline_summary = baseline["account_result"]["summary"]
    baseline_mc = baseline["monte_carlo"]["summary"]
    summary_rows = [
        _profile_summary_row(evaluation, baseline_summary=baseline_summary, baseline_mc=baseline_mc)
        for evaluation in evaluations
    ]
    walk_forward_rows = [
        {"variant": evaluation["variant"]["name"], **row}
        for evaluation in evaluations
        for row in evaluation["walk_forward"]
    ]
    monte_carlo_rows = [
        {"variant": evaluation["variant"]["name"], **evaluation["monte_carlo"]["summary"]}
        for evaluation in evaluations
    ]
    incremental_rows = [
        row
        for evaluation in evaluations[1:]
        for row in _incremental_trade_rows(
            baseline["ranked_rows"],
            evaluation["ranked_rows"],
            variant_name=evaluation["variant"]["name"],
        )
    ]
    return {
        "summary_rows": summary_rows,
        "walk_forward_rows": walk_forward_rows,
        "monte_carlo_rows": monte_carlo_rows,
        "incremental_trade_rows": incremental_rows,
        "evaluations": evaluations,
    }


def evaluate_robustness_variant(
    normalized_trades: list[dict[str, Any]],
    *,
    run_name: str,
    variant: RobustnessVariant,
    price_series: dict[str, dict[date, float]],
    trading_days: list[date],
    period: str = "year",
    monte_carlo_iterations: int = 1000,
    monte_carlo_block_size: int = 5,
    monte_carlo_seed: int = 42,
) -> dict[str, Any]:
    """Run one named profile through ranking, account simulation, windows, and MC."""

    ranked_rows = rank_trade_candidates(
        normalized_trades,
        run_name=run_name,
        config=variant.ranking_config.normalized(),
    )
    account_result = simulate_real_capital_portfolio(
        ranked_rows,
        config=variant.account_config.normalized(),
        price_series=price_series,
        trading_days=trading_days,
        run_name=f"{run_name}:{variant.name}",
    )
    walk_forward = run_walk_forward_windows(
        ranked_rows,
        account_config=variant.account_config.normalized(),
        price_series=price_series,
        trading_days=trading_days,
        period=period,
        run_name=f"{run_name}:{variant.name}",
    )
    monte_carlo = monte_carlo_equity_bootstrap(
        account_result["equity_curve"],
        initial_cash=variant.account_config.normalized().initial_cash,
        iterations=monte_carlo_iterations,
        block_size=monte_carlo_block_size,
        seed=monte_carlo_seed,
    )
    return {
        "variant": variant.to_dict(),
        "ranked_rows": ranked_rows,
        "account_result": account_result,
        "walk_forward": walk_forward,
        "monte_carlo": monte_carlo,
    }


def build_market_regime_series(
    price_series: dict[str, dict[date, float]],
    trading_days: list[date],
    *,
    config: MarketRegimeConfig | None = None,
) -> dict[date, dict[str, Any]]:
    """Build lagged market-regime labels from the local stock universe."""

    runtime_config = (config or MarketRegimeConfig()).normalized()
    sorted_days = sorted(set(trading_days))
    prepared_series = {
        stock_code: (sorted(prices), prices)
        for stock_code, prices in price_series.items()
        if prices
    }
    regimes: dict[date, dict[str, Any]] = {}
    for index, trade_day in enumerate(sorted_days):
        asof_index = index - runtime_config.lag_days
        asof_day = sorted_days[asof_index] if asof_index >= 0 else None
        metrics = _market_regime_metrics(prepared_series, asof_day=asof_day, config=runtime_config)
        regime = classify_market_regime(metrics, config=runtime_config)
        regimes[trade_day] = {
            "trade_date": trade_day.isoformat(),
            "asof_date": asof_day.isoformat() if asof_day else None,
            "market_regime": regime,
            **metrics,
        }
    return regimes


def apply_market_regime_overrides(
    regime_by_date: dict[date, dict[str, Any]],
    *,
    config: MarketRegimeOverrideConfig | None = None,
) -> dict[date, dict[str, Any]]:
    """Optionally downgrade fragile or euphoric bull/range labels for experiments."""

    runtime_config = (config or MarketRegimeOverrideConfig()).normalized()
    if not runtime_config.enabled:
        return regime_by_date

    result: dict[date, dict[str, Any]] = {}
    source_regimes = set(runtime_config.source_regimes)
    for trade_day, payload in regime_by_date.items():
        row = dict(payload)
        raw_regime = str(row.get("market_regime") or "unknown")
        row["raw_market_regime"] = raw_regime
        row["market_regime_override_reason"] = ""
        reason = _market_regime_override_reason(row, runtime_config, source_regimes=source_regimes)
        if reason:
            row["market_regime"] = runtime_config.target_regime
            row["market_regime_override_reason"] = reason
        result[trade_day] = row
    return result


def classify_market_regime(metrics: dict[str, Any], *, config: MarketRegimeConfig | None = None) -> str:
    runtime_config = (config or MarketRegimeConfig()).normalized()
    if int(metrics.get("available_symbol_count") or 0) < runtime_config.min_symbols:
        return "unknown"

    breadth_ma20 = to_float(metrics.get("breadth_ma20_pct"), default=0.0) or 0.0
    breadth_ma60 = to_float(metrics.get("breadth_ma60_pct"), default=0.0) or 0.0
    return_20d = to_float(metrics.get("avg_return_20d_pct"), default=0.0) or 0.0
    return_60d = to_float(metrics.get("avg_return_60d_pct"), default=0.0) or 0.0

    if (
        breadth_ma20 <= runtime_config.bear_breadth_ma20_pct
        and (
            breadth_ma60 <= runtime_config.bear_breadth_ma60_pct
            or return_20d <= runtime_config.bear_return_20d_pct
            or return_60d <= runtime_config.bear_return_60d_pct
        )
    ):
        return "bear_pause"
    if (
        breadth_ma20 >= runtime_config.bull_breadth_ma20_pct
        and breadth_ma60 >= runtime_config.bull_breadth_ma60_pct
        and return_20d >= runtime_config.bull_return_20d_pct
        and return_60d >= runtime_config.bull_return_60d_pct
    ):
        return "bull_active"
    if (
        breadth_ma20 <= runtime_config.weak_breadth_ma20_pct
        or breadth_ma60 <= runtime_config.weak_breadth_ma60_pct
        or return_20d <= runtime_config.weak_return_20d_pct
    ):
        return "weak_defensive"
    return "range_neutral"


def summarize_profiles_by_market_regime(
    evaluations: list[dict[str, Any]],
    *,
    regime_by_date: dict[date, dict[str, Any]],
    price_series: dict[str, dict[date, float]],
    trading_days: list[date],
) -> dict[str, Any]:
    """Summarize selected profile trades by entry-day market regime."""

    summary_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    for evaluation in evaluations:
        variant = evaluation["variant"]
        variant_name = str(variant["name"])
        account_config = RealCapitalConfig(**variant["account_config"]).normalized()
        selected_rows = [row for row in evaluation["ranked_rows"] if row.get("selected")]
        rows_by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for row in selected_rows:
            regime_payload = _regime_for_entry(row, regime_by_date)
            annotated = {
                "variant": variant_name,
                "market_regime": regime_payload.get("market_regime", "unknown"),
                "regime_asof_date": regime_payload.get("asof_date"),
                "regime_breadth_ma20_pct": regime_payload.get("breadth_ma20_pct"),
                "regime_breadth_ma60_pct": regime_payload.get("breadth_ma60_pct"),
                "regime_avg_return_20d_pct": regime_payload.get("avg_return_20d_pct"),
                "regime_avg_return_60d_pct": regime_payload.get("avg_return_60d_pct"),
                "regime_available_symbol_count": regime_payload.get("available_symbol_count"),
                **row,
            }
            trade_rows.append(annotated)
            rows_by_regime[str(annotated["market_regime"])].append(row)

        for regime_name in sorted(rows_by_regime):
            regime_rows = rows_by_regime[regime_name]
            account_result = simulate_real_capital_portfolio(
                regime_rows,
                config=account_config,
                price_series=price_series,
                trading_days=trading_days,
                run_name=f"{variant_name}:{regime_name}",
            )
            summary = account_result["summary"]
            metric_rows = [_regime_for_entry(row, regime_by_date) for row in regime_rows]
            summary_rows.append(
                {
                    "variant": variant_name,
                    "market_regime": regime_name,
                    "selected_trade_count": len(regime_rows),
                    "pullback_count": len([row for row in regime_rows if row.get("signal_type") == "pullback_bounce"]),
                    "breakout_count": len([row for row in regime_rows if row.get("signal_type") == "breakout_long"]),
                    "source_avg_return_pct": round_float(_average([to_float(row.get("return_pct"), default=None) for row in regime_rows])),
                    "source_sum_return_pct": round_float(sum(to_float(row.get("return_pct"), default=0.0) or 0.0 for row in regime_rows)),
                    "avg_breadth_ma20_pct": round_float(_average([to_float(row.get("breadth_ma20_pct"), default=None) for row in metric_rows])),
                    "avg_breadth_ma60_pct": round_float(_average([to_float(row.get("breadth_ma60_pct"), default=None) for row in metric_rows])),
                    "avg_market_return_20d_pct": round_float(_average([to_float(row.get("avg_return_20d_pct"), default=None) for row in metric_rows])),
                    "avg_market_return_60d_pct": round_float(_average([to_float(row.get("avg_return_60d_pct"), default=None) for row in metric_rows])),
                    **_summary_projection(summary),
                }
            )
    return {
        "summary_rows": summary_rows,
        "trade_rows": trade_rows,
    }


def rank_trade_candidates_by_market_regime(
    trades: list[dict[str, Any]],
    *,
    run_name: str,
    profile_map: RegimeProfileMap,
    regime_by_date: dict[date, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rank candidates with a different profile per entry-day market regime."""

    rows: list[dict[str, Any]] = []
    by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    scorer_cache: dict[tuple[str, int], Any] = {}

    for index, trade in enumerate(trades):
        row = dict(trade)
        row["candidate_id"] = f"{run_name}:{index + 1}"
        row["entry_day"] = parse_iso_date(row.get("entry_date"))
        row["exit_day"] = parse_iso_date(row.get("exit_date"))
        row["selected"] = False
        row["selected_order"] = None
        row["selected_layer"] = None
        row["daily_candidate_rank"] = None
        row["raw_daily_rank"] = None
        row["eligible_daily_rank"] = None
        row["daily_candidate_count"] = None
        row["eligible_candidate_count"] = None
        row["rank_filter_passed"] = False
        row["rank_filter_reason"] = None
        row["rank_mode"] = None
        row["rank_score"] = 0.0
        row["heat_score"] = None
        _annotate_regime(row, regime_by_date)
        row["selected_profile"] = _variant_for_regime(profile_map, str(row.get("market_regime") or "unknown")).name
        if row["entry_day"] is not None:
            by_date[row["entry_day"]].append(row)
            rows.append(row)

    open_rows: list[dict[str, Any]] = []
    selected_order = 0
    for entry_day in sorted(by_date):
        day_rows = by_date[entry_day]
        regime = str(day_rows[0].get("market_regime") or "unknown")
        variant = _variant_for_regime(profile_map, regime)
        ranking_config = variant.ranking_config.normalized()
        account_config = variant.account_config.normalized()
        if _is_walk_forward_rank_mode(ranking_config.rank_mode):
            closed_history = [
                row
                for row in rows
                if row.get("entry_day") is not None
                and row["entry_day"] < entry_day
                and row.get("exit_day") is not None
                and row["exit_day"] < entry_day
            ]
            scorer = _build_scorer(
                closed_history,
                rank_mode=_base_rank_mode(ranking_config.rank_mode),
                min_cohort_trades=ranking_config.min_cohort_trades,
            )
        else:
            scorer_key = (ranking_config.rank_mode, ranking_config.min_cohort_trades)
            scorer = scorer_cache.get(scorer_key)
            if scorer is None:
                scorer = _build_scorer(
                    rows,
                    rank_mode=ranking_config.rank_mode,
                    min_cohort_trades=ranking_config.min_cohort_trades,
                )
                scorer_cache[scorer_key] = scorer

        for row in day_rows:
            row["selected_profile"] = variant.name
            row["rank_mode"] = ranking_config.rank_mode
            row["rank_score"] = round(scorer(row), 6)
            row["position_size_pct"] = account_config.position_size_pct

        if regime in profile_map.paused_regimes:
            _mark_paused_day(day_rows, profile_name=f"paused:{regime}")
            continue

        all_day_candidates = sorted(day_rows, key=_rank_sort_key)
        candidates = [
            row
            for row in all_day_candidates
            if _rank_filter_passes(row, ranking_config)
        ]
        candidate_ids = {row["candidate_id"] for row in candidates}
        for daily_rank, row in enumerate(all_day_candidates, start=1):
            row["daily_candidate_rank"] = daily_rank
            row["raw_daily_rank"] = daily_rank
            row["daily_candidate_count"] = len(all_day_candidates)
            row["eligible_candidate_count"] = len(candidates)
            row["rank_filter_passed"] = row["candidate_id"] in candidate_ids
            row["rank_filter_reason"] = _rank_filter_reason(row, ranking_config) or "passed"
        for eligible_rank, row in enumerate(candidates, start=1):
            row["eligible_daily_rank"] = eligible_rank

        open_rows = [
            row for row in open_rows if row.get("exit_day") is not None and row["exit_day"] >= entry_day
        ]
        available_slots = ranking_config.max_per_day
        if ranking_config.max_open_positions > 0:
            available_slots = min(available_slots, max(0, ranking_config.max_open_positions - len(open_rows)))
        if available_slots <= 0:
            continue

        selected_today: list[dict[str, Any]] = []
        selected_ids: set[str] = set()
        for signal_type, quota in (
            ("pullback_bounce", ranking_config.pullback_quota),
            ("breakout_long", ranking_config.breakout_quota),
        ):
            if quota <= 0 or len(selected_today) >= available_slots:
                continue
            signal_candidates = [row for row in candidates if row.get("signal_type") == signal_type]
            for row in signal_candidates[:quota]:
                if row["candidate_id"] in selected_ids:
                    continue
                _select_regime_row(row, selected_today, selected_ids, selected_layer=f"quota:{signal_type}")
                if len(selected_today) >= available_slots:
                    break

        if ranking_config.fill_unused_slots and len(selected_today) < available_slots:
            for row in candidates:
                if row["candidate_id"] in selected_ids:
                    continue
                _select_regime_row(row, selected_today, selected_ids, selected_layer="fill")
                if len(selected_today) >= available_slots:
                    break

        for row in selected_today:
            selected_order += 1
            row["selected_order"] = selected_order
            if ranking_config.max_open_positions > 0:
                open_rows.append(row)

    return sorted(rows, key=lambda row: (str(row.get("entry_date")), int(row.get("daily_candidate_rank") or 0)))


def run_regime_aware_profile(
    normalized_trades: list[dict[str, Any]],
    *,
    run_name: str,
    profile_map: RegimeProfileMap,
    regime_by_date: dict[date, dict[str, Any]],
    price_series: dict[str, dict[date, float]],
    trading_days: list[date],
) -> dict[str, Any]:
    """Replay one account while switching entry profiles by market regime."""

    ranked_rows = rank_trade_candidates_by_market_regime(
        normalized_trades,
        run_name=run_name,
        profile_map=profile_map,
        regime_by_date=regime_by_date,
    )
    account_config = _merged_account_config(profile_map)
    account_result = simulate_real_capital_portfolio(
        ranked_rows,
        config=account_config,
        price_series=price_series,
        trading_days=trading_days,
        run_name=f"{run_name}:regime_aware",
    )
    return {
        "profile_map": profile_map.to_dict(),
        "ranked_rows": ranked_rows,
        "account_result": account_result,
    }


def summarize_selected_by_period_regime(
    candidate_rows: list[dict[str, Any]],
    *,
    period: str = "month",
) -> list[dict[str, Any]]:
    """Summarize selected candidates by period and market regime."""

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        if not row.get("selected"):
            continue
        period_key = _candidate_period_key(row, period)
        if period_key is None:
            continue
        groups[(period_key, str(row.get("market_regime") or "unknown"), str(row.get("selected_profile") or ""))].append(row)
    return [
        {
            "period": period_key,
            "market_regime": regime,
            "selected_profile": profile,
            **_candidate_group_stats(rows),
        }
        for (period_key, regime, profile), rows in sorted(groups.items())
    ]


def summarize_rank_filters_by_period_regime(
    candidate_rows: list[dict[str, Any]],
    *,
    period: str = "month",
) -> list[dict[str, Any]]:
    """Summarize all candidates by period, regime, filter reason, and signal type."""

    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        period_key = _candidate_period_key(row, period)
        if period_key is None:
            continue
        groups[
            (
                period_key,
                str(row.get("market_regime") or "unknown"),
                str(row.get("rank_filter_reason") or "unknown"),
                str(row.get("signal_type") or "unknown"),
            )
        ].append(row)
    return [
        {
            "period": period_key,
            "market_regime": regime,
            "rank_filter_reason": reason,
            "signal_type": signal_type,
            **_candidate_group_stats(rows),
        }
        for (period_key, regime, reason, signal_type), rows in sorted(groups.items())
    ]


def summarize_daily_rank_filters(candidate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize rank filtering per entry day and market regime."""

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        entry_date = str(row.get("entry_date") or "")
        if not entry_date:
            continue
        groups[
            (
                entry_date,
                str(row.get("market_regime") or "unknown"),
                str(row.get("selected_profile") or ""),
            )
        ].append(row)
    rows: list[dict[str, Any]] = []
    for (entry_date, regime, profile), group_rows in sorted(groups.items()):
        counts = _count_by(group_rows, "rank_filter_reason")
        rows.append(
            {
                "entry_date": entry_date,
                "market_regime": regime,
                "selected_profile": profile,
                "candidate_count": len(group_rows),
                "eligible_count": len([row for row in group_rows if row.get("rank_filter_passed")]),
                "selected_count": len([row for row in group_rows if row.get("selected")]),
                "filtered_count": len([row for row in group_rows if not row.get("rank_filter_passed")]),
                "filtered_above_heat_score_cap_count": counts.get("above_heat_score_cap", 0),
                "filtered_below_min_rank_score_count": counts.get("below_min_rank_score", 0),
                "paused_regime_count": counts.get("paused_regime", 0),
                "passed_count": counts.get("passed", 0),
                "selected_avg_return_pct": round_float(
                    _average([to_float(row.get("return_pct"), default=None) for row in group_rows if row.get("selected")])
                ),
                "selected_sum_return_pct": round_float(
                    sum(to_float(row.get("return_pct"), default=0.0) or 0.0 for row in group_rows if row.get("selected"))
                ),
                "filtered_avg_return_pct": round_float(
                    _average([to_float(row.get("return_pct"), default=None) for row in group_rows if not row.get("rank_filter_passed")])
                ),
                "filtered_sum_return_pct": round_float(
                    sum(to_float(row.get("return_pct"), default=0.0) or 0.0 for row in group_rows if not row.get("rank_filter_passed"))
                ),
            }
        )
    return rows


def summarize_rank_score_bins(
    candidate_rows: list[dict[str, Any]],
    *,
    period: str = "month",
) -> list[dict[str, Any]]:
    """Summarize candidate outcomes by rank-score decile for each regime and period."""

    bins = _rank_score_bin_labels()
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    dimensions: set[tuple[str, str]] = set()
    for row in candidate_rows:
        period_key = _candidate_period_key(row, period)
        if period_key is None:
            continue
        regime = str(row.get("market_regime") or "unknown")
        rank_bin = _rank_score_bin_label(to_float(row.get("rank_score"), default=None))
        for dimension in (
            (period_key, regime),
            (period_key, "ALL"),
            ("ALL", regime),
            ("ALL", "ALL"),
        ):
            dimensions.add(dimension)
            groups[(dimension[0], dimension[1], rank_bin)].append(row)

    rows: list[dict[str, Any]] = []
    scopes = (
        ("all_candidates", lambda values: values),
        ("eligible_candidates", lambda values: [row for row in values if row.get("rank_filter_passed")]),
        ("selected_candidates", lambda values: [row for row in values if row.get("selected")]),
        ("filtered_candidates", lambda values: [row for row in values if not row.get("rank_filter_passed")]),
    )
    for period_key, regime in sorted(dimensions):
        for rank_bin in bins:
            bin_rows = groups.get((period_key, regime, rank_bin), [])
            for scope, selector in scopes:
                scoped_rows = selector(bin_rows)
                rows.append(
                    {
                        "period": period_key,
                        "market_regime": regime,
                        "rank_score_bin": rank_bin,
                        "scope": scope,
                        **_candidate_group_stats(scoped_rows),
                    }
                )
    return rows


def monte_carlo_equity_bootstrap(
    equity_curve: list[dict[str, Any]],
    *,
    initial_cash: float,
    iterations: int = 1000,
    block_size: int = 5,
    seed: int = 42,
) -> dict[str, Any]:
    """Bootstrap account daily returns to stress final return and drawdown stability."""

    daily_returns = _daily_returns(equity_curve, initial_cash=initial_cash)
    iterations = max(1, int(iterations))
    block_size = max(1, int(block_size))
    rng = random.Random(seed)
    paths: list[dict[str, Any]] = []

    for index in range(iterations):
        sampled_returns = _sample_blocks(daily_returns, rng=rng, target_len=len(daily_returns), block_size=block_size)
        final_equity, max_drawdown_pct, min_equity = _compound_path(sampled_returns, initial_cash=initial_cash)
        paths.append(
            {
                "iteration": index + 1,
                "sampled_days": len(sampled_returns),
                "final_equity": round(final_equity, 2),
                "total_return_pct": round_float(_return_pct(initial_cash, final_equity)),
                "max_drawdown_pct": round_float(max_drawdown_pct),
                "min_equity": round(min_equity, 2),
            }
        )

    returns = [float(row["total_return_pct"]) for row in paths]
    drawdowns = [float(row["max_drawdown_pct"]) for row in paths]
    summary = {
        "iterations": iterations,
        "seed": seed,
        "block_size": block_size,
        "sampled_day_count": len(daily_returns),
        "return_mean_pct": round_float(mean(returns) if returns else 0.0),
        "return_median_pct": round_float(median(returns) if returns else 0.0),
        "return_p05_pct": round_float(_percentile(returns, 0.05)),
        "return_p25_pct": round_float(_percentile(returns, 0.25)),
        "return_p75_pct": round_float(_percentile(returns, 0.75)),
        "return_p95_pct": round_float(_percentile(returns, 0.95)),
        "loss_probability_pct": round_float(len([value for value in returns if value < 0]) / len(returns) * 100.0 if returns else 0.0),
        "drawdown_mean_pct": round_float(mean(drawdowns) if drawdowns else 0.0),
        "drawdown_p50_pct": round_float(_percentile(drawdowns, 0.50)),
        "drawdown_p95_pct": round_float(_percentile(drawdowns, 0.95)),
        "drawdown_p99_pct": round_float(_percentile(drawdowns, 0.99)),
    }
    return {"summary": summary, "paths": paths}


def robustness_score(row: dict[str, Any]) -> float | None:
    total_return = to_float(row.get("total_return_pct"), default=None)
    max_drawdown = to_float(row.get("max_drawdown_pct"), default=None)
    if total_return is None or max_drawdown is None or max_drawdown <= 0:
        return None
    return round_float(total_return / max_drawdown)


def _profile_summary_row(
    evaluation: dict[str, Any],
    *,
    baseline_summary: dict[str, Any],
    baseline_mc: dict[str, Any],
) -> dict[str, Any]:
    variant = evaluation["variant"]
    ranking_config = variant["ranking_config"]
    account_config = variant["account_config"]
    summary = evaluation["account_result"]["summary"]
    mc_summary = evaluation["monte_carlo"]["summary"]
    total_return = to_float(summary.get("total_return_pct"), default=0.0) or 0.0
    max_drawdown = to_float(summary.get("max_drawdown_pct"), default=0.0) or 0.0
    baseline_return = to_float(baseline_summary.get("total_return_pct"), default=0.0) or 0.0
    baseline_drawdown = to_float(baseline_summary.get("max_drawdown_pct"), default=0.0) or 0.0
    return {
        "variant": variant["name"],
        "rank_mode": ranking_config.get("rank_mode"),
        "max_per_day": ranking_config.get("max_per_day"),
        "pullback_quota": ranking_config.get("pullback_quota"),
        "breakout_quota": ranking_config.get("breakout_quota"),
        "ranking_max_open_positions": ranking_config.get("max_open_positions"),
        "min_rank_score": ranking_config.get("min_rank_score"),
        "heat_score_cap": ranking_config.get("heat_score_cap", ranking_config.get("max_heat_score")),
        "position_size_pct": account_config.get("position_size_pct"),
        "account_max_positions": account_config.get("max_positions"),
        **_summary_projection(summary),
        "return_to_drawdown": round_float(total_return / max_drawdown) if max_drawdown else None,
        "delta_return_pct": round_float(total_return - baseline_return),
        "delta_drawdown_pct": round_float(max_drawdown - baseline_drawdown),
        "mc_return_p05_pct": mc_summary.get("return_p05_pct"),
        "mc_return_median_pct": mc_summary.get("return_median_pct"),
        "mc_loss_probability_pct": mc_summary.get("loss_probability_pct"),
        "mc_drawdown_p95_pct": mc_summary.get("drawdown_p95_pct"),
        "delta_mc_return_p05_pct": _delta(mc_summary, baseline_mc, "return_p05_pct"),
        "delta_mc_loss_probability_pct": _delta(mc_summary, baseline_mc, "loss_probability_pct"),
        "delta_mc_drawdown_p95_pct": _delta(mc_summary, baseline_mc, "drawdown_p95_pct"),
    }


def _incremental_trade_rows(
    baseline_rows: list[dict[str, Any]],
    variant_rows: list[dict[str, Any]],
    *,
    variant_name: str,
) -> list[dict[str, Any]]:
    baseline_selected = {_selected_trade_key(row): row for row in baseline_rows if row.get("selected")}
    variant_selected = {_selected_trade_key(row): row for row in variant_rows if row.get("selected")}
    rows: list[dict[str, Any]] = []
    for change_type, source_keys, source_rows in (
        ("added", sorted(set(variant_selected) - set(baseline_selected)), variant_selected),
        ("removed", sorted(set(baseline_selected) - set(variant_selected)), baseline_selected),
    ):
        for key in source_keys:
            row = source_rows[key]
            rows.append(
                {
                    "variant": variant_name,
                    "change_type": change_type,
                    "candidate_id": row.get("candidate_id"),
                    "trade_id": row.get("trade_id"),
                    "stock_code": row.get("stock_code"),
                    "stock_name": row.get("stock_name"),
                    "entry_date": row.get("entry_date"),
                    "exit_date": row.get("exit_date"),
                    "signal_type": row.get("signal_type"),
                    "entry_signal_score": row.get("entry_signal_score"),
                    "rank_score": row.get("rank_score"),
                    "daily_candidate_rank": row.get("daily_candidate_rank"),
                    "selected_order": row.get("selected_order"),
                    "return_pct": row.get("return_pct"),
                    "exit_reason": row.get("exit_reason"),
                    "max_favorable_excursion_pct": row.get("max_favorable_excursion_pct"),
                    "max_adverse_excursion_pct": row.get("max_adverse_excursion_pct"),
                }
            )
    return rows


def _summary_projection(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "initial_cash": summary.get("initial_cash"),
        "final_equity": summary.get("final_equity"),
        "total_return_pct": summary.get("total_return_pct"),
        "max_drawdown_pct": summary.get("max_drawdown_pct"),
        "selected_candidate_count": summary.get("selected_candidate_count"),
        "opened_trade_count": summary.get("opened_trade_count"),
        "closed_trade_count": summary.get("closed_trade_count"),
        "skipped_candidate_count": summary.get("skipped_candidate_count"),
        "win_rate_pct": summary.get("win_rate_pct"),
        "avg_return_pct": summary.get("avg_return_pct"),
        "profit_factor": summary.get("profit_factor"),
        "max_consecutive_losses": summary.get("max_consecutive_losses"),
        "avg_exposure_pct": summary.get("avg_exposure_pct"),
        "max_exposure_pct": summary.get("max_exposure_pct"),
        "mark_price_fallback_count": summary.get("mark_price_fallback_count"),
        "mark_price_fallback_symbol_count": summary.get("mark_price_fallback_symbol_count"),
        "warnings": summary.get("warnings") or [],
    }


def _candidate_group_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [to_float(row.get("return_pct"), default=0.0) or 0.0 for row in rows]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    selected_rows = [row for row in rows if row.get("selected")]
    eligible_rows = [row for row in rows if row.get("rank_filter_passed")]
    filtered_rows = [row for row in rows if not row.get("rank_filter_passed")]
    return {
        "candidate_count": len(rows),
        "eligible_count": len(eligible_rows),
        "filtered_count": len(filtered_rows),
        "selected_count": len(selected_rows),
        "pullback_count": len([row for row in rows if row.get("signal_type") == "pullback_bounce"]),
        "breakout_count": len([row for row in rows if row.get("signal_type") == "breakout_long"]),
        "win_rate_pct": round_float(len(wins) / len(rows) * 100.0 if rows else 0.0),
        "avg_return_pct": round_float(sum(values) / len(values) if values else 0.0),
        "sum_return_pct": round_float(sum(values)),
        "profit_factor": round_float(sum(wins) / abs(sum(losses))) if losses else None,
        "avg_rank_score": round_float(_average([to_float(row.get("rank_score"), default=None) for row in rows])),
        "avg_heat_score": round_float(_average([to_float(row.get("heat_score"), default=None) for row in rows])),
        "avg_raw_daily_rank": round_float(_average([to_float(row.get("raw_daily_rank"), default=None) for row in rows])),
        "avg_eligible_daily_rank": round_float(_average([to_float(row.get("eligible_daily_rank"), default=None) for row in rows])),
        "avg_signal_quality_trade_count": round_float(
            _average([to_float(row.get("signal_quality_trade_count"), default=None) for row in rows])
        ),
        "avg_signal_quality_win_rate_pct": round_float(
            _average([to_float(row.get("signal_quality_win_rate_pct"), default=None) for row in rows])
        ),
        "avg_signal_quality_avg_return_pct": round_float(
            _average([to_float(row.get("signal_quality_avg_return_pct"), default=None) for row in rows])
        ),
        "avg_signal_quality_profit_factor": round_float(
            _average([to_float(row.get("signal_quality_profit_factor"), default=None) for row in rows])
        ),
        "avg_quality_signal_confidence": round_float(
            _average([to_float(row.get("quality_signal_confidence"), default=None) for row in rows])
        ),
        "avg_stock_quality_trade_count": round_float(
            _average([to_float(row.get("stock_quality_trade_count"), default=None) for row in rows])
        ),
        "avg_stock_quality_win_rate_pct": round_float(
            _average([to_float(row.get("stock_quality_win_rate_pct"), default=None) for row in rows])
        ),
        "avg_stock_quality_avg_return_pct": round_float(
            _average([to_float(row.get("stock_quality_avg_return_pct"), default=None) for row in rows])
        ),
        "avg_stock_quality_profit_factor": round_float(
            _average([to_float(row.get("stock_quality_profit_factor"), default=None) for row in rows])
        ),
        "avg_quality_stock_confidence": round_float(
            _average([to_float(row.get("quality_stock_confidence"), default=None) for row in rows])
        ),
        "avg_stock_signal_quality_trade_count": round_float(
            _average([to_float(row.get("stock_signal_quality_trade_count"), default=None) for row in rows])
        ),
        "avg_stock_signal_quality_win_rate_pct": round_float(
            _average([to_float(row.get("stock_signal_quality_win_rate_pct"), default=None) for row in rows])
        ),
        "avg_stock_signal_quality_avg_return_pct": round_float(
            _average([to_float(row.get("stock_signal_quality_avg_return_pct"), default=None) for row in rows])
        ),
        "avg_stock_signal_quality_profit_factor": round_float(
            _average([to_float(row.get("stock_signal_quality_profit_factor"), default=None) for row in rows])
        ),
        "avg_quality_stock_signal_confidence": round_float(
            _average([to_float(row.get("quality_stock_signal_confidence"), default=None) for row in rows])
        ),
        "avg_quality_signal_score": round_float(
            _average([to_float(row.get("quality_signal_score"), default=None) for row in rows])
        ),
        "avg_quality_stock_score": round_float(
            _average([to_float(row.get("quality_stock_score"), default=None) for row in rows])
        ),
        "avg_quality_stock_signal_score": round_float(
            _average([to_float(row.get("quality_stock_signal_score"), default=None) for row in rows])
        ),
        "avg_mfe_pct": round_float(
            _average([to_float(row.get("max_favorable_excursion_pct"), default=None) for row in rows])
        ),
        "avg_mae_pct": round_float(
            _average([to_float(row.get("max_adverse_excursion_pct"), default=None) for row in rows])
        ),
        "avg_holding_days": round_float(_average([to_float(row.get("holding_days"), default=None) for row in rows])),
    }


def _rank_score_bin_labels() -> list[str]:
    return [f"{lower:02d}-{lower + 10:02d}" for lower in range(0, 90, 10)] + ["90-100"]


def _rank_score_bin_label(score: float | None) -> str:
    if score is None:
        return "None"
    bounded = max(0.0, min(100.0, float(score)))
    if bounded >= 90.0:
        return "90-100"
    lower = int(bounded // 10) * 10
    return f"{lower:02d}-{lower + 10:02d}"


def _candidate_period_key(row: dict[str, Any], period: str) -> str | None:
    entry_day = parse_iso_date(row.get("entry_date"))
    if entry_day is None:
        return None
    return _period_key(entry_day, period)


def _period_key(day: date, period: str) -> str:
    normalized = str(period or "year").lower()
    if normalized == "month":
        return day.strftime("%Y-%m")
    if normalized == "quarter":
        return f"{day.year}-Q{((day.month - 1) // 3) + 1}"
    return day.strftime("%Y")


def _min_date_str(rows: list[dict[str, Any]], field: str) -> str | None:
    values = [day for day in (parse_iso_date(row.get(field)) for row in rows) if day is not None]
    return min(values).isoformat() if values else None


def _max_date_str(rows: list[dict[str, Any]], field: str) -> str | None:
    values = [day for day in (parse_iso_date(row.get(field)) for row in rows) if day is not None]
    return max(values).isoformat() if values else None


def _market_regime_metrics(
    prepared_series: dict[str, tuple[list[date], dict[date, float]]],
    *,
    asof_day: date | None,
    config: MarketRegimeConfig,
) -> dict[str, Any]:
    if asof_day is None:
        return {
            "available_symbol_count": 0,
            "breadth_ma20_pct": None,
            "breadth_ma60_pct": None,
            "avg_return_20d_pct": None,
            "avg_return_60d_pct": None,
        }
    ma20_above = 0
    ma60_above = 0
    return_20d_values: list[float] = []
    return_60d_values: list[float] = []
    available = 0
    required_count = config.long_window + 1

    for days, prices in prepared_series.values():
        closes = _last_closes(days, prices, asof_day=asof_day, count=required_count)
        if len(closes) < required_count:
            continue
        available += 1
        latest = closes[-1]
        ma20 = sum(closes[-config.short_window :]) / config.short_window
        ma60 = sum(closes[-config.long_window :]) / config.long_window
        ma20_above += 1 if latest > ma20 else 0
        ma60_above += 1 if latest > ma60 else 0
        return_20d_values.append(((latest / closes[-config.short_window - 1]) - 1.0) * 100.0)
        return_60d_values.append(((latest / closes[-config.long_window - 1]) - 1.0) * 100.0)

    return {
        "available_symbol_count": available,
        "breadth_ma20_pct": round_float(ma20_above / available * 100.0) if available else None,
        "breadth_ma60_pct": round_float(ma60_above / available * 100.0) if available else None,
        "avg_return_20d_pct": round_float(_average(return_20d_values)),
        "avg_return_60d_pct": round_float(_average(return_60d_values)),
    }


def _market_regime_override_reason(
    row: dict[str, Any],
    config: MarketRegimeOverrideConfig,
    *,
    source_regimes: set[str],
) -> str | None:
    regime = str(row.get("market_regime") or "unknown")
    if regime not in source_regimes:
        return None

    breadth_ma60 = to_float(row.get("breadth_ma60_pct"), default=None)
    breadth_ma20 = to_float(row.get("breadth_ma20_pct"), default=None)
    return_20d = to_float(row.get("avg_return_20d_pct"), default=None)
    return_60d = to_float(row.get("avg_return_60d_pct"), default=None)

    if (
        config.risk_breadth_ma60_pct is not None
        and breadth_ma60 is not None
        and breadth_ma60 <= config.risk_breadth_ma60_pct
    ):
        return "risk_breadth_ma60"
    if (
        config.fragile_return_60d_pct is not None
        and return_60d is not None
        and return_60d <= config.fragile_return_60d_pct
        and (
            config.fragile_breadth_ma60_pct is None
            or (breadth_ma60 is not None and breadth_ma60 <= config.fragile_breadth_ma60_pct)
        )
    ):
        return "fragile_return_60d"
    if (
        config.fragile_return_20d_pct is not None
        and return_20d is not None
        and return_20d <= config.fragile_return_20d_pct
    ):
        return "fragile_return_20d"
    if (
        config.cooling_breadth_ma20_pct is not None
        and config.cooling_return_20d_pct is not None
        and breadth_ma20 is not None
        and return_20d is not None
        and breadth_ma20 <= config.cooling_breadth_ma20_pct
        and return_20d <= config.cooling_return_20d_pct
    ):
        return "cooling_return_20d"
    if (
        config.euphoric_return_60d_pct is not None
        and config.euphoric_breadth_ma60_pct is not None
        and return_60d is not None
        and breadth_ma60 is not None
        and return_60d >= config.euphoric_return_60d_pct
        and breadth_ma60 >= config.euphoric_breadth_ma60_pct
    ):
        return "euphoric_return_60d"
    return None


def _optional_config_float(value: float | int | str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _last_closes(
    days: list[date],
    prices: dict[date, float],
    *,
    asof_day: date,
    count: int,
) -> list[float]:
    index = bisect.bisect_right(days, asof_day)
    if index <= 0:
        return []
    selected_days = days[max(0, index - count) : index]
    return [float(prices[day]) for day in selected_days if prices.get(day) is not None]


def _regime_for_entry(row: dict[str, Any], regime_by_date: dict[date, dict[str, Any]]) -> dict[str, Any]:
    entry_day = parse_iso_date(row.get("entry_date"))
    if entry_day is None:
        return {"market_regime": "unknown"}
    if entry_day in regime_by_date:
        return regime_by_date[entry_day]
    previous_days = [day for day in regime_by_date if day <= entry_day]
    if not previous_days:
        return {"market_regime": "unknown"}
    return regime_by_date[max(previous_days)]


def _annotate_regime(row: dict[str, Any], regime_by_date: dict[date, dict[str, Any]]) -> None:
    regime_payload = _regime_for_entry(row, regime_by_date)
    row["market_regime"] = regime_payload.get("market_regime", "unknown")
    row["raw_market_regime"] = regime_payload.get("raw_market_regime", row["market_regime"])
    row["market_regime_override_reason"] = regime_payload.get("market_regime_override_reason", "")
    row["regime_asof_date"] = regime_payload.get("asof_date")
    row["regime_breadth_ma20_pct"] = regime_payload.get("breadth_ma20_pct")
    row["regime_breadth_ma60_pct"] = regime_payload.get("breadth_ma60_pct")
    row["regime_avg_return_20d_pct"] = regime_payload.get("avg_return_20d_pct")
    row["regime_avg_return_60d_pct"] = regime_payload.get("avg_return_60d_pct")
    row["regime_available_symbol_count"] = regime_payload.get("available_symbol_count")


def _variant_for_regime(profile_map: RegimeProfileMap, regime: str) -> RobustnessVariant:
    return profile_map.regime_variants.get(regime) or profile_map.default_variant


def _mark_paused_day(rows: list[dict[str, Any]], *, profile_name: str) -> None:
    sorted_rows = sorted(rows, key=_rank_sort_key)
    for daily_rank, row in enumerate(sorted_rows, start=1):
        row["selected_profile"] = profile_name
        row["daily_candidate_rank"] = daily_rank
        row["raw_daily_rank"] = daily_rank
        row["daily_candidate_count"] = len(rows)
        row["eligible_daily_rank"] = None
        row["eligible_candidate_count"] = 0
        row["rank_filter_passed"] = False
        row["rank_filter_reason"] = "paused_regime"


def _select_regime_row(
    row: dict[str, Any],
    selected_today: list[dict[str, Any]],
    selected_ids: set[str],
    *,
    selected_layer: str,
) -> None:
    row["selected"] = True
    row["selected_layer"] = selected_layer
    selected_today.append(row)
    selected_ids.add(str(row["candidate_id"]))


def _merged_account_config(profile_map: RegimeProfileMap) -> RealCapitalConfig:
    variants = [profile_map.default_variant, *profile_map.regime_variants.values()]
    base = profile_map.default_variant.account_config.normalized()
    return RealCapitalConfig(
        initial_cash=base.initial_cash,
        position_size_pct=base.position_size_pct,
        max_positions=max(variant.account_config.normalized().max_positions for variant in variants),
        lot_size=base.lot_size,
        commission_bps=base.commission_bps,
        min_commission=base.min_commission,
        stamp_tax_bps=base.stamp_tax_bps,
        transfer_fee_bps=base.transfer_fee_bps,
        price_adjustment=base.price_adjustment,
    ).normalized()


def _average(values: list[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _selected_trade_key(row: dict[str, Any]) -> str:
    trade_id = row.get("trade_id")
    if trade_id:
        return str(trade_id)
    return "|".join(
        str(row.get(key) or "")
        for key in ("stock_code", "entry_date", "exit_date", "signal_type")
    )


def _delta(current: dict[str, Any], baseline: dict[str, Any], key: str) -> float | None:
    current_value = to_float(current.get(key), default=None)
    baseline_value = to_float(baseline.get(key), default=None)
    if current_value is None or baseline_value is None:
        return None
    return round_float(current_value - baseline_value)


def _daily_returns(equity_curve: list[dict[str, Any]], *, initial_cash: float) -> list[float]:
    returns: list[float] = []
    previous_equity = float(initial_cash)
    for point in equity_curve:
        equity = to_float(point.get("equity"), default=None)
        if equity is None or previous_equity <= 0:
            continue
        returns.append((float(equity) / previous_equity) - 1.0)
        previous_equity = float(equity)
    return returns


def _sample_blocks(
    returns: list[float],
    *,
    rng: random.Random,
    target_len: int,
    block_size: int,
) -> list[float]:
    if not returns or target_len <= 0:
        return []
    sampled: list[float] = []
    while len(sampled) < target_len:
        start = rng.randrange(len(returns))
        sampled.extend(returns[start : min(len(returns), start + block_size)])
    return sampled[:target_len]


def _compound_path(returns: list[float], *, initial_cash: float) -> tuple[float, float, float]:
    equity = float(initial_cash)
    peak = equity
    min_equity = equity
    max_drawdown_pct = 0.0
    for daily_return in returns:
        equity *= 1.0 + daily_return
        peak = max(peak, equity)
        min_equity = min(min_equity, equity)
        if peak > 0:
            max_drawdown_pct = max(max_drawdown_pct, (peak - equity) / peak * 100.0)
    return equity, max_drawdown_pct, min_equity


def _return_pct(initial_cash: float, final_equity: float) -> float:
    return ((final_equity - initial_cash) / initial_cash * 100.0) if initial_cash else 0.0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pct = max(0.0, min(1.0, float(pct)))
    position = (len(ordered) - 1) * pct
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return (ordered[lower] * (1.0 - weight)) + (ordered[upper] * weight)
