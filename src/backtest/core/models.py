# -*- coding: utf-8 -*-
"""Data models for the minimal backtest loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class BacktestConfig:
    initial_cash: float = 100000.0
    commission_bps: float = 10.0
    slippage_bps: float = 10.0
    lot_size: int = 100
    min_commission: float = 5.0
    stamp_tax_bps: float = 5.0
    transfer_fee_bps: float = 0.1
    price_adjustment: str = "raw"
    trading_constraint_mode: str = "legacy_pct"
    allow_limit_up_entry: bool = False
    block_limit_down_exit: bool = True
    enforce_t_plus_one: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Position:
    stock_code: str
    entry_date: date
    entry_price: float
    shares: int
    highest_price_seen: float
    lowest_price_seen: float
    entry_execution_price: float | None = None
    entry_cost: float | None = None
    entry_commission: float | None = None
    entry_stamp_tax: float | None = None
    entry_transfer_fee: float | None = None
    entry_slippage: float | None = None
    entry_signal_reason: str = ""
    entry_signal_score: float | None = None
    entry_signal_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["entry_date"] = self.entry_date.isoformat()
        return payload


@dataclass(slots=True)
class Trade:
    stock_code: str
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    shares: int
    gross_pnl: float
    net_pnl: float
    return_pct: float
    holding_days: int
    exit_reason: str
    entry_cost: float = 0.0
    exit_cost: float = 0.0
    total_cost: float = 0.0
    entry_commission: float = 0.0
    exit_commission: float = 0.0
    entry_stamp_tax: float = 0.0
    exit_stamp_tax: float = 0.0
    entry_transfer_fee: float = 0.0
    exit_transfer_fee: float = 0.0
    entry_slippage: float = 0.0
    exit_slippage: float = 0.0
    entry_signal_reason: str = ""
    entry_signal_score: float | None = None
    entry_signal_metadata: Dict[str, Any] = field(default_factory=dict)
    highest_price_seen: float | None = None
    lowest_price_seen: float | None = None
    max_favorable_excursion_pct: float | None = None
    max_adverse_excursion_pct: float | None = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["entry_date"] = self.entry_date.isoformat()
        payload["exit_date"] = self.exit_date.isoformat()
        return payload


@dataclass(slots=True)
class EquityPoint:
    trade_date: date
    cash: float
    market_value: float
    equity: float

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["trade_date"] = self.trade_date.isoformat()
        return payload


@dataclass(slots=True)
class BacktestResult:
    strategy_name: str
    stock_code: str
    start_date: str
    end_date: str
    config: Dict[str, Any]
    params: Dict[str, Any]
    metrics: Dict[str, Any]
    data_context: Dict[str, Any] = field(default_factory=dict)
    open_position: Optional[Position] = None
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[EquityPoint] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "stock_code": self.stock_code,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "config": self.config,
            "params": self.params,
            "metrics": self.metrics,
            "data_context": self.data_context,
            "open_position": self.open_position.to_dict() if self.open_position is not None else None,
            "trades": [item.to_dict() for item in self.trades],
            "equity_curve": [item.to_dict() for item in self.equity_curve],
            "notes": list(self.notes),
        }
