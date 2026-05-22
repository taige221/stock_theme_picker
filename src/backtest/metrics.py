# -*- coding: utf-8 -*-
"""Performance metrics for the minimal backtest engine."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from theme_picker.backtest.models import EquityPoint, Trade


def calculate_metrics(
    *,
    trades: List[Trade],
    equity_curve: List[EquityPoint],
    initial_cash: float,
    final_equity: float,
) -> Dict[str, Any]:
    total_return_pct = ((final_equity - initial_cash) / initial_cash * 100.0) if initial_cash else 0.0
    max_drawdown_pct = _calculate_max_drawdown_pct(equity_curve)
    winners = [trade for trade in trades if trade.net_pnl > 0]
    losers = [trade for trade in trades if trade.net_pnl < 0]
    gross_profit = sum(trade.net_pnl for trade in winners)
    gross_loss = abs(sum(trade.net_pnl for trade in losers))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

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
