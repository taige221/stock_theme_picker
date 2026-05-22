# -*- coding: utf-8 -*-
"""Starter A-share strategy adapted from crypto-style trend logic."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from theme_picker.strategy.base import Strategy, StrategySignal
from theme_picker.strategy.params import StrategyParams


class AShareMigratedCryptoStrategy(Strategy):
    """Simple breakout-plus-risk-control starter strategy.

    This is intentionally conservative for A-shares:
    - entry requires breakout and volume confirmation
    - exit uses stop loss / take profit / timeout / MA10 failure
    """

    name = "a_share_migrated_crypto"

    def generate_signal(
        self,
        history: pd.DataFrame,
        *,
        current_index: Optional[int] = None,
        params: StrategyParams,
        price_adjustment: str,
        has_position: bool,
        entry_price: Optional[float],
        holding_days: int,
    ) -> StrategySignal:
        min_required = max(20, params.breakout_lookback_days + 1)
        available_rows = (int(current_index) + 1) if current_index is not None else len(history)
        if history is None or history.empty or available_rows < min_required:
            return StrategySignal(
                action="hold",
                reason="history_not_ready",
                metadata={"price_adjustment": price_adjustment},
            )

        lookback_rows = max(min_required, int(params.breakout_lookback_days) + 20)
        if current_index is None:
            working = history.copy().sort_values("date").reset_index(drop=True)
        else:
            start_index = max(0, int(current_index) - lookback_rows + 1)
            working = history.iloc[start_index : int(current_index) + 1].copy().reset_index(drop=True)

        if "ma10" not in working.columns:
            working["ma10"] = pd.to_numeric(working["close"], errors="coerce").rolling(10, min_periods=1).mean()
        if "volume_ratio" not in working.columns:
            volume = pd.to_numeric(working["volume"], errors="coerce")
            avg_volume_5 = volume.rolling(5, min_periods=1).mean().shift(1)
            working["volume_ratio"] = (volume / avg_volume_5).replace([float("inf"), float("-inf")], pd.NA).fillna(1.0)
        if "pct_chg" not in working.columns:
            close = pd.to_numeric(working["close"], errors="coerce")
            working["pct_chg"] = close.pct_change().fillna(0.0) * 100.0

        latest = working.iloc[-1]
        close_price = self._to_float(latest.get("close"))
        ma10 = self._to_float(latest.get("ma10"))
        pct_chg = self._to_float(latest.get("pct_chg")) or 0.0
        volume_ratio = self._to_float(latest.get("volume_ratio")) or 0.0

        if close_price is None or ma10 is None:
            return StrategySignal(
                action="hold",
                reason="missing_price_context",
                metadata={"price_adjustment": price_adjustment},
            )

        if has_position and entry_price:
            pnl_pct = (close_price - entry_price) / entry_price
            if pnl_pct <= -abs(params.stop_loss_pct):
                return StrategySignal(
                    action="sell",
                    reason="stop_loss_hit",
                    score=pnl_pct,
                    metadata={
                        "price_adjustment": price_adjustment,
                        "close_price": close_price,
                        "entry_price": entry_price,
                    },
                )
            if pnl_pct >= abs(params.take_profit_pct):
                return StrategySignal(
                    action="sell",
                    reason="take_profit_hit",
                    score=pnl_pct,
                    metadata={
                        "price_adjustment": price_adjustment,
                        "close_price": close_price,
                        "entry_price": entry_price,
                    },
                )
            if holding_days >= int(params.max_holding_days):
                return StrategySignal(
                    action="sell",
                    reason="max_holding_days_reached",
                    score=pnl_pct,
                    metadata={
                        "price_adjustment": price_adjustment,
                        "close_price": close_price,
                        "entry_price": entry_price,
                    },
                )
            if close_price < ma10:
                return StrategySignal(
                    action="sell",
                    reason="close_below_ma10",
                    score=pnl_pct,
                    metadata={
                        "price_adjustment": price_adjustment,
                        "close_price": close_price,
                        "ma10": ma10,
                    },
                )
            return StrategySignal(
                action="hold",
                reason="holding",
                metadata={"price_adjustment": price_adjustment},
            )

        lookback = min(int(params.breakout_lookback_days), len(working) - 1)
        recent_high = self._to_float(
            pd.to_numeric(working["high"].iloc[-(lookback + 1):-1], errors="coerce").max()
        )
        if recent_high is None:
            return StrategySignal(
                action="hold",
                reason="missing_recent_high",
                metadata={"price_adjustment": price_adjustment},
            )

        bias_ma10_pct = ((close_price - ma10) / ma10 * 100.0) if ma10 else None
        breakout_confirmed = close_price >= recent_high
        momentum_confirmed = pct_chg >= float(params.min_breakout_pct)
        volume_confirmed = volume_ratio >= float(params.min_volume_ratio)
        bias_ok = bias_ma10_pct is None or bias_ma10_pct <= float(params.max_bias_ma10_pct)

        if breakout_confirmed and momentum_confirmed and volume_confirmed and bias_ok:
            return StrategySignal(
                action="buy",
                reason="breakout_volume_confirmed",
                score=pct_chg,
                metadata={
                    "price_adjustment": price_adjustment,
                    "close_price": close_price,
                    "ma10": ma10,
                    "recent_high": recent_high,
                    "pct_chg": pct_chg,
                    "volume_ratio": volume_ratio,
                    "bias_ma10_pct": bias_ma10_pct,
                },
            )
        return StrategySignal(
            action="hold",
            reason="entry_not_ready",
            metadata={
                "price_adjustment": price_adjustment,
                "close_price": close_price,
                "recent_high": recent_high,
            },
        )

    @staticmethod
    def _to_float(value) -> Optional[float]:
        if value is None or value is pd.NA:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
