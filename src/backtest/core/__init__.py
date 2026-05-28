# -*- coding: utf-8 -*-
"""Core backtest execution, models, and metrics."""

from theme_picker.backtest.core.engine import BacktestEngine
from theme_picker.backtest.core.metrics import calculate_metrics
from theme_picker.backtest.core.models import BacktestConfig, BacktestResult, EquityPoint, Position, Trade

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "EquityPoint",
    "Position",
    "Trade",
    "calculate_metrics",
]
