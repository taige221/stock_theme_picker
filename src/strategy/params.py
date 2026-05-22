# -*- coding: utf-8 -*-
"""Strategy parameter schema for the initial A-share backtest loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(slots=True)
class StrategyParams:
    """Tunable strategy parameters exposed to manual or AI optimization."""

    breakout_lookback_days: int = 20
    min_breakout_pct: float = 2.5
    min_volume_ratio: float = 1.5
    max_bias_ma10_pct: float = 4.0
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.12
    max_holding_days: int = 10
    position_size_pct: float = 1.0
    box_lookback_days: int = 30
    box_tolerance_pct: float = 0.015
    min_box_touches: int = 2
    min_box_height_pct: float = 0.05
    breakout_retest_window: int = 5
    pullback_reclaim_pct: float = 0.003
    stop_buffer_pct: float = 0.01
    rr_min: float = 2.0
    max_breakout_extension_pct: float = 0.08
    require_uptrend_for_entry: bool = True
    signal_number_lookback_days: int = 90
    signal_number_event_cooldown_days: int = 10
    min_turnover_rate: float = 2.0
    preferred_turnover_rate_low: float = 3.0
    preferred_turnover_rate_high: float = 12.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "StrategyParams":
        data = dict(payload or {})
        allowed = {field_name for field_name in cls.__dataclass_fields__}
        normalized = {key: value for key, value in data.items() if key in allowed}
        return cls(**normalized)
