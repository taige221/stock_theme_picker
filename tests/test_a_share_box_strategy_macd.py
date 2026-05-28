# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from theme_picker.strategy.a_share_box_strategy import AShareBoxStrategy
from theme_picker.strategy.params import StrategyParams


def _pullback_macd_frame(*, latest_low: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": "2024-01-01", "high": 10.5, "low": 9.8, "macd_dif": -0.20, "macd_hist": -0.10},
            {"date": "2024-01-02", "high": 10.2, "low": 9.2, "macd_dif": -0.35, "macd_hist": -0.25},
            {"date": "2024-01-03", "high": 9.5, "low": 8.0, "macd_dif": -0.60, "macd_hist": -0.45},
            {"date": "2024-01-04", "high": 10.0, "low": 8.7, "macd_dif": -0.50, "macd_hist": -0.35},
            {"date": "2024-01-05", "high": 10.4, "low": 9.0, "macd_dif": -0.45, "macd_hist": -0.30},
            {
                "date": "2024-01-06",
                "high": 10.8,
                "low": latest_low,
                "macd_dif": -0.30,
                "macd_hist": -0.10,
                "macd_hist_slope_3": 0.20,
            },
        ]
    )


def _macd_divergence_params() -> StrategyParams:
    return StrategyParams(
        enable_macd_divergence_decision=True,
        macd_divergence_lookback_days=20,
        macd_divergence_price_tolerance_pct=0.003,
    )


def test_pullback_macd_bullish_divergence_requires_price_near_prior_low() -> None:
    result = AShareBoxStrategy()._detect_macd_divergence(
        working=_pullback_macd_frame(latest_low=8.5),
        signal_type="pullback_bounce",
        volume_ratio=1.0,
        params=_macd_divergence_params(),
    )

    assert result["macd_divergence_price_confirms"] is False
    assert result["pullback_macd_bullish_divergence"] is False
    assert result["macd_divergence_detected"] is False


def test_pullback_macd_bullish_divergence_allows_price_inside_tolerance() -> None:
    result = AShareBoxStrategy()._detect_macd_divergence(
        working=_pullback_macd_frame(latest_low=8.02),
        signal_type="pullback_bounce",
        volume_ratio=1.0,
        params=_macd_divergence_params(),
    )

    assert result["macd_divergence_price_confirms"] is True
    assert result["pullback_macd_bullish_divergence"] is True
    assert result["macd_divergence_detected"] is True
    assert result["macd_divergence_reference_price"] == 8.0
