# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from theme_picker.backtest.core.engine import BacktestEngine
from theme_picker.strategy.a_share_box import AShareBoxStrategy
from theme_picker.strategy.a_share_box.strategy import BoxSnapshot
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


def _box_history_with_prior_breakout(latest: dict) -> pd.DataFrame:
    rows: list[dict] = []
    for idx in range(30):
        rows.append(_bar(idx, open_=9.6, high=10.5, low=8.5, close=9.7))
    for idx in range(30, 40):
        rows.append(_bar(idx, open_=10.0, high=11.0, low=9.0, close=10.4))
    for idx in range(40, 48):
        rows.append(_bar(idx, open_=11.2, high=12.0, low=10.0, close=11.7))
    rows.append(_bar(48, open_=11.9, high=12.55, low=11.85, close=12.35, pct_chg=3.4))
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
        _box_history_with_prior_breakout(
            _bar(49, open_=12.0, high=12.25, low=11.95, close=12.12, pct_chg=-1.8)
        ),
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
    assert signal.metadata["prior_breakout_required"] is True
    assert signal.metadata["pullback_pattern"] == "breakout_retest"
    assert signal.metadata["prior_breakout_date"] == "2024-02-18"
    assert signal.metadata["pullback_reference_resistance"] == 12.0


def test_a_share_box_labels_same_bar_box_reclaim_without_prior_breakout() -> None:
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
    assert signal.metadata["pullback_pattern"] == "box_reclaim"
    assert signal.metadata["prior_breakout_required"] is False
    assert signal.metadata["prior_breakout_date"] is None
    assert signal.metadata["pullback_reference_resistance"] == 12.0


def test_a_share_box_pullback_requires_confirmed_prior_breakout() -> None:
    rows = _box_history_with_prior_breakout(
        _bar(49, open_=12.0, high=12.25, low=11.95, close=12.12, pct_chg=-1.8)
    )
    rows.loc[48, "volume_ratio"] = 0.4

    signal = AShareBoxStrategy().generate_signal(
        rows,
        params=_golden_params(),
        price_adjustment="qfq",
        has_position=False,
        entry_price=None,
        holding_days=0,
    )

    assert signal.action == "hold"
    assert signal.reason == "entry_not_ready"


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


def test_a_share_box_stop_loss_has_priority_over_breakeven_stop() -> None:
    params = _golden_params()
    params.breakout_enable_breakeven_stop = True
    params.breakeven_activate_profit_pct = 0.03
    params.breakeven_exit_threshold_pct = 0.005

    signal = AShareBoxStrategy().generate_signal(
        _box_history(_bar(49, open_=11.7, high=11.8, low=11.3, close=11.4, pct_chg=-3.5)),
        params=params,
        price_adjustment="qfq",
        has_position=True,
        entry_price=12.0,
        holding_days=4,
        entry_signal_reason="breakout_long",
        position_highest_price_seen=12.6,
    )

    assert signal.action == "sell"
    assert signal.reason == "stop_loss_hit"


def test_a_share_box_pullback_failure_uses_entry_reference_resistance() -> None:
    strategy = AShareBoxStrategy()
    params = _golden_params()
    params.pullback_enable_failure_exit = True
    params.pullback_failure_buffer_pct = 0.003

    signal = strategy._detect_pullback_failure_exit(
        working=pd.DataFrame([_bar(50, open_=12.6, high=12.7, low=12.4, close=12.5)]),
        params=params,
        entry_signal_reason="pullback_bounce",
        entry_signal_metadata={
            "box_resistance": 13.0,
            "pullback_reference_resistance": 12.0,
        },
        current_box=BoxSnapshot(
            support=10.0,
            resistance=13.0,
            height=3.0,
            support_touches=2,
            resistance_touches=3,
        ),
        close_price=12.5,
        pnl_pct=-0.01,
        holding_days=1,
    )

    assert signal is None


def test_a_share_box_breakout_retest_failure_uses_retest_window() -> None:
    strategy = AShareBoxStrategy()
    params = _golden_params()
    params.pullback_enable_failure_exit = True
    params.pullback_failure_exit_days = 1
    params.breakout_retest_window = 4

    common_kwargs = {
        "working": pd.DataFrame([_bar(50, open_=11.95, high=12.0, low=11.6, close=11.8)]),
        "params": params,
        "entry_signal_reason": "pullback_bounce",
        "current_box": BoxSnapshot(
            support=10.0,
            resistance=12.0,
            height=2.0,
            support_touches=2,
            resistance_touches=3,
        ),
        "close_price": 11.8,
        "pnl_pct": -0.02,
        "holding_days": 3,
    }

    box_reclaim_signal = strategy._detect_pullback_failure_exit(
        entry_signal_metadata={
            "pullback_pattern": "box_reclaim",
            "pullback_reference_resistance": 12.0,
        },
        **common_kwargs,
    )
    breakout_retest_signal = strategy._detect_pullback_failure_exit(
        entry_signal_metadata={
            "pullback_pattern": "breakout_retest",
            "pullback_reference_resistance": 12.0,
        },
        **common_kwargs,
    )

    assert box_reclaim_signal is None
    assert breakout_retest_signal is not None
    assert breakout_retest_signal["pullback_failure_exit_days"] == 4
    assert breakout_retest_signal["pullback_failure_exit_window_source"] == "breakout_retest_window"


def test_a_share_box_pullback_failure_has_priority_over_entry_stall() -> None:
    params = _golden_params()
    params.pullback_enable_entry_stall_exit = True
    params.pullback_entry_stall_days = 3
    params.pullback_entry_stall_min_return_pct = 0.01
    params.pullback_enable_failure_exit = True
    params.pullback_failure_exit_days = 1
    params.breakout_retest_window = 4

    signal = AShareBoxStrategy().generate_signal(
        _box_history(_bar(49, open_=11.9, high=12.0, low=11.6, close=11.8, pct_chg=-1.0)),
        params=params,
        price_adjustment="qfq",
        has_position=True,
        entry_price=12.1,
        holding_days=3,
        entry_signal_reason="pullback_bounce",
        entry_signal_metadata={
            "pullback_pattern": "breakout_retest",
            "pullback_reference_resistance": 12.0,
        },
    )

    assert signal.action == "sell"
    assert signal.reason == "pullback_failure_exit"
    assert signal.metadata["pullback_failure_exit_window_source"] == "breakout_retest_window"


def test_a_share_box_box_reclaim_keeps_breakeven_priority() -> None:
    params = _golden_params()
    params.enable_breakeven_stop = True
    params.breakeven_activate_profit_pct = 0.03
    params.breakeven_exit_threshold_pct = 0.005
    params.pullback_enable_failure_exit = True
    params.pullback_failure_exit_days = 4

    signal = AShareBoxStrategy().generate_signal(
        _box_history(_bar(49, open_=11.9, high=12.0, low=11.6, close=11.8, pct_chg=-1.0)),
        params=params,
        price_adjustment="qfq",
        has_position=True,
        entry_price=12.1,
        holding_days=1,
        entry_signal_reason="pullback_bounce",
        entry_signal_metadata={
            "pullback_pattern": "box_reclaim",
            "pullback_reference_resistance": 12.0,
        },
        position_highest_price_seen=12.5,
    )

    assert signal.action == "sell"
    assert signal.reason == "breakeven_stop"


def test_backtest_engine_keeps_pullback_reference_in_entry_snapshot() -> None:
    snapshot = BacktestEngine._build_entry_signal_snapshot(
        {
            "signal_type": "pullback_bounce",
            "pullback_pattern": "breakout_retest",
            "pullback_reference_resistance": 12.0,
            "pullback_reference_support": 10.0,
            "pullback_reference_resistance_touches": 3,
            "prior_breakout_required": True,
            "prior_breakout_date": "2024-02-18",
            "prior_breakout_close": 12.35,
        }
    )

    assert snapshot["pullback_pattern"] == "breakout_retest"
    assert snapshot["pullback_reference_resistance"] == 12.0
    assert snapshot["prior_breakout_required"] is True
    assert snapshot["prior_breakout_date"] == "2024-02-18"
