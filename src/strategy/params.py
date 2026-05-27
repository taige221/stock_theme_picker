# -*- coding: utf-8 -*-
"""Strategy parameter schema for the initial A-share backtest loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


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
    min_signal_score: float = 0.0
    breakout_min_signal_score: Optional[float] = None
    pullback_min_signal_score: Optional[float] = None
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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "StrategyParams":
        data = dict(payload or {})
        allowed = {field_name for field_name in cls.__dataclass_fields__}
        normalized = {key: value for key, value in data.items() if key in allowed}
        return cls(**normalized)
