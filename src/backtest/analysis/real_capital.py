# -*- coding: utf-8 -*-
"""Real-capital portfolio simulation for ranked backtest trades."""

from __future__ import annotations

import bisect
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

import duckdb

from theme_picker.backtest.analysis.signal_ranking import (
    parse_iso_date,
    resolve_backtest_database_path,
    round_float,
    to_float,
    to_int,
)
from theme_picker.infrastructure.stock_pool_service import build_stock_code_variants, canonicalize_stock_code


@dataclass(slots=True)
class RealCapitalConfig:
    initial_cash: float = 1_000_000.0
    position_size_pct: float = 0.10
    max_positions: int = 8
    lot_size: int = 100
    commission_bps: float = 10.0
    min_commission: float = 5.0
    stamp_tax_bps: float = 5.0
    transfer_fee_bps: float = 0.1
    price_adjustment: str = "qfq"

    def normalized(self) -> "RealCapitalConfig":
        return RealCapitalConfig(
            initial_cash=max(0.0, float(self.initial_cash)),
            position_size_pct=max(0.0, min(1.0, float(self.position_size_pct))),
            max_positions=max(1, int(self.max_positions)),
            lot_size=max(1, int(self.lot_size)),
            commission_bps=max(0.0, float(self.commission_bps)),
            min_commission=max(0.0, float(self.min_commission)),
            stamp_tax_bps=max(0.0, float(self.stamp_tax_bps)),
            transfer_fee_bps=max(0.0, float(self.transfer_fee_bps)),
            price_adjustment=str(self.price_adjustment or "qfq").strip().lower() or "qfq",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.normalized())


@dataclass(slots=True)
class _AccountPosition:
    stock_code: str
    stock_name: str | None
    trade_id: str | None
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    shares: int
    entry_value: float
    entry_cost: float
    entry_cash_out: float
    position_size_pct: float
    signal_type: str | None
    rank_score: float | None
    selected_order: int | None
    source_row: dict[str, Any]


@dataclass(slots=True)
class _MarkPriceLookup:
    price: float
    source: str
    source_date: date | None = None
    fallback_reason: str | None = None


class _MarkPriceDiagnostics:
    def __init__(self) -> None:
        self.lookup_count = 0
        self.current_price_count = 0
        self.carried_forward_price_count = 0
        self.entry_fallback_count = 0
        self.missing_series_fallback_count = 0
        self.before_series_fallback_count = 0
        self.fallback_symbols: dict[str, int] = {}
        self.carried_forward_symbols: dict[str, int] = {}
        self.fallback_examples: list[dict[str, Any]] = []
        self.carried_forward_examples: list[dict[str, Any]] = []

    def record(self, stock_code: str, current_day: date | None, lookup: _MarkPriceLookup) -> None:
        self.lookup_count += 1
        canonical = _canonical_code(stock_code)
        if lookup.source == "current":
            self.current_price_count += 1
            return
        if lookup.source == "carry_forward":
            self.carried_forward_price_count += 1
            self.carried_forward_symbols[canonical] = self.carried_forward_symbols.get(canonical, 0) + 1
            if len(self.carried_forward_examples) < 20:
                self.carried_forward_examples.append(
                    {
                        "stock_code": canonical,
                        "trade_date": current_day.isoformat() if current_day else None,
                        "source_date": lookup.source_date.isoformat() if lookup.source_date else None,
                    }
                )
            return
        if lookup.source == "entry_fallback":
            self.entry_fallback_count += 1
            self.fallback_symbols[canonical] = self.fallback_symbols.get(canonical, 0) + 1
            if lookup.fallback_reason == "missing_price_series":
                self.missing_series_fallback_count += 1
            elif lookup.fallback_reason == "before_first_price":
                self.before_series_fallback_count += 1
            if len(self.fallback_examples) < 50:
                self.fallback_examples.append(
                    {
                        "stock_code": canonical,
                        "trade_date": current_day.isoformat() if current_day else None,
                        "reason": lookup.fallback_reason,
                    }
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lookup_count": self.lookup_count,
            "current_price_count": self.current_price_count,
            "carried_forward_price_count": self.carried_forward_price_count,
            "entry_fallback_count": self.entry_fallback_count,
            "missing_series_fallback_count": self.missing_series_fallback_count,
            "before_series_fallback_count": self.before_series_fallback_count,
            "fallback_symbol_count": len(self.fallback_symbols),
            "carried_forward_symbol_count": len(self.carried_forward_symbols),
            "fallback_symbols": dict(sorted(self.fallback_symbols.items())),
            "carried_forward_symbols": dict(sorted(self.carried_forward_symbols.items())),
            "fallback_examples": self.fallback_examples,
            "carried_forward_examples": self.carried_forward_examples,
        }


def simulate_real_capital_portfolio(
    candidate_rows: list[dict[str, Any]],
    *,
    config: RealCapitalConfig | None = None,
    price_series: dict[str, dict[date, float]] | None = None,
    trading_days: list[date] | None = None,
    run_name: str | None = None,
) -> dict[str, Any]:
    """Replay ranked selected candidates under one shared cash account."""

    runtime_config = (config or RealCapitalConfig()).normalized()
    candidates = [_prepare_candidate(row) for row in candidate_rows if row.get("selected")]
    candidates = [row for row in candidates if row.get("entry_day") and row.get("exit_day")]
    candidates.sort(key=lambda row: (row["entry_day"], _sort_number(row.get("selected_order")), _sort_number(row.get("daily_candidate_rank"))))
    days = _build_trading_days(candidates, trading_days=trading_days, price_series=price_series or {})

    cash = runtime_config.initial_cash
    positions: dict[str, _AccountPosition] = {}
    opened_trades: list[dict[str, Any]] = []
    closed_trades: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    candidates_by_entry: dict[date, list[dict[str, Any]]] = {}
    mark_price_diagnostics = _MarkPriceDiagnostics()
    for row in candidates:
        candidates_by_entry.setdefault(row["entry_day"], []).append(row)

    previous_equity = runtime_config.initial_cash
    for current_day in days:
        for stock_code, position in sorted(list(positions.items()), key=lambda item: (item[1].exit_date, item[0])):
            if position.exit_date <= current_day:
                closed = _close_position(position, current_day=current_day, config=runtime_config)
                cash += float(closed["exit_cash_in"])
                closed_trades.append(closed)
                positions.pop(stock_code, None)

        equity_for_sizing = max(previous_equity, cash)
        for row in candidates_by_entry.get(current_day, []):
            stock_code = _canonical_code(row.get("stock_code"))
            if not stock_code:
                skipped.append(_skip_row(row, "missing_stock_code"))
                continue
            if stock_code in positions:
                skipped.append(_skip_row(row, "duplicate_open_position"))
                continue
            if len(positions) >= runtime_config.max_positions:
                skipped.append(_skip_row(row, "position_cap"))
                continue

            entry_price = to_float(row.get("entry_price"), default=None)
            exit_price = to_float(row.get("exit_price"), default=None)
            if entry_price is None or entry_price <= 0 or exit_price is None or exit_price <= 0:
                skipped.append(_skip_row(row, "missing_entry_or_exit_price"))
                continue

            position_size_pct = _row_position_size_pct(row, runtime_config)
            budget = min(cash, equity_for_sizing * position_size_pct)
            shares = _max_affordable_shares(
                entry_price=entry_price,
                budget=budget,
                config=runtime_config,
            )
            if shares <= 0:
                skipped.append(_skip_row(row, "insufficient_cash_or_lot"))
                continue

            entry_value = entry_price * shares
            entry_cost = _trade_cost(entry_price, shares, runtime_config, side="buy")
            entry_cash_out = entry_value + entry_cost
            if entry_cash_out > cash + 1e-8:
                skipped.append(_skip_row(row, "insufficient_cash"))
                continue

            cash -= entry_cash_out
            position = _AccountPosition(
                stock_code=stock_code,
                stock_name=row.get("stock_name"),
                trade_id=row.get("trade_id"),
                entry_date=row["entry_day"],
                exit_date=row["exit_day"],
                entry_price=entry_price,
                exit_price=exit_price,
                shares=shares,
                entry_value=entry_value,
                entry_cost=entry_cost,
                entry_cash_out=entry_cash_out,
                position_size_pct=position_size_pct,
                signal_type=row.get("signal_type"),
                rank_score=to_float(row.get("rank_score"), default=None),
                selected_order=to_int(row.get("selected_order")),
                source_row=row,
            )
            positions[stock_code] = position
            opened_trades.append(_open_payload(position))

        market_value = _market_value(
            positions,
            current_day=current_day,
            price_series=price_series or {},
            diagnostics=mark_price_diagnostics,
        )
        equity = cash + market_value
        previous_equity = equity
        equity_curve.append(
            {
                "trade_date": current_day.isoformat(),
                "cash": round(cash, 2),
                "market_value": round(market_value, 2),
                "equity": round(equity, 2),
                "open_positions": len(positions),
                "exposure_pct": round_float((market_value / equity * 100.0) if equity else 0.0),
            }
        )

    final_day = days[-1] if days else None
    open_positions = [
        _open_position_payload(
            position,
            current_day=final_day,
            price_series=price_series or {},
            diagnostics=mark_price_diagnostics,
        )
        for position in sorted(positions.values(), key=lambda item: item.stock_code)
    ]
    diagnostics = {"mark_price": mark_price_diagnostics.to_dict()}
    summary = build_real_capital_summary(
        run_name=run_name,
        config=runtime_config,
        selected_candidate_count=len(candidates),
        opened_trades=opened_trades,
        closed_trades=closed_trades,
        skipped=skipped,
        equity_curve=equity_curve,
        open_positions=open_positions,
        diagnostics=diagnostics,
    )
    return {
        "run_name": run_name,
        "config": runtime_config.to_dict(),
        "summary": summary,
        "equity_curve": equity_curve,
        "trades": closed_trades,
        "opened_trades": opened_trades,
        "skipped_candidates": skipped,
        "open_positions": open_positions,
        "diagnostics": diagnostics,
        "yearly_returns": period_returns(equity_curve, period="year", initial_cash=runtime_config.initial_cash),
        "monthly_returns": period_returns(equity_curve, period="month", initial_cash=runtime_config.initial_cash),
    }


def build_real_capital_summary(
    *,
    run_name: str | None,
    config: RealCapitalConfig,
    selected_candidate_count: int,
    opened_trades: list[dict[str, Any]],
    closed_trades: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    open_positions: list[dict[str, Any]],
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_equity = float(equity_curve[-1]["equity"]) if equity_curve else config.initial_cash
    total_return_pct = ((final_equity - config.initial_cash) / config.initial_cash * 100.0) if config.initial_cash else 0.0
    max_drawdown_pct, max_drawdown_amount = _drawdown(equity_curve)
    wins = [trade for trade in closed_trades if float(trade.get("net_pnl") or 0.0) > 0]
    losses = [trade for trade in closed_trades if float(trade.get("net_pnl") or 0.0) < 0]
    gross_profit = sum(float(trade.get("net_pnl") or 0.0) for trade in wins)
    gross_loss = abs(sum(float(trade.get("net_pnl") or 0.0) for trade in losses))
    returns = [float(trade.get("return_pct") or 0.0) for trade in closed_trades]
    exposure_values = [float(point.get("exposure_pct") or 0.0) for point in equity_curve]
    open_count_values = [int(point.get("open_positions") or 0) for point in equity_curve]
    warnings = _diagnostic_warnings(diagnostics or {})
    return {
        "run_name": run_name,
        "initial_cash": round(config.initial_cash, 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round_float(total_return_pct),
        "max_drawdown_pct": round_float(max_drawdown_pct),
        "max_drawdown_amount": round(max_drawdown_amount, 2),
        "selected_candidate_count": selected_candidate_count,
        "opened_trade_count": len(opened_trades),
        "closed_trade_count": len(closed_trades),
        "skipped_candidate_count": len(skipped),
        "open_position_count": len(open_positions),
        "win_rate_pct": round_float(len(wins) / len(closed_trades) * 100.0 if closed_trades else 0.0),
        "avg_return_pct": round_float(sum(returns) / len(returns) if returns else 0.0),
        "avg_win_pct": round_float(sum(float(trade.get("return_pct") or 0.0) for trade in wins) / len(wins) if wins else 0.0),
        "avg_loss_pct": round_float(sum(float(trade.get("return_pct") or 0.0) for trade in losses) / len(losses) if losses else 0.0),
        "profit_factor": round_float(gross_profit / gross_loss) if gross_loss else None,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_profit": round(final_equity - config.initial_cash, 2),
        "max_consecutive_losses": _max_consecutive_losses(closed_trades),
        "avg_exposure_pct": round_float(sum(exposure_values) / len(exposure_values) if exposure_values else 0.0),
        "max_exposure_pct": round_float(max(exposure_values) if exposure_values else 0.0),
        "avg_open_positions": round_float(sum(open_count_values) / len(open_count_values) if open_count_values else 0.0),
        "max_open_positions_seen": max(open_count_values) if open_count_values else 0,
        "skipped_by_reason": _count_by(skipped, "skip_reason"),
        "warnings": warnings,
        "mark_price_fallback_count": int((diagnostics or {}).get("mark_price", {}).get("entry_fallback_count") or 0),
        "mark_price_fallback_symbol_count": int((diagnostics or {}).get("mark_price", {}).get("fallback_symbol_count") or 0),
    }


def period_returns(
    equity_curve: list[dict[str, Any]],
    *,
    period: str,
    initial_cash: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_equity = float(initial_cash)
    current_key = None
    period_start_equity = previous_equity
    period_start_date = None
    latest_point = None

    for point in equity_curve:
        trade_date = parse_iso_date(point.get("trade_date"))
        if trade_date is None:
            continue
        key = trade_date.strftime("%Y") if period == "year" else trade_date.strftime("%Y-%m")
        if current_key is None:
            current_key = key
            period_start_date = trade_date
            period_start_equity = previous_equity
        elif key != current_key and latest_point is not None:
            end_equity = float(latest_point.get("equity") or previous_equity)
            rows.append(_period_row(current_key, period_start_date, parse_iso_date(latest_point.get("trade_date")), period_start_equity, end_equity))
            previous_equity = end_equity
            current_key = key
            period_start_date = trade_date
            period_start_equity = previous_equity
        latest_point = point

    if current_key is not None and latest_point is not None:
        end_equity = float(latest_point.get("equity") or previous_equity)
        rows.append(_period_row(current_key, period_start_date, parse_iso_date(latest_point.get("trade_date")), period_start_equity, end_equity))
    return rows


def load_price_series_from_duckdb(
    stock_codes: list[str],
    *,
    database_path: str | None = None,
    start_date: date,
    end_date: date,
    price_adjustment: str = "qfq",
) -> dict[str, dict[date, float]]:
    db_path = resolve_backtest_database_path(database_path)
    close_expr = "coalesce(close_qfq, close)" if str(price_adjustment or "qfq").lower() == "qfq" else "close"
    series: dict[str, dict[date, float]] = {}
    with duckdb.connect(str(db_path), read_only=True) as conn:
        for raw_code in stock_codes:
            canonical = _canonical_code(raw_code)
            if not canonical:
                continue
            rows: list[tuple[Any, Any]] = []
            for variant in build_stock_code_variants(canonical):
                result = conn.execute(
                    f"""
                    select trade_date, {close_expr} as close
                    from stock_daily_raw
                    where ts_code = ? and trade_date between ? and ? and {close_expr} is not null
                    order by trade_date
                    """,
                    (variant, start_date, end_date),
                ).fetchall()
                if result:
                    rows = result
                    break
            if rows:
                series[canonical] = {
                    _ensure_date(trade_date): float(close)
                    for trade_date, close in rows
                    if close is not None and _ensure_date(trade_date) is not None
                }
    return series


def load_trading_days_from_duckdb(
    *,
    database_path: str | None = None,
    start_date: date,
    end_date: date,
) -> list[date]:
    db_path = resolve_backtest_database_path(database_path)
    with duckdb.connect(str(db_path), read_only=True) as conn:
        rows = conn.execute(
            """
            select cal_date
            from trade_calendar
            where is_open = 1 and cal_date between ? and ?
            order by cal_date
            """,
            (start_date, end_date),
        ).fetchall()
    return [_ensure_date(row[0]) for row in rows if _ensure_date(row[0]) is not None]


def _prepare_candidate(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["stock_code"] = _canonical_code(payload.get("stock_code"))
    payload["entry_day"] = parse_iso_date(payload.get("entry_date"))
    payload["exit_day"] = parse_iso_date(payload.get("exit_date"))
    return payload


def _build_trading_days(
    candidates: list[dict[str, Any]],
    *,
    trading_days: list[date] | None,
    price_series: dict[str, dict[date, float]],
) -> list[date]:
    event_days = {
        day
        for row in candidates
        for day in (row.get("entry_day"), row.get("exit_day"))
        if isinstance(day, date)
    }
    if not event_days:
        return []
    start = min(event_days)
    end = max(event_days)
    days = [day for day in (trading_days or []) if start <= day <= end]
    if not days:
        days = sorted({day for prices in price_series.values() for day in prices if start <= day <= end} | event_days)
    else:
        days = sorted(set(days) | event_days)
    return days


def _close_position(position: _AccountPosition, *, current_day: date, config: RealCapitalConfig) -> dict[str, Any]:
    exit_value = position.exit_price * position.shares
    exit_cost = _trade_cost(position.exit_price, position.shares, config, side="sell")
    exit_cash_in = exit_value - exit_cost
    gross_pnl = exit_value - position.entry_value
    net_pnl = exit_cash_in - position.entry_cash_out
    return_pct = (net_pnl / position.entry_value * 100.0) if position.entry_value else 0.0
    row = position.source_row
    return {
        "trade_id": position.trade_id,
        "stock_code": position.stock_code,
        "stock_name": position.stock_name,
        "entry_date": position.entry_date.isoformat(),
        "exit_date": position.exit_date.isoformat(),
        "account_exit_date": current_day.isoformat(),
        "entry_price": round(position.entry_price, 4),
        "exit_price": round(position.exit_price, 4),
        "shares": position.shares,
        "position_size_pct": round_float(position.position_size_pct),
        "entry_value": round(position.entry_value, 2),
        "exit_value": round(exit_value, 2),
        "entry_cost": round(position.entry_cost, 2),
        "exit_cost": round(exit_cost, 2),
        "total_cost": round(position.entry_cost + exit_cost, 2),
        "entry_cash_out": round(position.entry_cash_out, 2),
        "exit_cash_in": round(exit_cash_in, 2),
        "gross_pnl": round(gross_pnl, 2),
        "net_pnl": round(net_pnl, 2),
        "return_pct": round_float(return_pct),
        "source_return_pct": row.get("return_pct"),
        "holding_days": max(0, (position.exit_date - position.entry_date).days),
        "exit_reason": row.get("exit_reason"),
        "signal_type": position.signal_type,
        "rank_score": position.rank_score,
        "selected_order": position.selected_order,
        "entry_signal_score": row.get("entry_signal_score"),
        "max_favorable_excursion_pct": row.get("max_favorable_excursion_pct"),
        "max_adverse_excursion_pct": row.get("max_adverse_excursion_pct"),
    }


def _open_payload(position: _AccountPosition) -> dict[str, Any]:
    return {
        "trade_id": position.trade_id,
        "stock_code": position.stock_code,
        "stock_name": position.stock_name,
        "entry_date": position.entry_date.isoformat(),
        "planned_exit_date": position.exit_date.isoformat(),
        "entry_price": round(position.entry_price, 4),
        "exit_price": round(position.exit_price, 4),
        "shares": position.shares,
        "position_size_pct": round_float(position.position_size_pct),
        "entry_value": round(position.entry_value, 2),
        "entry_cost": round(position.entry_cost, 2),
        "entry_cash_out": round(position.entry_cash_out, 2),
        "signal_type": position.signal_type,
        "rank_score": position.rank_score,
        "selected_order": position.selected_order,
    }


def _open_position_payload(
    position: _AccountPosition,
    *,
    current_day: date | None,
    price_series: dict[str, dict[date, float]],
    diagnostics: _MarkPriceDiagnostics | None = None,
) -> dict[str, Any]:
    mark_price = _mark_price(
        position.stock_code,
        current_day,
        price_series,
        fallback=position.entry_price,
        diagnostics=diagnostics,
    )
    market_value = mark_price * position.shares
    unrealized_pnl = market_value - position.entry_cash_out
    return {
        **_open_payload(position),
        "mark_date": current_day.isoformat() if current_day else None,
        "mark_price": round(mark_price, 4),
        "market_value": round(market_value, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
    }


def _skip_row(row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "skip_reason": reason,
        "trade_id": row.get("trade_id"),
        "stock_code": row.get("stock_code"),
        "stock_name": row.get("stock_name"),
        "entry_date": row.get("entry_date"),
        "exit_date": row.get("exit_date"),
        "signal_type": row.get("signal_type"),
        "rank_score": row.get("rank_score"),
        "selected_order": row.get("selected_order"),
        "daily_candidate_rank": row.get("daily_candidate_rank"),
        "position_size_pct": row.get("position_size_pct"),
        "return_pct": row.get("return_pct"),
    }


def _market_value(
    positions: dict[str, _AccountPosition],
    *,
    current_day: date,
    price_series: dict[str, dict[date, float]],
    diagnostics: _MarkPriceDiagnostics | None = None,
) -> float:
    total = 0.0
    for position in positions.values():
        price = _mark_price(
            position.stock_code,
            current_day,
            price_series,
            fallback=position.entry_price,
            diagnostics=diagnostics,
        )
        total += price * position.shares
    return total


def _mark_price(
    stock_code: str,
    current_day: date | None,
    price_series: dict[str, dict[date, float]],
    *,
    fallback: float,
    diagnostics: _MarkPriceDiagnostics | None = None,
) -> float:
    lookup = _mark_price_lookup(stock_code, current_day, price_series, fallback=fallback)
    if diagnostics is not None:
        diagnostics.record(stock_code, current_day, lookup)
    return lookup.price


def _mark_price_lookup(
    stock_code: str,
    current_day: date | None,
    price_series: dict[str, dict[date, float]],
    *,
    fallback: float,
) -> _MarkPriceLookup:
    if current_day is None:
        return _MarkPriceLookup(float(fallback), source="entry_fallback", fallback_reason="missing_trade_date")
    series = price_series.get(_canonical_code(stock_code)) or {}
    if current_day in series:
        return _MarkPriceLookup(float(series[current_day]), source="current", source_date=current_day)
    if not series:
        return _MarkPriceLookup(float(fallback), source="entry_fallback", fallback_reason="missing_price_series")
    days = sorted(series)
    index = bisect.bisect_right(days, current_day) - 1
    if index >= 0:
        source_day = days[index]
        return _MarkPriceLookup(float(series[source_day]), source="carry_forward", source_date=source_day)
    return _MarkPriceLookup(float(fallback), source="entry_fallback", fallback_reason="before_first_price")


def _max_affordable_shares(*, entry_price: float, budget: float, config: RealCapitalConfig) -> int:
    if entry_price <= 0 or budget <= 0:
        return 0
    lot_size = max(1, int(config.lot_size))
    shares = int(budget // entry_price)
    shares = (shares // lot_size) * lot_size
    while shares > 0:
        cash_needed = entry_price * shares + _trade_cost(entry_price, shares, config, side="buy")
        if cash_needed <= budget + 1e-8:
            return shares
        shares -= lot_size
    return 0


def _row_position_size_pct(row: dict[str, Any], config: RealCapitalConfig) -> float:
    value = to_float(row.get("position_size_pct"), default=config.position_size_pct)
    if value is None:
        value = config.position_size_pct
    return max(0.0, min(1.0, float(value)))


def _trade_cost(price: float, shares: int, config: RealCapitalConfig, *, side: str) -> float:
    turnover = max(0.0, float(price) * int(shares))
    if turnover <= 0:
        return 0.0
    commission = max(turnover * (config.commission_bps / 10000.0), config.min_commission) if config.commission_bps > 0 else 0.0
    transfer_fee = turnover * (config.transfer_fee_bps / 10000.0) if config.transfer_fee_bps > 0 else 0.0
    stamp_tax = turnover * (config.stamp_tax_bps / 10000.0) if str(side).lower() == "sell" else 0.0
    return commission + transfer_fee + stamp_tax


def _drawdown(equity_curve: list[dict[str, Any]]) -> tuple[float, float]:
    peak = None
    max_pct = 0.0
    max_amount = 0.0
    for point in equity_curve:
        equity = float(point.get("equity") or 0.0)
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > 0:
            amount = peak - equity
            pct = amount / peak * 100.0
            if pct > max_pct:
                max_pct = pct
                max_amount = amount
    return max_pct, max_amount


def _max_consecutive_losses(trades: list[dict[str, Any]]) -> int:
    current = 0
    max_losses = 0
    for trade in sorted(trades, key=lambda row: (str(row.get("exit_date")), str(row.get("stock_code")))):
        if float(trade.get("net_pnl") or 0.0) < 0:
            current += 1
            max_losses = max(max_losses, current)
        else:
            current = 0
    return max_losses


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _period_row(
    period_key: str,
    start_date: date | None,
    end_date: date | None,
    start_equity: float,
    end_equity: float,
) -> dict[str, Any]:
    return {
        "period": period_key,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "start_equity": round(start_equity, 2),
        "end_equity": round(end_equity, 2),
        "return_pct": round_float(((end_equity - start_equity) / start_equity * 100.0) if start_equity else 0.0),
    }


def _diagnostic_warnings(diagnostics: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    mark_price = diagnostics.get("mark_price") or {}
    fallback_count = int(mark_price.get("entry_fallback_count") or 0)
    fallback_symbol_count = int(mark_price.get("fallback_symbol_count") or 0)
    if fallback_count:
        warnings.append(
            "mark_price_entry_fallback:"
            f" {fallback_count} valuation points across {fallback_symbol_count} symbols used entry_price;"
            " in-period market_value/equity/max_drawdown may be overly smooth"
        )
    return warnings


def _canonical_code(value: Any) -> str:
    text = canonicalize_stock_code(str(value or "").strip())
    if "." in text:
        return text.split(".", 1)[0]
    return text


def _ensure_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date") and not isinstance(value, str):
        return value.date()
    return parse_iso_date(value)


def _sort_number(value: Any) -> int:
    parsed = to_int(value)
    return parsed if parsed is not None else 1_000_000


def dumps_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
