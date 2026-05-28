# -*- coding: utf-8 -*-
"""Strategy parameter schema for the initial A-share backtest loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Optional


class StrategyParamValidationError(ValueError):
    """Raised when a strategy parameter payload is malformed."""


@dataclass(slots=True)
class StrategyParams:
    """Tunable strategy parameters exposed to manual or AI optimization."""

    breakout_lookback_days: int = 20
    min_breakout_pct: float = 2.5
    min_volume_ratio: float = 1.5
    breakout_min_breakout_pct: Optional[float] = None
    breakout_min_volume_ratio: Optional[float] = None
    breakout_min_body_pct: Optional[float] = None
    breakout_min_close_above_resistance_pct: Optional[float] = None
    breakout_max_upper_shadow_ratio: Optional[float] = None
    pullback_min_volume_ratio: Optional[float] = None
    max_bias_ma10_pct: float = 0.0
    breakout_max_bias_ma10_pct: Optional[float] = None
    pullback_max_bias_ma10_pct: Optional[float] = None
    stop_loss_pct: float = 0.05
    breakout_stop_loss_pct: Optional[float] = None
    pullback_stop_loss_pct: Optional[float] = None
    take_profit_pct: float = 0.12
    breakout_take_profit_pct: Optional[float] = None
    pullback_take_profit_pct: Optional[float] = None
    max_holding_days: int = 10
    breakout_max_holding_days: Optional[int] = None
    pullback_max_holding_days: Optional[int] = None
    position_size_pct: float = 1.0
    box_lookback_days: int = 30
    box_tolerance_pct: float = 0.015
    min_box_touches: int = 2
    breakout_min_box_touches: Optional[int] = None
    pullback_min_box_touches: Optional[int] = None
    pullback_slow_large_min_box_touches: Optional[int] = None
    pullback_balanced_trend_min_box_touches: Optional[int] = None
    pullback_high_beta_min_box_touches: Optional[int] = None
    min_box_height_pct: float = 0.05
    breakout_max_box_height_pct: Optional[float] = None
    breakout_avoid_box_height_low_pct: float = 0.0
    breakout_avoid_box_height_high_pct: float = 0.0
    pullback_min_box_height_pct: Optional[float] = None
    breakout_retest_window: int = 5
    pullback_reclaim_pct: float = 0.003
    pullback_max_break_below_resistance_pct: Optional[float] = None
    pullback_slow_large_reclaim_pct: Optional[float] = None
    pullback_balanced_trend_reclaim_pct: Optional[float] = None
    pullback_high_beta_reclaim_pct: Optional[float] = None
    stop_buffer_pct: float = 0.01
    rr_min: float = 2.0
    max_breakout_extension_pct: float = 0.08
    breakout_max_extension_pct: Optional[float] = None
    breakout_min_stack_lift_pct: float = 0.0
    block_breakout_after_downtrend: bool = False
    require_uptrend_for_entry: bool = True
    signal_number_lookback_days: int = 90
    signal_number_event_cooldown_days: int = 10
    min_turnover_rate: float = 2.0
    preferred_turnover_rate_low: float = 3.0
    preferred_turnover_rate_high: float = 12.0
    max_turnover_rate: float = 0.0
    min_signal_score: float = 0.0
    breakout_min_signal_score: Optional[float] = None
    pullback_min_signal_score: Optional[float] = None
    score_high_box_height_threshold_pct: float = 0.0
    score_high_box_height_penalty: float = 0.0
    score_high_turnover_rate_threshold: float = 0.0
    score_high_turnover_rate_penalty: float = 0.0
    score_high_volume_ratio_threshold: float = 0.0
    score_high_volume_ratio_penalty: float = 0.0
    enable_macd_score_adjustment: bool = False
    macd_bullish_bonus: float = 0.0
    macd_bearish_penalty: float = 0.0
    breakout_high_volume_macd_weak_penalty: float = 0.0
    pullback_macd_weak_penalty: float = 0.0
    enable_macd_divergence_decision: bool = False
    macd_divergence_lookback_days: int = 20
    macd_divergence_price_tolerance_pct: float = 0.003
    breakout_macd_bearish_divergence_min_volume_ratio: float = 0.0
    breakout_macd_bearish_divergence_penalty: float = 0.0
    breakout_block_macd_bearish_divergence: bool = False
    pullback_macd_bullish_divergence_bonus: float = 0.0
    enable_pullback_rebound_risk_control: bool = False
    pullback_rebound_recent_gain_days: int = 5
    pullback_rebound_max_recent_gain_pct: float = 10.0
    pullback_rebound_max_bias_ma10_pct: float = 10.0
    pullback_rebound_score_penalty: float = 0.0
    pullback_rebound_block_entry: bool = False
    enable_pullback_profit_power_filter: bool = False
    pullback_profit_power_lookback_days: int = 120
    pullback_profit_power_min_range_pct: float = 80.0
    pullback_profit_power_rolling_gain_days: int = 20
    pullback_profit_power_min_rolling_gain_pct: float = 0.0
    pullback_profit_power_max_recent_gain_pct: float = 0.0
    pullback_profit_power_max_ma10_bias_pct: float = 0.0
    pullback_rebound_profit_power_penalty_multiplier: float = 0.0
    enable_breakout_trend_hold_extension: bool = False
    breakout_trend_hold_extension_max_days: int = 25
    box_stack_lift_score_weight: float = 0.0
    box_height_score_weight: float = 0.0
    enable_entry_stall_exit: bool = False
    breakout_enable_entry_stall_exit: Optional[bool] = None
    pullback_enable_entry_stall_exit: Optional[bool] = None
    entry_stall_days: int = 3
    breakout_entry_stall_days: Optional[int] = None
    pullback_entry_stall_days: Optional[int] = None
    entry_stall_min_return_pct: float = 0.02
    breakout_entry_stall_min_return_pct: Optional[float] = None
    pullback_entry_stall_min_return_pct: Optional[float] = None
    pullback_slow_large_enable_entry_stall_exit: Optional[bool] = None
    pullback_balanced_trend_enable_entry_stall_exit: Optional[bool] = None
    pullback_high_beta_enable_entry_stall_exit: Optional[bool] = None
    pullback_slow_large_entry_stall_days: Optional[int] = None
    pullback_balanced_trend_entry_stall_days: Optional[int] = None
    pullback_high_beta_entry_stall_days: Optional[int] = None
    pullback_slow_large_entry_stall_min_return_pct: Optional[float] = None
    pullback_balanced_trend_entry_stall_min_return_pct: Optional[float] = None
    pullback_high_beta_entry_stall_min_return_pct: Optional[float] = None
    enable_symbol_loss_cooldown: bool = False
    symbol_loss_cooldown_losses: int = 2
    symbol_loss_cooldown_days: int = 20
    enable_trailing_stop: bool = False
    breakout_enable_trailing_stop: Optional[bool] = None
    pullback_enable_trailing_stop: Optional[bool] = None
    pullback_slow_large_enable_trailing_stop: Optional[bool] = None
    pullback_balanced_trend_enable_trailing_stop: Optional[bool] = None
    pullback_high_beta_enable_trailing_stop: Optional[bool] = None
    trailing_stop_activate_profit_pct: float = 0.08
    breakout_trailing_stop_activate_profit_pct: Optional[float] = None
    pullback_trailing_stop_activate_profit_pct: Optional[float] = None
    pullback_slow_large_trailing_stop_activate_profit_pct: Optional[float] = None
    pullback_balanced_trend_trailing_stop_activate_profit_pct: Optional[float] = None
    pullback_high_beta_trailing_stop_activate_profit_pct: Optional[float] = None
    trailing_stop_drawdown_pct: float = 0.04
    breakout_trailing_stop_drawdown_pct: Optional[float] = None
    pullback_trailing_stop_drawdown_pct: Optional[float] = None
    pullback_slow_large_trailing_stop_drawdown_pct: Optional[float] = None
    pullback_balanced_trend_trailing_stop_drawdown_pct: Optional[float] = None
    pullback_high_beta_trailing_stop_drawdown_pct: Optional[float] = None
    enable_ma10_confirm_exit: bool = False
    breakout_enable_ma10_confirm_exit: Optional[bool] = None
    pullback_enable_ma10_confirm_exit: Optional[bool] = None
    ma10_confirm_days: int = 2
    breakout_ma10_confirm_days: Optional[int] = None
    pullback_ma10_confirm_days: Optional[int] = None
    pullback_enable_failure_exit: bool = False
    pullback_failure_exit_days: int = 5
    pullback_failure_confirm_days: int = 1
    pullback_failure_buffer_pct: float = 0.003
    pullback_failure_max_profit_pct: float = 0.03
    enable_breakeven_stop: bool = False
    breakout_enable_breakeven_stop: Optional[bool] = None
    pullback_enable_breakeven_stop: Optional[bool] = None
    breakeven_activate_profit_pct: float = 0.03
    breakeven_exit_threshold_pct: float = 0.005

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None, *, strict: bool = True) -> "StrategyParams":
        if payload is None:
            params = cls()
            params.validate()
            return params
        if not isinstance(payload, dict):
            raise StrategyParamValidationError("StrategyParams payload must be a JSON object")

        data = dict(payload)
        allowed = {field.name for field in fields(cls)}
        unknown = sorted(key for key in data if key not in allowed)
        if unknown and strict:
            joined = ", ".join(unknown)
            raise StrategyParamValidationError(f"Unknown StrategyParams field(s): {joined}")

        normalized = {key: value for key, value in data.items() if key in allowed}
        params = cls(**normalized)
        params.validate()
        return params

    def validate(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if value is None or isinstance(value, bool):
                continue
            if isinstance(value, (int, float)) and value < 0:
                raise StrategyParamValidationError(f"{field.name} must be non-negative")

        self._require_positive("box_lookback_days")
        self._require_positive("breakout_lookback_days")
        self._require_positive("max_holding_days")
        self._require_positive("signal_number_lookback_days")
        self._require_positive("signal_number_event_cooldown_days")
        self._require_positive("pullback_profit_power_lookback_days")
        self._require_positive("pullback_profit_power_rolling_gain_days")
        self._require_positive("pullback_rebound_recent_gain_days")
        self._require_positive("breakout_trend_hold_extension_max_days")
        self._require_positive("entry_stall_days")
        self._require_positive("ma10_confirm_days")
        self._require_positive("pullback_failure_confirm_days")
        self._require_positive("symbol_loss_cooldown_losses")
        self._require_positive("symbol_loss_cooldown_days")
        self._require_optional_positive("breakout_max_holding_days")
        self._require_optional_positive("pullback_max_holding_days")
        self._require_optional_positive("breakout_entry_stall_days")
        self._require_optional_positive("pullback_entry_stall_days")
        self._require_optional_positive("pullback_slow_large_entry_stall_days")
        self._require_optional_positive("pullback_balanced_trend_entry_stall_days")
        self._require_optional_positive("pullback_high_beta_entry_stall_days")
        self._require_optional_positive("breakout_ma10_confirm_days")
        self._require_optional_positive("pullback_ma10_confirm_days")

        if not 0 < float(self.position_size_pct) <= 1:
            raise StrategyParamValidationError("position_size_pct must be > 0 and <= 1")

    def _require_positive(self, name: str) -> None:
        value = getattr(self, name)
        if value <= 0:
            raise StrategyParamValidationError(f"{name} must be positive")

    def _require_optional_positive(self, name: str) -> None:
        value = getattr(self, name)
        if value is not None and value <= 0:
            raise StrategyParamValidationError(f"{name} must be positive when set")