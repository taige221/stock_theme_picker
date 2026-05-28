# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from theme_picker.backtest.core.metrics import calculate_metrics
from theme_picker.backtest.models import EquityPoint, Trade


def _trade(
    *,
    entry_day: int,
    exit_day: int,
    gross_pnl: float,
    net_pnl: float,
    return_pct: float,
    holding_days: int,
    mfe_pct: float = 0.0,
    mae_pct: float = 0.0,
) -> Trade:
    return Trade(
        stock_code="000001",
        entry_date=date(2024, 1, entry_day),
        exit_date=date(2024, 1, exit_day),
        entry_price=10.0,
        exit_price=10.0,
        shares=100,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        return_pct=return_pct,
        holding_days=holding_days,
        exit_reason="test",
        max_favorable_excursion_pct=mfe_pct,
        max_adverse_excursion_pct=mae_pct,
    )


def _equity_point(day: int, equity: float) -> EquityPoint:
    return EquityPoint(
        trade_date=date(2024, 1, day),
        cash=equity,
        market_value=0.0,
        equity=equity,
    )


def test_metrics_include_review_fields_for_winning_and_losing_trades() -> None:
    trades = [
        _trade(entry_day=1, exit_day=2, gross_pnl=110.0, net_pnl=100.0, return_pct=10.0, holding_days=2, mfe_pct=15.0, mae_pct=-2.0),
        _trade(entry_day=3, exit_day=4, gross_pnl=-45.0, net_pnl=-50.0, return_pct=-5.0, holding_days=3, mfe_pct=4.0, mae_pct=-8.0),
        _trade(entry_day=5, exit_day=6, gross_pnl=-20.0, net_pnl=-25.0, return_pct=-2.5, holding_days=1, mfe_pct=2.0, mae_pct=-4.0),
        _trade(entry_day=7, exit_day=8, gross_pnl=80.0, net_pnl=75.0, return_pct=7.5, holding_days=4, mfe_pct=9.0, mae_pct=-1.0),
    ]
    equity_curve = [
        _equity_point(1, 1000.0),
        _equity_point(2, 1100.0),
        _equity_point(3, 950.0),
        _equity_point(4, 1100.0),
    ]

    metrics = calculate_metrics(
        trades=trades,
        equity_curve=equity_curve,
        initial_cash=1000.0,
        final_equity=1100.0,
    )

    assert metrics["trade_count"] == 4
    assert metrics["win_rate_pct"] == 50.0
    assert metrics["avg_win_pct"] == 8.75
    assert metrics["avg_loss_pct"] == -3.75
    assert metrics["profit_factor"] == 2.33
    assert metrics["avg_return_pct"] == 2.5
    assert metrics["expectancy_pct"] == 2.5
    assert metrics["payoff_ratio"] == 2.33
    assert metrics["avg_holding_days"] == 2.5
    assert metrics["trade_days_held_total"] == 10
    assert metrics["exposure_days"] == 10
    assert metrics["max_consecutive_losses"] == 2
    assert metrics["gross_profit"] == 175.0
    assert metrics["gross_loss"] == 75.0
    assert metrics["total_cost"] == 25.0
    assert metrics["cost_return_drag_pct"] == 2.5
    assert metrics["recovery_factor"] == 0.67
    assert metrics["calmar_like"] == 0.73
    assert metrics["max_trade_mfe_pct"] == 15.0
    assert metrics["max_trade_mae_pct"] == -8.0


@dataclass
class TradeWithTotalCost:
    gross_pnl: float
    net_pnl: float
    return_pct: float
    holding_days: int
    total_cost: float
    max_favorable_excursion_pct: float = 0.0
    max_adverse_excursion_pct: float = 0.0


def test_metrics_prefer_explicit_total_cost_when_available() -> None:
    trade = TradeWithTotalCost(
        gross_pnl=100.0,
        net_pnl=90.0,
        return_pct=9.0,
        holding_days=2,
        total_cost=3.0,
    )

    metrics = calculate_metrics(
        trades=[trade],  # type: ignore[list-item]
        equity_curve=[_equity_point(1, 1000.0)],
        initial_cash=1000.0,
        final_equity=1090.0,
    )

    assert metrics["total_cost"] == 3.0
    assert metrics["cost_return_drag_pct"] == 0.3


def test_metrics_return_neutral_values_for_empty_trades() -> None:
    metrics = calculate_metrics(
        trades=[],
        equity_curve=[],
        initial_cash=1000.0,
        final_equity=1000.0,
    )

    assert metrics["trade_count"] == 0
    assert metrics["win_rate_pct"] == 0.0
    assert metrics["avg_return_pct"] == 0.0
    assert metrics["expectancy_pct"] == 0.0
    assert metrics["payoff_ratio"] is None
    assert metrics["avg_holding_days"] == 0.0
    assert metrics["max_consecutive_losses"] == 0
    assert metrics["gross_profit"] == 0.0
    assert metrics["gross_loss"] == 0.0
    assert metrics["total_cost"] == 0.0
    assert metrics["cost_return_drag_pct"] == 0.0
    assert metrics["trade_days_held_total"] == 0
    assert metrics["exposure_days"] == 0
    assert metrics["recovery_factor"] is None
    assert metrics["calmar_like"] is None
