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
    max_drawdown_pct, max_drawdown_amount = _calculate_drawdown(equity_curve)
    winners = [trade for trade in trades if _float_attr(trade, "net_pnl") > 0]
    losers = [trade for trade in trades if _float_attr(trade, "net_pnl") < 0]
    gross_profit = sum(_float_attr(trade, "net_pnl") for trade in winners)
    gross_loss = abs(sum(_float_attr(trade, "net_pnl") for trade in losers))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
    return_pcts = [_float_attr(trade, "return_pct") for trade in trades]
    avg_return_pct = _average(return_pcts)
    avg_win_pct = _average([_float_attr(trade, "return_pct") for trade in winners])
    avg_loss_pct = _average([_float_attr(trade, "return_pct") for trade in losers])
    expectancy_pct = (
        (len(winners) / len(trades) * avg_win_pct) + (len(losers) / len(trades) * avg_loss_pct)
        if trades
        else 0.0
    )
    avg_win_pnl = (gross_profit / len(winners)) if winners else 0.0
    avg_loss_pnl_abs = (gross_loss / len(losers)) if losers else 0.0
    payoff_ratio = (avg_win_pnl / avg_loss_pnl_abs) if avg_loss_pnl_abs > 0 else None
    trade_days_held_total = sum(max(0, int(_float_attr(trade, "holding_days"))) for trade in trades)
    avg_holding_days = (trade_days_held_total / len(trades)) if trades else 0.0
    total_cost = sum(_trade_total_cost(trade) for trade in trades)
    cost_return_drag_pct = (total_cost / initial_cash * 100.0) if initial_cash else 0.0
    net_profit = final_equity - initial_cash
    recovery_factor = (net_profit / max_drawdown_amount) if max_drawdown_amount > 0 else None
    calmar_like = (total_return_pct / max_drawdown_pct) if max_drawdown_pct > 0 else None
    max_trade_mfe_pct = max((_float_attr(trade, "max_favorable_excursion_pct") for trade in trades), default=0.0)
    max_trade_mae_pct = min((_float_attr(trade, "max_adverse_excursion_pct") for trade in trades), default=0.0)
    exposure_days = trade_days_held_total + _open_position_holding_days(
        open_position=open_position,
        equity_curve=equity_curve,
    )
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
        "avg_win_pct": round(avg_win_pct, 2),
        "avg_loss_pct": round(avg_loss_pct, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "has_open_position": has_open_position,
        "open_position_market_value": round(open_position_market_value, 2),
        "final_unrealized_pnl": round(final_unrealized_pnl, 2),
        "final_unrealized_pnl_pct": round(final_unrealized_pnl_pct, 2),
        "max_trade_mfe_pct": round(max_trade_mfe_pct, 2),
        "max_trade_mae_pct": round(max_trade_mae_pct, 2),
        "avg_return_pct": round(avg_return_pct, 2),
        "expectancy_pct": round(expectancy_pct, 2),
        "payoff_ratio": round(payoff_ratio, 2) if payoff_ratio is not None else None,
        "avg_holding_days": round(avg_holding_days, 2),
        "max_consecutive_losses": _max_consecutive_losses(trades),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "total_cost": round(total_cost, 2),
        "cost_return_drag_pct": round(cost_return_drag_pct, 2),
        "trade_days_held_total": trade_days_held_total,
        "exposure_days": exposure_days,
        "recovery_factor": round(recovery_factor, 2) if recovery_factor is not None else None,
        "calmar_like": round(calmar_like, 2) if calmar_like is not None else None,
    }


def _calculate_max_drawdown_pct(equity_curve: Iterable[EquityPoint]) -> float:
    return _calculate_drawdown(equity_curve)[0]


def _calculate_drawdown(equity_curve: Iterable[EquityPoint]) -> tuple[float, float]:
    peak = None
    max_drawdown = 0.0
    max_drawdown_amount = 0.0
    for point in equity_curve:
        equity = float(point.equity or 0.0)
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > 0:
            drawdown_amount = peak - equity
            drawdown_pct = drawdown_amount / peak * 100.0
            if drawdown_pct > max_drawdown:
                max_drawdown = drawdown_pct
                max_drawdown_amount = drawdown_amount
    return max_drawdown, max_drawdown_amount


def _average(values: Iterable[float]) -> float:
    items = list(values)
    return (sum(items) / len(items)) if items else 0.0


def _float_attr(item: Any, name: str, default: float = 0.0) -> float:
    value = getattr(item, name, default)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _trade_total_cost(trade: Any) -> float:
    gross_pnl = _float_attr(trade, "gross_pnl")
    net_pnl = _float_attr(trade, "net_pnl")
    estimated_cost = max(0.0, gross_pnl - net_pnl)

    explicit_cost = getattr(trade, "total_cost", None)
    if explicit_cost is not None:
        parsed_cost = max(0.0, _float_attr(trade, "total_cost"))
        return parsed_cost if parsed_cost > 0 or estimated_cost <= 0 else estimated_cost

    return estimated_cost


def _max_consecutive_losses(trades: Iterable[Any]) -> int:
    current = 0
    max_losses = 0
    for trade in trades:
        if _float_attr(trade, "net_pnl") < 0:
            current += 1
            max_losses = max(max_losses, current)
        else:
            current = 0
    return max_losses


def _open_position_holding_days(
    *,
    open_position: Position | None,
    equity_curve: List[EquityPoint],
) -> int:
    if open_position is None or not equity_curve:
        return 0
    latest_date = equity_curve[-1].trade_date
    return max(0, (latest_date - open_position.entry_date).days)
