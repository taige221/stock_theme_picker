# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import date

from theme_picker.backtest.analysis.real_capital import RealCapitalConfig, simulate_real_capital_portfolio


def _candidate(
    stock_code: str,
    *,
    entry_date: str,
    exit_date: str,
    entry_price: float,
    exit_price: float,
    selected_order: int,
) -> dict:
    return {
        "selected": True,
        "stock_code": stock_code,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "signal_type": "pullback_bounce",
        "rank_score": 90.0,
        "selected_order": selected_order,
        "daily_candidate_rank": selected_order,
        "return_pct": (exit_price - entry_price) / entry_price * 100.0,
    }


def test_real_capital_simulation_enforces_cash_and_lot() -> None:
    result = simulate_real_capital_portfolio(
        [
            _candidate("000001", entry_date="2024-01-02", exit_date="2024-01-04", entry_price=50.0, exit_price=55.0, selected_order=1),
            _candidate("000002", entry_date="2024-01-02", exit_date="2024-01-04", entry_price=60.0, exit_price=66.0, selected_order=2),
        ],
        config=RealCapitalConfig(
            initial_cash=10_000.0,
            position_size_pct=0.5,
            max_positions=2,
            lot_size=100,
            commission_bps=0.0,
            min_commission=0.0,
            stamp_tax_bps=0.0,
            transfer_fee_bps=0.0,
        ),
        price_series={
            "000001": {date(2024, 1, 2): 50.0, date(2024, 1, 3): 45.0, date(2024, 1, 4): 55.0},
            "000002": {date(2024, 1, 2): 60.0, date(2024, 1, 3): 62.0, date(2024, 1, 4): 66.0},
        },
        trading_days=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
    )

    assert result["summary"]["opened_trade_count"] == 1
    assert result["summary"]["closed_trade_count"] == 1
    assert result["summary"]["skipped_candidate_count"] == 1
    assert result["summary"]["skipped_by_reason"] == {"insufficient_cash_or_lot": 1}
    assert result["summary"]["final_equity"] == 10500.0
    assert result["summary"]["total_return_pct"] == 5.0
    assert result["summary"]["max_drawdown_pct"] == 5.0


def test_real_capital_simulation_enforces_position_cap() -> None:
    result = simulate_real_capital_portfolio(
        [
            _candidate("000001", entry_date="2024-01-02", exit_date="2024-01-05", entry_price=10.0, exit_price=11.0, selected_order=1),
            _candidate("000002", entry_date="2024-01-03", exit_date="2024-01-05", entry_price=10.0, exit_price=11.0, selected_order=2),
        ],
        config=RealCapitalConfig(
            initial_cash=100_000.0,
            position_size_pct=0.1,
            max_positions=1,
            lot_size=100,
            commission_bps=0.0,
            min_commission=0.0,
            stamp_tax_bps=0.0,
            transfer_fee_bps=0.0,
        ),
        price_series={
            "000001": {date(2024, 1, 2): 10.0, date(2024, 1, 3): 10.0, date(2024, 1, 5): 11.0},
            "000002": {date(2024, 1, 3): 10.0, date(2024, 1, 5): 11.0},
        },
        trading_days=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)],
    )

    assert result["summary"]["opened_trade_count"] == 1
    assert result["summary"]["skipped_by_reason"] == {"position_cap": 1}


def test_real_capital_simulation_reports_entry_price_mark_fallback() -> None:
    result = simulate_real_capital_portfolio(
        [
            _candidate("000001", entry_date="2024-01-02", exit_date="2024-01-04", entry_price=10.0, exit_price=12.0, selected_order=1),
        ],
        config=RealCapitalConfig(
            initial_cash=100_000.0,
            position_size_pct=0.1,
            max_positions=1,
            lot_size=100,
            commission_bps=0.0,
            min_commission=0.0,
            stamp_tax_bps=0.0,
            transfer_fee_bps=0.0,
        ),
        price_series={},
        trading_days=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
    )

    mark_price = result["diagnostics"]["mark_price"]
    assert result["summary"]["closed_trade_count"] == 1
    assert result["summary"]["final_equity"] == 102000.0
    assert result["summary"]["mark_price_fallback_count"] == 2
    assert result["summary"]["mark_price_fallback_symbol_count"] == 1
    assert result["summary"]["warnings"] == [
        "mark_price_entry_fallback: 2 valuation points across 1 symbols used entry_price; in-period market_value/equity/max_drawdown may be overly smooth"
    ]
    assert mark_price["entry_fallback_count"] == 2
    assert mark_price["missing_series_fallback_count"] == 2
    assert mark_price["fallback_symbols"] == {"000001": 2}


def test_real_capital_simulation_uses_candidate_position_size_override() -> None:
    candidate = _candidate(
        "000001",
        entry_date="2024-01-02",
        exit_date="2024-01-04",
        entry_price=10.0,
        exit_price=11.0,
        selected_order=1,
    )
    candidate["position_size_pct"] = 0.2
    result = simulate_real_capital_portfolio(
        [candidate],
        config=RealCapitalConfig(
            initial_cash=10_000.0,
            position_size_pct=1.0,
            max_positions=1,
            lot_size=100,
            commission_bps=0.0,
            min_commission=0.0,
            stamp_tax_bps=0.0,
            transfer_fee_bps=0.0,
        ),
        price_series={
            "000001": {date(2024, 1, 2): 10.0, date(2024, 1, 3): 10.5, date(2024, 1, 4): 11.0},
        },
        trading_days=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
    )

    assert result["opened_trades"][0]["position_size_pct"] == 0.2
    assert result["opened_trades"][0]["shares"] == 200
    assert result["opened_trades"][0]["entry_value"] == 2000.0
    assert result["summary"]["final_equity"] == 10200.0
