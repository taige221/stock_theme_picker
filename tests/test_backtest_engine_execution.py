# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from theme_picker.backtest.engine import BacktestEngine
from theme_picker.backtest.models import BacktestConfig
from theme_picker.strategy.base import Strategy, StrategySignal
from theme_picker.strategy.params import StrategyParams


class ScriptedStrategy(Strategy):
    name = "scripted"

    def __init__(self, actions: dict[int, str]) -> None:
        self._actions = actions

    def generate_signal(
        self,
        history: pd.DataFrame,
        *,
        current_index=None,
        params,
        price_adjustment,
        has_position,
        entry_price,
        holding_days,
        entry_signal_reason=None,
        entry_signal_metadata=None,
        position_highest_price_seen=None,
    ) -> StrategySignal:
        action = self._actions.get(int(current_index), "hold")
        return StrategySignal(action=action, reason=f"{action}_{current_index}", score=80.0)


def _bars(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_engine_executes_signals_on_next_bar_open() -> None:
    bars = _bars(
        [
            {"date": "2024-01-01", "open": 10.0, "high": 11.0, "low": 9.0, "close": 11.0},
            {"date": "2024-01-02", "open": 12.0, "high": 20.0, "low": 11.0, "close": 20.0},
            {"date": "2024-01-03", "open": 13.0, "high": 22.0, "low": 12.0, "close": 21.0},
            {"date": "2024-01-04", "open": 14.0, "high": 16.0, "low": 13.0, "close": 15.0},
        ]
    )

    result = BacktestEngine().run(
        stock_code="000001",
        bars=bars,
        strategy=ScriptedStrategy({0: "buy", 2: "sell"}),
        params=StrategyParams(position_size_pct=1.0),
        config=BacktestConfig(initial_cash=1000.0, commission_bps=0.0, slippage_bps=0.0, lot_size=1),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_date.isoformat() == "2024-01-02"
    assert trade.entry_price == 12.0
    assert trade.exit_date.isoformat() == "2024-01-04"
    assert trade.exit_price == 14.0


def test_pending_buy_uses_execution_bar_limits() -> None:
    bars = _bars(
        [
            {
                "date": "2024-01-01",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 11.0,
                "raw_close": 11.0,
                "up_limit": 12.0,
                "is_suspended": 0,
            },
            {
                "date": "2024-01-02",
                "open": 12.0,
                "high": 12.0,
                "low": 12.0,
                "close": 12.0,
                "raw_close": 12.0,
                "up_limit": 12.0,
                "is_suspended": 0,
            },
            {
                "date": "2024-01-03",
                "open": 13.0,
                "high": 14.0,
                "low": 12.0,
                "close": 13.0,
                "raw_close": 13.0,
                "up_limit": 14.0,
                "is_suspended": 0,
            },
        ]
    )

    result = BacktestEngine().run(
        stock_code="000001",
        bars=bars,
        strategy=ScriptedStrategy({0: "buy"}),
        params=StrategyParams(position_size_pct=1.0),
        config=BacktestConfig(
            initial_cash=1000.0,
            commission_bps=0.0,
            slippage_bps=0.0,
            lot_size=1,
            trading_constraint_mode="daily_limits",
            allow_limit_up_entry=False,
        ),
    )

    assert result.trades == []
    assert result.open_position is None
    assert any("2024-01-02 买入信号(2024-01-01)因涨停约束被跳过" in note for note in result.notes)
