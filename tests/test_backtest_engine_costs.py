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


def test_a_share_costs_include_min_commission_stamp_tax_and_net_pnl() -> None:
    bars = pd.DataFrame(
        [
            {"date": "2024-01-01", "open": 9.8, "high": 10.2, "low": 9.7, "close": 10.0},
            {"date": "2024-01-02", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1},
            {"date": "2024-01-03", "open": 10.5, "high": 10.8, "low": 10.2, "close": 10.7},
            {"date": "2024-01-04", "open": 11.0, "high": 11.2, "low": 10.8, "close": 11.1},
        ]
    )

    result = BacktestEngine().run(
        stock_code="000001",
        bars=bars,
        strategy=ScriptedStrategy({0: "buy", 2: "sell"}),
        params=StrategyParams(position_size_pct=1.0),
        config=BacktestConfig(
            initial_cash=1500.0,
            commission_bps=3.0,
            slippage_bps=0.0,
            lot_size=100,
            min_commission=5.0,
            stamp_tax_bps=5.0,
            transfer_fee_bps=0.1,
        ),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.shares == 100
    assert trade.gross_pnl == 100.0
    assert trade.entry_commission == 5.0
    assert trade.entry_stamp_tax == 0.0
    assert trade.entry_transfer_fee == 0.01
    assert trade.entry_cost == 5.01
    assert trade.exit_commission == 5.0
    assert trade.exit_stamp_tax == 0.55
    assert trade.exit_transfer_fee == 0.01
    assert trade.exit_cost == 5.56
    assert trade.total_cost == 10.57
    assert trade.net_pnl == 89.43

    payload = trade.to_dict()
    assert payload["entry_cost"] == 5.01
    assert payload["exit_stamp_tax"] == 0.55
    assert payload["total_cost"] == 10.57
    assert result.metrics["final_equity"] == 1589.43
