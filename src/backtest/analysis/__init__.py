# -*- coding: utf-8 -*-
"""Backtest analysis and research overlays."""

from theme_picker.backtest.analysis.real_capital import RealCapitalConfig, simulate_real_capital_portfolio
from theme_picker.backtest.analysis.robustness import (
    MarketRegimeConfig,
    MarketRegimeOverrideConfig,
    RegimeProfileMap,
    RobustnessVariant,
    apply_market_regime_overrides,
    build_market_regime_series,
    classify_market_regime,
    compare_profile_variants,
    evaluate_robustness_variant,
    monte_carlo_equity_bootstrap,
    rank_trade_candidates_by_market_regime,
    run_parameter_sensitivity,
    run_regime_aware_profile,
    run_walk_forward_windows,
    summarize_daily_rank_filters,
    summarize_profiles_by_market_regime,
    summarize_rank_score_bins,
    summarize_rank_filters_by_period_regime,
    summarize_selected_by_period_regime,
)
from theme_picker.backtest.analysis.signal_ranking import LayeredRankingConfig, rank_trade_candidates

__all__ = [
    "LayeredRankingConfig",
    "MarketRegimeConfig",
    "MarketRegimeOverrideConfig",
    "RegimeProfileMap",
    "RealCapitalConfig",
    "RobustnessVariant",
    "apply_market_regime_overrides",
    "build_market_regime_series",
    "classify_market_regime",
    "compare_profile_variants",
    "evaluate_robustness_variant",
    "monte_carlo_equity_bootstrap",
    "rank_trade_candidates",
    "rank_trade_candidates_by_market_regime",
    "run_parameter_sensitivity",
    "run_regime_aware_profile",
    "run_walk_forward_windows",
    "summarize_daily_rank_filters",
    "summarize_profiles_by_market_regime",
    "summarize_rank_score_bins",
    "summarize_rank_filters_by_period_regime",
    "summarize_selected_by_period_regime",
    "simulate_real_capital_portfolio",
]
