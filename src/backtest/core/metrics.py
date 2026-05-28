# -*- coding: utf-8 -*-
"""Performance metrics for the minimal backtest engine."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from theme_picker.backtest.core.models import EquityPoint, Position, Trade


def calculate_metrics(
    *,
    trades: List[Trade],
    equity_curve: List[EquityPoint],
    initial_cash: float,
    final_equity: float,
    open_position: Position | None = None,
    latest_close: float | None = None,
) -> Dict[str, Any]:
    total_return_pct = ((final_equity - initial_cash) / initial_cash * 100.0) if initial_cash else 0.0
    max_drawdown_pct = _calculate_max_drawdown_pct(equity_curve)
    winners = [trade for trade in trades if trade.net_pnl > 0]
    losers = [trade for trade in trades if trade.net_pnl < 0]
    gross_profit = sum(trade.net_pnl for trade in winners)
    gross_loss = abs(sum(trade.net_pnl for trade in losers))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
    max_trade_mfe_pct = max((float(trade.max_favorable_excursion_pct or 0.0) for trade in trades), default=0.0)
    max_trade_mae_pct = min((float(trade.max_adverse_excursion_pct or 0.0) for trade in trades), default=0.0)
    final_unrealized_pnl = 0.0
    final_unrealized_pnl_pct = 0.0
    open_position_market_value = 0.0
    has_open_position = open_position is not None
    if open_position is not None and latest_close is not None and latest_close > 0:
        open_position_market_value = latest_close * int(open_position.shares)
        final_unrealized_pnl = (latest_close - float(open_position.entry_price)) * int(open_position.shares)
        invested = float(open_position.entry_price) * int(open_position.shares)
        final_unrealized_pnl_pct = (final_unrealized_pnl / invested * 100.0) if invested else 0.0

    return {
        "initial_cash": round(initial_cash, 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "trade_count": len(trades),
        "win_rate_pct": round((len(winners) / len(trades) * 100.0), 2) if trades else 0.0,
        "avg_win_pct": round(sum(trade.return_pct for trade in winners) / len(winners), 2) if winners else 0.0,
        "avg_loss_pct": round(sum(trade.return_pct for trade in losers) / len(losers), 2) if losers else 0.0,
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "has_open_position": has_open_position,
        "open_position_market_value": round(open_position_market_value, 2),
        "final_unrealized_pnl": round(final_unrealized_pnl, 2),
        "final_unrealized_pnl_pct": round(final_unrealized_pnl_pct, 2),
        "max_trade_mfe_pct": round(max_trade_mfe_pct, 2),
        "max_trade_mae_pct": round(max_trade_mae_pct, 2),
    }


def _calculate_max_drawdown_pct(equity_curve: Iterable[EquityPoint]) -> float:
    peak = None
    max_drawdown = 0.0
    for point in equity_curve:
        equity = float(point.equity or 0.0)
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > 0:
            drawdown = (peak - equity) / peak * 100.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
    return max_drawdown
