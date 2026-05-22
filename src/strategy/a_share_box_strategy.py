# -*- coding: utf-8 -*-
"""A-share box-stacking strategy adapted from the user's price-action playbook."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

from theme_picker.strategy.base import Strategy, StrategySignal
from theme_picker.strategy.params import StrategyParams


TrendLabel = Literal["uptrend", "downtrend", "sideways"]


@dataclass(frozen=True)
class BoxSnapshot:
    support: float
    resistance: float
    height: float
    support_touches: int
    resistance_touches: int


class AShareBoxStrategy(Strategy):
    """Long-only A-share box strategy.

    Adaptation notes:
    - only keeps long setups because normal A-shares are not short-friendly
    - uses daily-bar box stacking to infer trend
    - emphasizes breakout and breakout-retest long entries
    - exits on stop, target, timeout, box failure, or MA10 loss
    """

    name = "a_share_box"

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
        min_required = max(40, int(params.box_lookback_days) * 2)
        available_rows = (int(current_index) + 1) if current_index is not None else len(history)
        if history is None or history.empty or available_rows < min_required:
            return StrategySignal(
                action="hold",
                reason="history_not_ready",
                metadata={"price_adjustment": price_adjustment, "strategy_name": self.name},
            )

        slice_lookback = max(
            min_required,
            int(params.signal_number_lookback_days),
            int(params.box_lookback_days) * 2 + int(params.breakout_retest_window) + 5,
        )
        if current_index is None:
            working = history.copy().sort_values("date").reset_index(drop=True)
        else:
            start_index = max(0, int(current_index) - slice_lookback + 1)
            working = history.iloc[start_index : int(current_index) + 1].copy().reset_index(drop=True)
        self._ensure_indicators(working)

        latest = working.iloc[-1]
        current_box = self._build_box_snapshot(working.iloc[-int(params.box_lookback_days):-1], params)
        previous_slice = working.iloc[-int(params.box_lookback_days) * 2:-int(params.box_lookback_days)]
        previous_box = self._build_box_snapshot(previous_slice, params)
        trend = self._classify_trend(current_box, previous_box)

        close_price = self._to_float(latest.get("close"))
        low_price = self._to_float(latest.get("low"))
        ma10 = self._to_float(latest.get("ma10"))
        pct_chg = self._to_float(latest.get("pct_chg")) or 0.0
        volume_ratio = self._to_float(latest.get("volume_ratio")) or 0.0
        turnover_rate = self._to_float(latest.get("turnover_rate")) or 0.0
        open_price = self._to_float(latest.get("open"))
        previous_close = self._to_float(working.iloc[-2].get("close"))

        base_metadata = {
            "strategy_name": self.name,
            "price_adjustment": price_adjustment,
            "trend": trend,
            "box_support": round(current_box.support, 4),
            "box_resistance": round(current_box.resistance, 4),
            "box_height": round(current_box.height, 4),
            "support_touches": current_box.support_touches,
            "resistance_touches": current_box.resistance_touches,
            "close_price": close_price,
            "ma10": ma10,
            "pct_chg": pct_chg,
            "volume_ratio": volume_ratio,
            "turnover_rate": turnover_rate,
        }

        if close_price is None or low_price is None or ma10 is None or previous_close is None:
            return StrategySignal(action="hold", reason="missing_price_context", metadata=base_metadata)

        stop_price = current_box.support * (1 - float(params.stop_buffer_pct))
        risk_per_share = max(0.0, close_price - stop_price)
        target_price = close_price + max(current_box.height, risk_per_share * float(params.rr_min))
        rr_ratio = (target_price - close_price) / risk_per_share if risk_per_share > 0 else None

        if has_position and entry_price:
            pnl_pct = (close_price - entry_price) / entry_price
            if pnl_pct <= -abs(params.stop_loss_pct):
                return StrategySignal(action="sell", reason="stop_loss_hit", score=pnl_pct, metadata=base_metadata)
            if pnl_pct >= abs(params.take_profit_pct):
                return StrategySignal(action="sell", reason="take_profit_hit", score=pnl_pct, metadata=base_metadata)
            if holding_days >= int(params.max_holding_days):
                return StrategySignal(action="sell", reason="max_holding_days_reached", score=pnl_pct, metadata=base_metadata)
            if close_price < stop_price:
                return StrategySignal(action="sell", reason="box_support_failed", score=pnl_pct, metadata=base_metadata)
            if close_price < ma10:
                return StrategySignal(action="sell", reason="close_below_ma10", score=pnl_pct, metadata=base_metadata)
            return StrategySignal(action="hold", reason="holding", metadata=base_metadata)

        if bool(params.require_uptrend_for_entry) and trend != "uptrend":
            return StrategySignal(action="hold", reason="trend_not_up", metadata=base_metadata)

        if turnover_rate < float(params.min_turnover_rate):
            return StrategySignal(action="hold", reason="turnover_rate_too_low", metadata=base_metadata)

        breakout_confirmed = (
            previous_close <= current_box.resistance
            and close_price > current_box.resistance
            and pct_chg >= float(params.min_breakout_pct)
            and volume_ratio >= float(params.min_volume_ratio)
            and current_box.resistance_touches >= int(params.min_box_touches)
            and ((close_price - current_box.resistance) / current_box.resistance) <= float(params.max_breakout_extension_pct)
        )
        if breakout_confirmed:
            signal_number, breakout_cluster_count = self._estimate_signal_number(
                working,
                params=params,
                signal_type="breakout_long",
            )
            quality_score = self._score_breakout_signal(
                trend=trend,
                current_box=current_box,
                volume_ratio=volume_ratio,
                turnover_rate=turnover_rate,
                extension_pct=(close_price - current_box.resistance) / current_box.resistance,
                rr_ratio=rr_ratio,
                signal_number=signal_number,
                params=params,
            )
            return StrategySignal(
                action="buy",
                reason="breakout_long",
                score=quality_score,
                metadata={
                    **base_metadata,
                    "signal_type": "breakout_long",
                    "signal_number": signal_number,
                    "breakout_cluster_count": breakout_cluster_count,
                    "signal_number_rule": "count breakout clusters inside lookback window",
                    "signal_number_lookback_days": int(params.signal_number_lookback_days),
                    "signal_number_event_cooldown_days": int(params.signal_number_event_cooldown_days),
                    "quality_score": quality_score,
                    "rr_ratio": round(rr_ratio, 4) if rr_ratio is not None else None,
                    "entry_price_hint": close_price,
                    "stop_price_hint": round(stop_price, 4),
                    "target_price_hint": round(target_price, 4),
                },
            )

        pullback_signal = self._detect_pullback_bounce(
            working=working,
            params=params,
            current_box=current_box,
            close_price=close_price,
            low_price=low_price,
            open_price=open_price,
            volume_ratio=volume_ratio,
        )
        if pullback_signal:
            signal_number, breakout_cluster_count = self._estimate_signal_number(
                working,
                params=params,
                signal_type="pullback_bounce",
            )
            quality_score = self._score_pullback_signal(
                trend=trend,
                current_box=current_box,
                volume_ratio=volume_ratio,
                turnover_rate=turnover_rate,
                rr_ratio=rr_ratio,
                signal_number=signal_number,
                params=params,
            )
            return StrategySignal(
                action="buy",
                reason="pullback_bounce",
                score=quality_score,
                metadata={
                    **base_metadata,
                    "signal_type": "pullback_bounce",
                    "signal_number": signal_number,
                    "breakout_cluster_count": breakout_cluster_count,
                    "signal_number_rule": "pullback is treated as at least the next signal after breakout cluster count",
                    "signal_number_lookback_days": int(params.signal_number_lookback_days),
                    "signal_number_event_cooldown_days": int(params.signal_number_event_cooldown_days),
                    "quality_score": quality_score,
                    "rr_ratio": round(rr_ratio, 4) if rr_ratio is not None else None,
                    "entry_price_hint": close_price,
                    "stop_price_hint": round(stop_price, 4),
                    "target_price_hint": round(target_price, 4),
                },
            )

        return StrategySignal(action="hold", reason="entry_not_ready", metadata=base_metadata)

    def _detect_pullback_bounce(
        self,
        *,
        working: pd.DataFrame,
        params: StrategyParams,
        current_box: BoxSnapshot,
        close_price: float,
        low_price: float,
        open_price: Optional[float],
        volume_ratio: float,
    ) -> bool:
        retest_window = max(2, int(params.breakout_retest_window))
        recent = working.iloc[-retest_window:]
        if recent.empty:
            return False

        recent_high_close = pd.to_numeric(recent["close"], errors="coerce").max()
        had_breakout = self._to_float(recent_high_close) is not None and recent_high_close > current_box.resistance
        touched_zone = low_price <= current_box.resistance * (1 + float(params.box_tolerance_pct))
        reclaimed = close_price >= current_box.resistance * (1 + float(params.pullback_reclaim_pct))
        rebound_bar = open_price is None or close_price >= open_price
        enough_volume = volume_ratio >= max(1.0, float(params.min_volume_ratio) * 0.8)
        return bool(had_breakout and touched_zone and reclaimed and rebound_bar and enough_volume)

    def _estimate_signal_number(
        self,
        working: pd.DataFrame,
        *,
        params: StrategyParams,
        signal_type: str,
    ) -> tuple[int, int]:
        lookback = max(int(params.signal_number_lookback_days), int(params.box_lookback_days) * 2, 40)
        recent = working.tail(lookback).copy()
        if len(recent) < int(params.box_lookback_days) + 2:
            fallback_number = 1 if signal_type == "breakout_long" else 2
            return fallback_number, 1

        close_series = pd.to_numeric(recent["close"], errors="coerce")
        rolling_resistance = close_series.shift(1).rolling(int(params.box_lookback_days), min_periods=max(5, int(params.box_lookback_days) // 2)).max()
        prior_close = close_series.shift(1)
        breakout_events = ((prior_close <= rolling_resistance) & (close_series > rolling_resistance)).fillna(False)
        cooldown = max(3, int(params.signal_number_event_cooldown_days))
        breakout_count = 0
        last_event_index = None
        for index, is_breakout in enumerate(breakout_events.tolist()):
            if not is_breakout:
                continue
            if last_event_index is None or (index - last_event_index) > cooldown:
                breakout_count += 1
                last_event_index = index

        if signal_type == "breakout_long":
            return max(1, breakout_count), max(1, breakout_count)
        return max(2, breakout_count + 1), max(1, breakout_count)

    def _score_breakout_signal(
        self,
        *,
        trend: TrendLabel,
        current_box: BoxSnapshot,
        volume_ratio: float,
        turnover_rate: float,
        extension_pct: float,
        rr_ratio: Optional[float],
        signal_number: int,
        params: StrategyParams,
    ) -> float:
        score = 0.35
        if trend == "uptrend":
            score += 0.2
        elif trend == "sideways":
            score += 0.05

        if current_box.resistance_touches >= 3:
            score += 0.15
        elif current_box.resistance_touches >= int(params.min_box_touches):
            score += 0.08

        if volume_ratio >= float(params.min_volume_ratio) * 1.3:
            score += 0.15
        elif volume_ratio >= float(params.min_volume_ratio):
            score += 0.1

        score += self._turnover_score(turnover_rate, params)

        if rr_ratio is not None:
            if rr_ratio >= 3.0:
                score += 0.1
            elif rr_ratio >= float(params.rr_min):
                score += 0.06

        if signal_number == 1:
            score += 0.08
        elif signal_number >= 3:
            score -= min(0.12, 0.03 * (signal_number - 2))

        max_extension = max(0.001, float(params.max_breakout_extension_pct))
        if extension_pct >= max_extension * 0.8:
            score -= 0.1
        elif extension_pct >= max_extension * 0.5:
            score -= 0.05

        return round(max(0.05, min(score, 0.95)), 4)

    def _score_pullback_signal(
        self,
        *,
        trend: TrendLabel,
        current_box: BoxSnapshot,
        volume_ratio: float,
        turnover_rate: float,
        rr_ratio: Optional[float],
        signal_number: int,
        params: StrategyParams,
    ) -> float:
        score = 0.4
        if trend == "uptrend":
            score += 0.2
        elif trend == "sideways":
            score += 0.08

        if current_box.resistance_touches >= 3:
            score += 0.1
        elif current_box.resistance_touches >= int(params.min_box_touches):
            score += 0.06

        if volume_ratio >= float(params.min_volume_ratio):
            score += 0.1
        elif volume_ratio >= max(1.0, float(params.min_volume_ratio) * 0.8):
            score += 0.05

        score += self._turnover_score(turnover_rate, params)

        if rr_ratio is not None:
            if rr_ratio >= 3.0:
                score += 0.08
            elif rr_ratio >= float(params.rr_min):
                score += 0.05

        if signal_number == 2:
            score += 0.08
        elif signal_number >= 4:
            score -= min(0.1, 0.025 * (signal_number - 3))

        return round(max(0.05, min(score, 0.95)), 4)

    def _build_box_snapshot(self, window: pd.DataFrame, params: StrategyParams) -> BoxSnapshot:
        tolerance = max(0.001, float(params.box_tolerance_pct))
        high_series = pd.to_numeric(window.get("high"), errors="coerce")
        low_series = pd.to_numeric(window.get("low"), errors="coerce")
        resistance = self._to_float(high_series.max()) or 0.0
        support = self._to_float(low_series.min()) or 0.0
        if resistance <= 0 or support <= 0 or resistance <= support:
            resistance = max(resistance, support)
            height = max(0.0, resistance - support)
        else:
            height = resistance - support

        if support > 0 and resistance > 0:
            support_touches = int((low_series <= support * (1 + tolerance)).sum())
            resistance_touches = int((high_series >= resistance * (1 - tolerance)).sum())
        else:
            support_touches = 0
            resistance_touches = 0

        min_height = support * float(params.min_box_height_pct) if support > 0 else 0.0
        if height < min_height:
            resistance = support + min_height
            height = min_height

        return BoxSnapshot(
            support=support,
            resistance=resistance,
            height=height,
            support_touches=support_touches,
            resistance_touches=resistance_touches,
        )

    @staticmethod
    def _classify_trend(current_box: BoxSnapshot, previous_box: BoxSnapshot) -> TrendLabel:
        if current_box.support > previous_box.support and current_box.resistance > previous_box.resistance:
            return "uptrend"
        if current_box.support < previous_box.support and current_box.resistance < previous_box.resistance:
            return "downtrend"
        return "sideways"

    @staticmethod
    def _ensure_indicators(frame: pd.DataFrame) -> None:
        if "ma10" not in frame.columns:
            frame["ma10"] = pd.to_numeric(frame["close"], errors="coerce").rolling(10, min_periods=1).mean()
        if "volume_ratio" not in frame.columns:
            volume = pd.to_numeric(frame["volume"], errors="coerce")
            avg_volume_5 = volume.rolling(5, min_periods=1).mean().shift(1)
            frame["volume_ratio"] = (volume / avg_volume_5).replace([float("inf"), float("-inf")], pd.NA).fillna(1.0)
        if "turnover_rate" in frame.columns:
            frame["turnover_rate"] = pd.to_numeric(frame["turnover_rate"], errors="coerce")
        if "pct_chg" not in frame.columns:
            close = pd.to_numeric(frame["close"], errors="coerce")
            frame["pct_chg"] = close.pct_change().fillna(0.0) * 100.0

    @staticmethod
    def _turnover_score(turnover_rate: float, params: StrategyParams) -> float:
        min_turnover = max(0.0, float(params.min_turnover_rate))
        preferred_low = max(min_turnover, float(params.preferred_turnover_rate_low))
        preferred_high = max(preferred_low, float(params.preferred_turnover_rate_high))
        if turnover_rate >= preferred_low and turnover_rate <= preferred_high:
            return 0.08
        if turnover_rate > preferred_high:
            return 0.03 if turnover_rate <= preferred_high * 1.5 else -0.04
        if turnover_rate >= min_turnover:
            return 0.02
        return -0.08

    @staticmethod
    def _to_float(value) -> Optional[float]:
        if value is None or value is pd.NA:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
