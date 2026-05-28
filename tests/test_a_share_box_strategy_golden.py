# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from theme_picker.strategy.a_share_box import AShareBoxStrategy
from theme_picker.strategy.params import StrategyParams


def _golden_params() -> StrategyParams:
    return StrategyParams(
        box_lookback_days=10,
        min_breakout_pct=2.0,
        min_volume_ratio=1.0,
        min_turnover_rate=0.0,
        min_box_touches=2,
        breakout_min_body_pct=0.0,
        breakout_min_close_above_resistance_pct=0.0,
        breakout_max_upper_shadow_ratio=1.0,
        max_breakout_extension_pct=0.06,
        pullback_min_volume_ratio=1.0,
        pullback_min_box_touches=2,
        pullback_reclaim_pct=0.003,
        breakout_retest_window=4,
        min_box_height_pct=0.0,
        signal_number_lookback_days=40,
        pullback_profit_power_lookback_days=20,
        pullback_profit_power_rolling_gain_days=5,
        stop_loss_pct=0.04,
    )


def _bar(index: int, *, open_: float, high: float, low: float, close: float, pct_chg: float = 0.0) -> dict:
    trade_date = date(2024, 1, 1) + timedelta(days=index)
    return {
        "date": trade_date.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000000,
        "volume_ratio": 1.5,
        "turnover_rate": 5.0,
        "pct_chg": pct_chg,
        "ma10": 11.0,
    }


def _box_history(latest: dict) -> pd.DataFrame:
    rows: list[dict] = []
    for idx in range(30):
        rows.append(_bar(idx, open_=9.6, high=10.5, low=8.5, close=9.7))
    for idx in range(30, 40):
        rows.append(_bar(idx, open_=10.0, high=11.0, low=9.0, close=10.4))
    for idx in range(40, 49):
        rows.append(_bar(idx, open_=11.2, high=12.0, low=10.0, close=11.7))
    rows.append(latest)
    return pd.DataFrame(rows)


def test_a_share_box_returns_history_not_ready_before_minimum_window() -> None:
    signal = AShareBoxStrategy().generate_signal(
        pd.DataFrame([_bar(idx, open_=10.0, high=10.5, low=9.5, close=10.1) for idx in range(12)]),
        params=_golden_params(),
        price_adjustment="qfq",
        has_position=False,
        entry_price=None,
        holding_days=0,
    )

    assert signal.action == "hold"
    assert signal.reason == "history_not_ready"


def test_a_share_box_breakout_golden_sample_buys() -> None:
    signal = AShareBoxStrategy().generate_signal(
        _box_history(_bar(49, open_=12.1, high=12.8, low=11.9, close=12.6, pct_chg=4.0)),
        params=_golden_params(),
        price_adjustment="qfq",
        has_position=False,
        entry_price=None,
        holding_days=0,
    )

    assert signal.action == "buy"
    assert signal.reason == "breakout_long"
    assert signal.metadata["signal_type"] == "breakout_long"
    assert signal.metadata["trend"] == "uptrend"


def test_a_share_box_rejects_overextended_breakout_golden_sample() -> None:
    signal = AShareBoxStrategy().generate_signal(
        _box_history(_bar(49, open_=13.1, high=13.7, low=13.0, close=13.5, pct_chg=7.0)),
        params=_golden_params(),
        price_adjustment="qfq",
        has_position=False,
        entry_price=None,
        holding_days=0,
    )

    assert signal.action == "hold"
    assert signal.reason == "entry_not_ready"


def test_a_share_box_pullback_golden_sample_buys() -> None:
    signal = AShareBoxStrategy().generate_signal(
        _box_history(_bar(49, open_=12.0, high=12.3, low=11.95, close=12.12, pct_chg=0.6)),
        params=_golden_params(),
        price_adjustment="qfq",
        has_position=False,
        entry_price=None,
        holding_days=0,
    )

    assert signal.action == "buy"
    assert signal.reason == "pullback_bounce"
    assert signal.metadata["signal_type"] == "pullback_bounce"
    assert signal.metadata["touched_zone"] is True
    assert signal.metadata["reclaimed"] is True


def test_a_share_box_stop_loss_has_exit_priority() -> None:
    signal = AShareBoxStrategy().generate_signal(
        _box_history(_bar(49, open_=11.7, high=11.8, low=11.3, close=11.4, pct_chg=-3.5)),
        params=_golden_params(),
        price_adjustment="qfq",
        has_position=True,
        entry_price=12.0,
        holding_days=2,
        entry_signal_reason="breakout_long",
    )

    assert signal.action == "sell"
    assert signal.reason == "stop_loss_hit"
