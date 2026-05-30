# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

from theme_picker.backtest.analysis.real_capital import RealCapitalConfig
from theme_picker.backtest.analysis.robustness import (
    MarketRegimeConfig,
    MarketRegimeOverrideConfig,
    RegimeProfileMap,
    RobustnessVariant,
    apply_market_regime_overrides,
    build_market_regime_series,
    classify_market_regime,
    compare_profile_variants,
    monte_carlo_equity_bootstrap,
    rank_trade_candidates_by_market_regime,
    run_regime_aware_profile,
    run_parameter_sensitivity,
    run_walk_forward_windows,
    summarize_profiles_by_market_regime,
    summarize_rank_score_bins,
)
from theme_picker.backtest.analysis.signal_ranking import LayeredRankingConfig, rank_trade_candidates


def _load_robustness_runner():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_backtest_robustness.py"
    spec = importlib.util.spec_from_file_location("run_backtest_robustness", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_DEFAULT_REGIME_PROFILE_MAP = _load_robustness_runner()._default_regime_profile_map


def _selected_trade(stock_code: str, entry_date: str, exit_date: str) -> dict:
    return {
        "selected": True,
        "stock_code": stock_code,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry_price": 10.0,
        "exit_price": 11.0,
        "signal_type": "pullback_bounce",
        "rank_score": 90.0,
        "selected_order": 1,
        "daily_candidate_rank": 1,
        "return_pct": 10.0,
    }


def _candidate_trade(stock_code: str, entry_date: str, exit_date: str, score: float) -> dict:
    return {
        "stock_code": stock_code,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry_price": 10.0,
        "exit_price": 11.0,
        "signal_type": "pullback_bounce",
        "entry_signal_score": score,
        "return_pct": 10.0,
        "holding_days": 2,
    }


def _no_cost_account(position_size_pct: float = 1.0) -> RealCapitalConfig:
    return RealCapitalConfig(
        initial_cash=10_000.0,
        position_size_pct=position_size_pct,
        max_positions=1,
        lot_size=100,
        commission_bps=0.0,
        min_commission=0.0,
        stamp_tax_bps=0.0,
        transfer_fee_bps=0.0,
    )


def test_walk_forward_windows_split_by_year_and_reset_capital() -> None:
    rows = run_walk_forward_windows(
        [
            _selected_trade("000001", "2024-01-02", "2024-01-04"),
            _selected_trade("000002", "2025-01-02", "2025-01-04"),
        ],
        account_config=_no_cost_account(),
        price_series={
            "000001": {date(2024, 1, 2): 10.0, date(2024, 1, 3): 10.5, date(2024, 1, 4): 11.0},
            "000002": {date(2025, 1, 2): 10.0, date(2025, 1, 3): 10.5, date(2025, 1, 4): 11.0},
        },
        trading_days=[
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
            date(2025, 1, 2),
            date(2025, 1, 3),
            date(2025, 1, 4),
        ],
        period="year",
    )

    assert [row["period"] for row in rows] == ["2024", "2025"]
    assert [row["total_return_pct"] for row in rows] == [10.0, 10.0]
    assert [row["closed_trade_count"] for row in rows] == [1, 1]


def test_parameter_sensitivity_runs_named_variants() -> None:
    trades = [
        _candidate_trade("000001", "2024-01-02", "2024-01-04", 90.0),
        _candidate_trade("000002", "2024-01-03", "2024-01-05", 80.0),
    ]
    rows = run_parameter_sensitivity(
        trades,
        run_name="pytest",
        variants=[
            RobustnessVariant(
                "baseline",
                LayeredRankingConfig(max_per_day=1, pullback_quota=1, breakout_quota=0, max_open_positions=1),
                _no_cost_account(position_size_pct=1.0),
            ),
            RobustnessVariant(
                "half_size",
                LayeredRankingConfig(max_per_day=1, pullback_quota=1, breakout_quota=0, max_open_positions=1),
                _no_cost_account(position_size_pct=0.5),
            ),
        ],
        price_series={
            "000001": {date(2024, 1, 2): 10.0, date(2024, 1, 3): 10.5, date(2024, 1, 4): 11.0},
            "000002": {date(2024, 1, 3): 10.0, date(2024, 1, 4): 10.5, date(2024, 1, 5): 11.0},
        },
        trading_days=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)],
    )

    assert [row["variant"] for row in rows] == ["baseline", "half_size"]
    assert rows[0]["opened_trade_count"] == 1
    assert rows[1]["opened_trade_count"] == 1
    assert rows[0]["total_return_pct"] > rows[1]["total_return_pct"]


def test_monte_carlo_equity_bootstrap_single_return_path() -> None:
    result = monte_carlo_equity_bootstrap(
        [{"trade_date": "2024-01-02", "equity": 110.0}],
        initial_cash=100.0,
        iterations=3,
        block_size=1,
        seed=7,
    )

    assert result["summary"]["iterations"] == 3
    assert result["summary"]["return_p05_pct"] == 10.0
    assert result["summary"]["loss_probability_pct"] == 0.0
    assert len(result["paths"]) == 3


def test_compare_profile_variants_reports_incremental_trades() -> None:
    trades = [
        _candidate_trade("000001", "2024-01-02", "2024-01-04", 90.0),
        _candidate_trade("000002", "2024-01-02", "2024-01-04", 80.0),
    ]
    result = compare_profile_variants(
        trades,
        run_name="pytest",
        baseline_variant=RobustnessVariant(
            "baseline",
            LayeredRankingConfig(max_per_day=1, pullback_quota=1, breakout_quota=0, max_open_positions=1),
            _no_cost_account(position_size_pct=0.5),
        ),
        comparison_variants=[
            RobustnessVariant(
                "candidate_max2",
                LayeredRankingConfig(max_per_day=2, pullback_quota=2, breakout_quota=0, max_open_positions=2),
                RealCapitalConfig(
                    initial_cash=10_000.0,
                    position_size_pct=0.5,
                    max_positions=2,
                    lot_size=100,
                    commission_bps=0.0,
                    min_commission=0.0,
                    stamp_tax_bps=0.0,
                    transfer_fee_bps=0.0,
                ),
            ),
        ],
        price_series={
            "000001": {date(2024, 1, 2): 10.0, date(2024, 1, 3): 10.5, date(2024, 1, 4): 11.0},
            "000002": {date(2024, 1, 2): 10.0, date(2024, 1, 3): 10.5, date(2024, 1, 4): 11.0},
        },
        trading_days=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        monte_carlo_iterations=3,
        monte_carlo_block_size=1,
    )

    assert [row["variant"] for row in result["summary_rows"]] == ["baseline", "candidate_max2"]
    assert result["summary_rows"][1]["delta_return_pct"] > 0
    assert result["walk_forward_rows"][1]["variant"] == "candidate_max2"
    assert result["monte_carlo_rows"][1]["variant"] == "candidate_max2"
    assert result["incremental_trade_rows"] == [
        {
            "variant": "candidate_max2",
            "change_type": "added",
            "candidate_id": "pytest:2",
            "trade_id": None,
            "stock_code": "000002",
            "stock_name": None,
            "entry_date": "2024-01-02",
            "exit_date": "2024-01-04",
            "signal_type": "pullback_bounce",
            "entry_signal_score": 80.0,
            "rank_score": 80.0,
            "daily_candidate_rank": 2,
            "selected_order": 2,
            "return_pct": 10.0,
            "exit_reason": None,
            "max_favorable_excursion_pct": None,
            "max_adverse_excursion_pct": None,
        }
    ]


def test_build_market_regime_series_uses_lagged_universe_metrics() -> None:
    trading_days = [date(2024, 1, day) for day in range(1, 7)]
    regimes = build_market_regime_series(
        {
            "000001": {day: float(index + 1) for index, day in enumerate(trading_days)},
            "000002": {day: float(index + 2) for index, day in enumerate(trading_days)},
        },
        trading_days,
        config=MarketRegimeConfig(
            short_window=2,
            long_window=3,
            lag_days=1,
            min_symbols=1,
            bull_return_20d_pct=1.0,
            bull_return_60d_pct=1.0,
        ),
    )

    assert regimes[date(2024, 1, 5)]["asof_date"] == "2024-01-04"
    assert regimes[date(2024, 1, 5)]["market_regime"] == "bull_active"
    assert regimes[date(2024, 1, 5)]["available_symbol_count"] == 2


def test_classify_market_regime_prioritizes_risk_before_weakness() -> None:
    assert classify_market_regime(
        {
            "available_symbol_count": 100,
            "breadth_ma20_pct": 34.0,
            "breadth_ma60_pct": 44.0,
            "avg_return_20d_pct": -3.5,
            "avg_return_60d_pct": -4.0,
        }
    ) == "bear_pause"


def test_classify_market_regime_checks_bull_before_weak_for_custom_thresholds() -> None:
    regime = classify_market_regime(
        {
            "available_symbol_count": 100,
            "breadth_ma20_pct": 65.0,
            "breadth_ma60_pct": 56.0,
            "avg_return_20d_pct": 3.0,
            "avg_return_60d_pct": 1.0,
        },
        config=MarketRegimeConfig(weak_breadth_ma60_pct=60.0),
    )

    assert regime == "bull_active"


def test_apply_market_regime_overrides_keeps_default_series_unchanged() -> None:
    regimes = {
        date(2024, 1, 2): {
            "market_regime": "bull_active",
            "avg_return_60d_pct": 1.0,
        }
    }

    assert apply_market_regime_overrides(regimes) is regimes


def test_apply_market_regime_overrides_downgrades_fragile_and_euphoric_bull_range() -> None:
    regimes = apply_market_regime_overrides(
        {
            date(2024, 1, 2): {
                "market_regime": "bull_active",
                "avg_return_20d_pct": 8.0,
                "avg_return_60d_pct": 4.0,
                "breadth_ma60_pct": 80.0,
            },
            date(2024, 1, 3): {
                "market_regime": "range_neutral",
                "avg_return_20d_pct": 9.0,
                "avg_return_60d_pct": 42.0,
                "breadth_ma60_pct": 96.0,
            },
            date(2024, 1, 4): {
                "market_regime": "weak_defensive",
                "avg_return_20d_pct": -3.0,
                "avg_return_60d_pct": -1.0,
                "breadth_ma60_pct": 40.0,
            },
        },
        config=MarketRegimeOverrideConfig(
            enabled=True,
            fragile_return_60d_pct=6.0,
            euphoric_return_60d_pct=35.0,
            euphoric_breadth_ma60_pct=95.0,
        ),
    )

    assert regimes[date(2024, 1, 2)]["market_regime"] == "risk_pause"
    assert regimes[date(2024, 1, 2)]["raw_market_regime"] == "bull_active"
    assert regimes[date(2024, 1, 2)]["market_regime_override_reason"] == "fragile_return_60d"
    assert regimes[date(2024, 1, 3)]["market_regime"] == "risk_pause"
    assert regimes[date(2024, 1, 3)]["market_regime_override_reason"] == "euphoric_return_60d"
    assert regimes[date(2024, 1, 4)]["market_regime"] == "weak_defensive"
    assert regimes[date(2024, 1, 4)]["market_regime_override_reason"] == ""


def test_apply_market_regime_overrides_supports_mvp_combo_guards() -> None:
    regimes = apply_market_regime_overrides(
        {
            date(2024, 1, 2): {
                "market_regime": "bull_active",
                "breadth_ma20_pct": 70.0,
                "breadth_ma60_pct": 58.0,
                "avg_return_20d_pct": 8.0,
                "avg_return_60d_pct": 12.0,
            },
            date(2024, 1, 3): {
                "market_regime": "range_neutral",
                "breadth_ma20_pct": 70.0,
                "breadth_ma60_pct": 68.0,
                "avg_return_20d_pct": 8.0,
                "avg_return_60d_pct": 5.0,
            },
            date(2024, 1, 4): {
                "market_regime": "bull_active",
                "breadth_ma20_pct": 54.0,
                "breadth_ma60_pct": 90.0,
                "avg_return_20d_pct": 5.0,
                "avg_return_60d_pct": 30.0,
            },
            date(2024, 1, 5): {
                "market_regime": "bull_active",
                "breadth_ma20_pct": 73.0,
                "breadth_ma60_pct": 71.0,
                "avg_return_20d_pct": 3.0,
                "avg_return_60d_pct": -1.0,
            },
        },
        config=MarketRegimeOverrideConfig(
            enabled=True,
            target_regime="weak_defensive",
            risk_breadth_ma60_pct=60.0,
            fragile_return_60d_pct=6.0,
            fragile_breadth_ma60_pct=70.0,
            cooling_breadth_ma20_pct=55.0,
            cooling_return_20d_pct=6.0,
        ),
    )

    assert regimes[date(2024, 1, 2)]["market_regime_override_reason"] == "risk_breadth_ma60"
    assert regimes[date(2024, 1, 3)]["market_regime_override_reason"] == "fragile_return_60d"
    assert regimes[date(2024, 1, 4)]["market_regime_override_reason"] == "cooling_return_20d"
    assert regimes[date(2024, 1, 5)]["market_regime"] == "bull_active"


def test_summarize_profiles_by_market_regime_groups_selected_trades() -> None:
    ranked_rows = [
        {
            **_selected_trade("000001", "2024-01-02", "2024-01-04"),
            "candidate_id": "pytest:1",
            "selected": True,
        },
        {
            **_selected_trade("000002", "2024-01-03", "2024-01-04"),
            "candidate_id": "pytest:2",
            "selected": True,
        },
    ]
    result = summarize_profiles_by_market_regime(
        [
            {
                "variant": RobustnessVariant(
                    "baseline",
                    LayeredRankingConfig(max_per_day=2, pullback_quota=2, breakout_quota=0),
                    _no_cost_account(position_size_pct=0.5),
                ).to_dict(),
                "ranked_rows": ranked_rows,
            }
        ],
        regime_by_date={
            date(2024, 1, 2): {
                "market_regime": "bull_active",
                "asof_date": "2024-01-01",
                "breadth_ma20_pct": 80.0,
                "breadth_ma60_pct": 70.0,
                "avg_return_20d_pct": 5.0,
                "avg_return_60d_pct": 8.0,
                "available_symbol_count": 100,
            },
            date(2024, 1, 3): {
                "market_regime": "weak_defensive",
                "asof_date": "2024-01-02",
                "breadth_ma20_pct": 40.0,
                "breadth_ma60_pct": 38.0,
                "avg_return_20d_pct": -3.0,
                "avg_return_60d_pct": -5.0,
                "available_symbol_count": 100,
            },
        },
        price_series={
            "000001": {date(2024, 1, 2): 10.0, date(2024, 1, 3): 10.5, date(2024, 1, 4): 11.0},
            "000002": {date(2024, 1, 3): 10.0, date(2024, 1, 4): 11.0},
        },
        trading_days=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
    )

    assert [row["market_regime"] for row in result["summary_rows"]] == ["bull_active", "weak_defensive"]
    assert [row["selected_trade_count"] for row in result["summary_rows"]] == [1, 1]
    assert [row["market_regime"] for row in result["trade_rows"]] == ["bull_active", "weak_defensive"]


def test_regime_aware_ranking_matches_baseline_when_all_days_use_default_profile() -> None:
    trades = [
        _candidate_trade("000001", "2024-01-02", "2024-01-04", 90.0),
        _candidate_trade("000002", "2024-01-02", "2024-01-04", 80.0),
        _candidate_trade("000003", "2024-01-03", "2024-01-05", 95.0),
    ]
    ranking_config = LayeredRankingConfig(max_per_day=1, pullback_quota=1, breakout_quota=0, max_open_positions=1)
    baseline = rank_trade_candidates(trades, run_name="pytest", config=ranking_config)
    regime_aware = rank_trade_candidates_by_market_regime(
        trades,
        run_name="pytest",
        profile_map=RegimeProfileMap(
            default_variant=RobustnessVariant("baseline_default", ranking_config, _no_cost_account(position_size_pct=0.5)),
            regime_variants={},
        ),
        regime_by_date={
            date(2024, 1, 2): {"market_regime": "range_neutral"},
            date(2024, 1, 3): {"market_regime": "range_neutral"},
        },
    )

    assert [row["candidate_id"] for row in regime_aware if row["selected"]] == [
        row["candidate_id"] for row in baseline if row["selected"]
    ]
    assert {row["selected_profile"] for row in regime_aware if row["selected"]} == {"baseline_default"}


def test_regime_aware_ranking_can_expand_bull_days_and_pause_bear_days() -> None:
    trades = [
        _candidate_trade("000001", "2024-01-02", "2024-01-04", 90.0),
        _candidate_trade("000002", "2024-01-02", "2024-01-04", 80.0),
        _candidate_trade("000003", "2024-01-03", "2024-01-05", 95.0),
    ]
    rows = rank_trade_candidates_by_market_regime(
        trades,
        run_name="pytest",
        profile_map=RegimeProfileMap(
            default_variant=RobustnessVariant(
                "baseline_default",
                LayeredRankingConfig(max_per_day=1, pullback_quota=1, breakout_quota=0, max_open_positions=1),
                _no_cost_account(position_size_pct=0.5),
            ),
            regime_variants={
                "bull_active": RobustnessVariant(
                    "bull_max2",
                    LayeredRankingConfig(max_per_day=2, pullback_quota=2, breakout_quota=0, max_open_positions=2),
                    _no_cost_account(position_size_pct=0.5),
                )
            },
            paused_regimes={"bear_pause"},
        ),
        regime_by_date={
            date(2024, 1, 2): {"market_regime": "bull_active"},
            date(2024, 1, 3): {"market_regime": "bear_pause"},
        },
    )

    selected_rows = [row for row in rows if row["selected"]]
    paused_rows = [row for row in rows if row["entry_date"] == "2024-01-03"]
    assert [row["stock_code"] for row in selected_rows] == ["000001", "000002"]
    assert {row["selected_profile"] for row in selected_rows} == {"bull_max2"}
    assert paused_rows[0]["selected_profile"] == "paused:bear_pause"
    assert paused_rows[0]["rank_filter_passed"] is False


def test_regime_aware_ranking_can_use_soft_bear_profile() -> None:
    trades = [
        _candidate_trade("000001", "2024-01-03", "2024-01-05", 90.0),
        _candidate_trade("000002", "2024-01-03", "2024-01-05", 80.0),
    ]
    rows = rank_trade_candidates_by_market_regime(
        trades,
        run_name="pytest",
        profile_map=RegimeProfileMap(
            default_variant=RobustnessVariant(
                "baseline_default",
                LayeredRankingConfig(max_per_day=1, pullback_quota=1, breakout_quota=0, max_open_positions=1),
                _no_cost_account(position_size_pct=0.5),
            ),
            regime_variants={
                "bear_pause": RobustnessVariant(
                    "bear_soft_max1_pullback_only",
                    LayeredRankingConfig(max_per_day=1, pullback_quota=1, breakout_quota=0, max_open_positions=1),
                    _no_cost_account(position_size_pct=0.25),
                )
            },
        ),
        regime_by_date={
            date(2024, 1, 3): {"market_regime": "bear_pause"},
        },
    )

    selected_rows = [row for row in rows if row["selected"]]
    assert [row["stock_code"] for row in selected_rows] == ["000001"]
    assert selected_rows[0]["selected_profile"] == "bear_soft_max1_pullback_only"
    assert selected_rows[0]["position_size_pct"] == 0.25
    assert {row["rank_filter_reason"] for row in rows} == {"passed"}


def test_default_regime_profile_map_keeps_bear_paused_by_default() -> None:
    profile_map = _DEFAULT_REGIME_PROFILE_MAP(
        LayeredRankingConfig(max_per_day=3, pullback_quota=2, breakout_quota=1),
        _no_cost_account(position_size_pct=0.08),
    )

    assert "bear_pause" in profile_map.paused_regimes
    assert "bear_pause" not in profile_map.regime_variants


def test_default_regime_profile_map_can_soft_trade_bear_with_position_overrides() -> None:
    profile_map = _DEFAULT_REGIME_PROFILE_MAP(
        LayeredRankingConfig(max_per_day=3, pullback_quota=2, breakout_quota=1, heat_score_cap=55.0),
        _no_cost_account(position_size_pct=0.08),
        position_sizes={
            "bull_active": 0.09,
            "range_neutral": 0.06,
            "weak_defensive": 0.1,
            "bear_pause": 0.04,
            "unknown": 0.05,
        },
        bear_action="soft",
    )

    assert "bear_pause" not in profile_map.paused_regimes
    assert profile_map.regime_variants["bear_pause"].ranking_config.max_per_day == 1
    assert profile_map.regime_variants["bear_pause"].ranking_config.breakout_quota == 0
    assert profile_map.regime_variants["bear_pause"].account_config.position_size_pct == 0.04
    assert profile_map.regime_variants["weak_defensive"].account_config.position_size_pct == 0.1


def test_default_regime_profile_map_has_risk_defensive_pullback_only_profile() -> None:
    profile_map = _DEFAULT_REGIME_PROFILE_MAP(
        LayeredRankingConfig(max_per_day=3, pullback_quota=2, breakout_quota=1, heat_score_cap=55.0),
        _no_cost_account(position_size_pct=0.08),
        position_sizes={
            "bull_active": 0.08,
            "range_neutral": 0.08,
            "weak_defensive": 0.08,
            "risk_defensive": 0.04,
            "bear_pause": 0.04,
            "unknown": 0.08,
        },
    )

    risk_variant = profile_map.regime_variants["risk_defensive"]
    assert risk_variant.name == "risk_defensive_max1_pullback_only"
    assert risk_variant.ranking_config.max_per_day == 1
    assert risk_variant.ranking_config.pullback_quota == 1
    assert risk_variant.ranking_config.breakout_quota == 0
    assert risk_variant.account_config.position_size_pct == 0.04


def test_regime_aware_profile_passes_per_regime_position_size_into_account_replay() -> None:
    trades = [
        _candidate_trade("000001", "2024-01-02", "2024-01-04", 90.0),
        _candidate_trade("000002", "2024-01-03", "2024-01-05", 95.0),
    ]
    result = run_regime_aware_profile(
        trades,
        run_name="pytest",
        profile_map=RegimeProfileMap(
            default_variant=RobustnessVariant(
                "baseline_default",
                LayeredRankingConfig(max_per_day=1, pullback_quota=1, breakout_quota=0, max_open_positions=1),
                _no_cost_account(position_size_pct=0.2),
            ),
            regime_variants={
                "bull_active": RobustnessVariant(
                    "bull_half_size",
                    LayeredRankingConfig(max_per_day=1, pullback_quota=1, breakout_quota=0, max_open_positions=1),
                    _no_cost_account(position_size_pct=0.5),
                )
            },
        ),
        regime_by_date={
            date(2024, 1, 2): {"market_regime": "bull_active"},
            date(2024, 1, 3): {"market_regime": "range_neutral"},
        },
        price_series={
            "000001": {date(2024, 1, 2): 10.0, date(2024, 1, 3): 10.5, date(2024, 1, 4): 11.0},
            "000002": {date(2024, 1, 3): 10.0, date(2024, 1, 4): 10.5, date(2024, 1, 5): 11.0},
        },
        trading_days=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)],
    )

    opened = result["account_result"]["opened_trades"]
    assert opened[0]["position_size_pct"] == 0.5
    assert opened[0]["entry_value"] == 5000.0
    assert result["ranked_rows"][0]["position_size_pct"] == 0.5


def test_summarize_rank_score_bins_reports_outcome_and_quality_diagnostics() -> None:
    rows = [
        {
            "entry_date": "2024-01-02",
            "market_regime": "bull_active",
            "signal_type": "pullback_bounce",
            "rank_score": 15.0,
            "heat_score": 40.0,
            "rank_filter_passed": True,
            "selected": True,
            "return_pct": 10.0,
            "max_adverse_excursion_pct": -2.0,
            "holding_days": 3,
            "stock_quality_trade_count": 4,
            "quality_stock_confidence": 0.5,
        },
        {
            "entry_date": "2024-01-03",
            "market_regime": "bull_active",
            "signal_type": "breakout_long",
            "rank_score": 65.0,
            "heat_score": 70.0,
            "rank_filter_passed": False,
            "rank_filter_reason": "above_heat_score_cap",
            "selected": False,
            "return_pct": -5.0,
            "max_adverse_excursion_pct": -6.0,
            "holding_days": 2,
            "stock_quality_trade_count": 8,
            "quality_stock_confidence": 0.6667,
        },
    ]

    summary = summarize_rank_score_bins(rows, period="month")
    selected_bin = [
        row
        for row in summary
        if row["period"] == "ALL"
        and row["market_regime"] == "ALL"
        and row["rank_score_bin"] == "10-20"
        and row["scope"] == "selected_candidates"
    ][0]
    filtered_bin = [
        row
        for row in summary
        if row["period"] == "ALL"
        and row["market_regime"] == "ALL"
        and row["rank_score_bin"] == "60-70"
        and row["scope"] == "filtered_candidates"
    ][0]

    assert selected_bin["candidate_count"] == 1
    assert selected_bin["win_rate_pct"] == 100.0
    assert selected_bin["avg_return_pct"] == 10.0
    assert selected_bin["avg_mae_pct"] == -2.0
    assert selected_bin["avg_holding_days"] == 3.0
    assert selected_bin["avg_quality_stock_confidence"] == 0.5
    assert filtered_bin["candidate_count"] == 1
    assert filtered_bin["profit_factor"] == 0.0
    assert filtered_bin["avg_heat_score"] == 70.0
