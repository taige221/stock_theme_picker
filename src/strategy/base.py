# -*- coding: utf-8 -*-
"""Base contracts for backtestable strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional

import pandas as pd

from theme_picker.strategy.params import StrategyParams

SignalAction = Literal["buy", "sell", "hold"]


@dataclass(frozen=True)
class StrategySignal:
    """Single-bar strategy output consumed by the backtest engine."""

    action: SignalAction = "hold"
    reason: str = ""
    score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Strategy(ABC):
    """Abstract strategy interface for historical backtests."""

    name = "base"

    @abstractmethod
    def generate_signal(
        self,
        history: pd.DataFrame,
        *,
        current_index: Optional[int] = None,
        params: StrategyParams,
        price_adjustment: str,
        has_position: bool,
        entry_price: Optional[float],
        holding_days: int,
    ) -> StrategySignal:
        """Generate a buy/sell/hold decision from historical bars."""
