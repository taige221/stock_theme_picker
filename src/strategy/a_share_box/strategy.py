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


@dataclass(frozen=True)
class ExitProfile:
    stop_loss_pct: float
    take_profit_pct: float
    max_holding_days: int
    enable_trailing_stop: bool
    trailing_stop_activate_profit_pct: float
    trailing_stop_drawdown_pct: float
    enable_ma10_confirm_exit: bool
    ma10_confirm_days: int


@dataclass(frozen=True)
class StallProfile:
    enable_entry_stall_exit: bool
    entry_stall_days: int
    entry_stall_min_return_pct: float


@dataclass(frozen=True)
class BoxSignalContext:
    working: pd.DataFrame
    latest: pd.Series
    current_box: BoxSnapshot
    previous_box: BoxSnapshot
    pre_previous_box: Optional[BoxSnapshot]
    trend: TrendLabel
    previous_trend: Optional[TrendLabel]
    close_price: Optional[float]
    low_price: Optional[float]
    ma10: Optional[float]
    pct_chg: float
    volume_ratio: float
    turnover_rate: float
    turnover_rate_median_20: Optional[float]
    atr_pct_20: Optional[float]
    style_bucket: Optional[str]
    open_price: Optional[float]
    previous_close: Optional[float]
    macd_dif: Optional[float]
    macd_dea: Optional[float]
    macd_hist: Optional[float]
    macd_hist_slope_3: Optional[float]
    macd_dif_above_dea: bool
    macd_above_zero: bool
    macd_hist_rising_3: bool
    macd_state: Optional[str]
    effective_min_turnover_rate: float
    effective_preferred_turnover_rate_low: float
    effective_preferred_turnover_rate_high: float
    breakout_min_breakout_pct: float
    breakout_min_volume_ratio: float
    breakout_min_body_pct: float
    breakout_min_close_above_resistance_pct: float
    breakout_max_upper_shadow_ratio: float
    breakout_min_box_touches: int
    breakout_max_extension_pct: float
    breakout_max_bias_ma10_pct: float
    breakout_max_box_height_pct: float
    breakout_avoid_box_height_low_pct: float
    breakout_avoid_box_height_high_pct: float
    breakout_min_stack_lift_pct: float
    pullback_min_volume_ratio: float
    pullback_min_box_touches: int
    pullback_reclaim_pct: float
    pullback_max_break_below_resistance_pct: float
    pullback_max_bias_ma10_pct: float
    pullback_min_box_height_pct: float
    breakout_min_signal_score: float
    pullback_min_signal_score: float
    exit_profile: ExitProfile
    stall_profile: StallProfile
    ma10_bias_pct: Optional[float]
    box_height_pct: Optional[float]
    box_stack_lift_pct: Optional[float]
    recovering_from_downtrend: bool
    pullback_rebound_recent_gain_pct: Optional[float]
    pullback_profit_power: dict[str, object]
    pullback_rebound_risk: dict[str, object]
    base_metadata: dict[str, object]


@dataclass(frozen=True)
class BoxRiskPlan:
    stop_price: float
    target_price: float
    rr_ratio: Optional[float]


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
        entry_signal_reason: Optional[str] = None,
        entry_signal_metadata: Optional[dict] = None,
        position_highest_price_seen: Optional[float] = None,
    ) -> StrategySignal:
        min_required = self._min_required_rows(params)
        available_rows = 0 if history is None else (
            (int(current_index) + 1) if current_index is not None else len(history)
        )
        if history is None or history.empty or available_rows < min_required:
            return StrategySignal(
                action="hold",
                reason="history_not_ready",
                metadata={"price_adjustment": price_adjustment, "strategy_name": self.name},
            )

        working = self._prepare_working_frame(history, current_index=current_index, params=params)
        context = self._build_signal_context(
            working=working,
            params=params,
            price_adjustment=price_adjustment,
            entry_signal_reason=entry_signal_reason,
        )

        if self._missing_price_context(context):
            return StrategySignal(action="hold", reason="missing_price_context", metadata=context.base_metadata)

        risk_plan = self._build_risk_plan(context, params)

        if has_position and entry_price:
            return self._generate_exit_signal(
                context=context,
                risk_plan=risk_plan,
                params=params,
                entry_price=entry_price,
                holding_days=holding_days,
                entry_signal_reason=entry_signal_reason,
                entry_signal_metadata=entry_signal_metadata,
                position_highest_price_seen=position_highest_price_seen,
            )

        entry_block_signal = self._check_entry_preconditions(context, params)
        if entry_block_signal is not None:
            return entry_block_signal

        breakout_signal = self._generate_breakout_signal(context=context, risk_plan=risk_plan, params=params)
        if breakout_signal is not None:
            return breakout_signal

        pullback_signal = self._generate_pullback_signal(context=context, risk_plan=risk_plan, params=params)
        if pullback_signal is not None:
            return pullback_signal

        return StrategySignal(action="hold", reason="entry_not_ready", metadata=context.base_metadata)

    @staticmethod
    def _min_required_rows(params: StrategyParams) -> int:
        return max(40, int(params.box_lookback_days) * 2)

    def _prepare_working_frame(
        self,
        history: pd.DataFrame,
        *,
        current_index: Optional[int],
        params: StrategyParams,
    ) -> pd.DataFrame:
        min_required = self._min_required_rows(params)
        slice_lookback = max(
            min_required,
            int(params.signal_number_lookback_days),
            int(params.box_lookback_days) * 2 + int(params.breakout_retest_window) + 5,
            int(params.pullback_profit_power_lookback_days)
            + int(params.pullback_profit_power_rolling_gain_days)
            + 5,
        )
        if current_index is None:
            working = history.copy().sort_values("date").reset_index(drop=True)
        else:
            start_index = max(0, int(current_index) - slice_lookback + 1)
            working = history.iloc[start_index : int(current_index) + 1].copy().reset_index(drop=True)
        self._ensure_indicators(working)
        return working

    def _build_signal_context(
        self,
        *,
        working: pd.DataFrame,
        params: StrategyParams,
        price_adjustment: str,
        entry_signal_reason: Optional[str],
    ) -> BoxSignalContext:
        latest = working.iloc[-1]
        current_box = self._build_box_snapshot(working.iloc[-int(params.box_lookback_days):-1], params)
        previous_slice = working.iloc[-int(params.box_lookback_days) * 2:-int(params.box_lookback_days)]
        previous_box = self._build_box_snapshot(previous_slice, params)
        pre_previous_box = self._build_optional_box_snapshot(
            working.iloc[-int(params.box_lookback_days) * 3:-int(params.box_lookback_days) * 2],
            params,
        )
        trend = self._classify_trend(current_box, previous_box)
        previous_trend = self._classify_trend(previous_box, pre_previous_box) if pre_previous_box else None

        close_price = self._to_float(latest.get("close"))
        low_price = self._to_float(latest.get("low"))
        ma10 = self._to_float(latest.get("ma10"))
        pct_chg = self._to_float(latest.get("pct_chg")) or 0.0
        volume_ratio = self._to_float(latest.get("volume_ratio")) or 0.0
        turnover_rate = self._to_float(latest.get("turnover_rate")) or 0.0
        turnover_rate_median_20 = self._to_float(latest.get("turnover_rate_median_20"))
        atr_pct_20 = self._to_float(latest.get("atr_pct_20"))
        style_bucket = self._normalize_style_bucket(latest.get("style_bucket"))
        open_price = self._to_float(latest.get("open"))
        previous_close = self._to_float(working.iloc[-2].get("close"))
        macd_dif = self._to_float(latest.get("macd_dif"))
        macd_dea = self._to_float(latest.get("macd_dea"))
        macd_hist = self._to_float(latest.get("macd_hist"))
        macd_hist_slope_3 = self._to_float(latest.get("macd_hist_slope_3"))
        macd_dif_above_dea = bool(macd_dif is not None and macd_dea is not None and macd_dif > macd_dea)
        macd_above_zero = bool(macd_dif is not None and macd_dea is not None and macd_dif > 0 and macd_dea > 0)
        macd_hist_rising_3 = bool(macd_hist_slope_3 is not None and macd_hist_slope_3 >= 0)
        macd_state = self._classify_macd_state(
            macd_dif=macd_dif,
            macd_dea=macd_dea,
            macd_hist=macd_hist,
            macd_hist_slope_3=macd_hist_slope_3,
        )
        effective_min_turnover_rate, effective_preferred_turnover_rate_low, effective_preferred_turnover_rate_high = (
            self._resolve_turnover_profile(style_bucket, params)
        )
        breakout_min_breakout_pct = self._resolve_breakout_min_breakout_pct(params)
        breakout_min_volume_ratio = self._resolve_breakout_min_volume_ratio(params)
        breakout_min_body_pct = self._resolve_breakout_min_body_pct(params)
        breakout_min_close_above_resistance_pct = self._resolve_breakout_min_close_above_resistance_pct(params)
        breakout_max_upper_shadow_ratio = self._resolve_breakout_max_upper_shadow_ratio(params)
        breakout_min_box_touches = self._resolve_breakout_min_box_touches(params)
        breakout_max_extension_pct = self._resolve_breakout_max_extension_pct(params)
        breakout_max_bias_ma10_pct = self._resolve_breakout_max_bias_ma10_pct(params)
        breakout_max_box_height_pct = self._resolve_breakout_max_box_height_pct(params)
        breakout_avoid_box_height_low_pct = float(params.breakout_avoid_box_height_low_pct)
        breakout_avoid_box_height_high_pct = float(params.breakout_avoid_box_height_high_pct)
        breakout_min_stack_lift_pct = float(params.breakout_min_stack_lift_pct)
        pullback_min_volume_ratio = self._resolve_pullback_min_volume_ratio(params)
        pullback_min_box_touches = self._resolve_pullback_min_box_touches(style_bucket, params)
        pullback_reclaim_pct = self._resolve_pullback_reclaim_pct(style_bucket, params)
        pullback_max_break_below_resistance_pct = self._resolve_pullback_max_break_below_resistance_pct(params)
        pullback_max_bias_ma10_pct = self._resolve_pullback_max_bias_ma10_pct(params)
        pullback_min_box_height_pct = self._resolve_pullback_min_box_height_pct(params)
        breakout_min_signal_score = self._resolve_breakout_min_signal_score(params)
        pullback_min_signal_score = self._resolve_pullback_min_signal_score(params)
        exit_profile = self._resolve_exit_profile(entry_signal_reason, style_bucket, params)
        stall_profile = self._resolve_stall_profile(entry_signal_reason, style_bucket, params)
        ma10_bias_pct = self._calculate_ma10_bias_pct(close_price=close_price, ma10=ma10)
        box_height_pct = self._calculate_box_height_pct(current_box)
        box_stack_lift_pct = self._calculate_box_stack_lift_pct(current_box, previous_box)
        recovering_from_downtrend = bool(previous_trend == "downtrend" and trend == "uptrend")
        pullback_rebound_recent_gain_pct = self._calculate_recent_gain_pct(
            working,
            days=int(params.pullback_rebound_recent_gain_days),
        )
        pullback_profit_power = self._detect_pullback_profit_power(working=working, params=params)
        pullback_rebound_risk = self._detect_pullback_rebound_risk(
            recovering_from_downtrend=bool(recovering_from_downtrend),
            recent_gain_pct=pullback_rebound_recent_gain_pct,
            ma10_bias_pct=ma10_bias_pct,
            profit_power=pullback_profit_power,
            params=params,
        )

        base_metadata = {
            "strategy_name": self.name,
            "price_adjustment": price_adjustment,
            "trend": trend,
            "previous_trend": previous_trend,
            "recovering_from_downtrend": recovering_from_downtrend,
            "box_support": round(current_box.support, 4),
            "box_resistance": round(current_box.resistance, 4),
            "box_height": round(current_box.height, 4),
            "box_height_pct": round(box_height_pct, 4) if box_height_pct is not None else None,
            "box_stack_lift_pct": round(box_stack_lift_pct, 4) if box_stack_lift_pct is not None else None,
            "support_touches": current_box.support_touches,
            "resistance_touches": current_box.resistance_touches,
            "close_price": close_price,
            "ma10": ma10,
            "ma10_bias_pct": round(ma10_bias_pct, 4) if ma10_bias_pct is not None else None,
            "pct_chg": pct_chg,
            "volume_ratio": volume_ratio,
            "turnover_rate": turnover_rate,
            "turnover_rate_median_20": turnover_rate_median_20,
            "atr_pct_20": atr_pct_20,
            "style_bucket": style_bucket,
            "macd_dif": self._round_optional(macd_dif, 4),
            "macd_dea": self._round_optional(macd_dea, 4),
            "macd_hist": self._round_optional(macd_hist, 4),
            "macd_hist_slope_3": self._round_optional(macd_hist_slope_3, 4),
            "macd_dif_above_dea": macd_dif_above_dea,
            "macd_above_zero": macd_above_zero,
            "macd_hist_rising_3": macd_hist_rising_3,
            "macd_state": macd_state,
            "effective_enable_macd_score_adjustment": bool(params.enable_macd_score_adjustment),
            "effective_macd_bullish_bonus": float(params.macd_bullish_bonus),
            "effective_macd_bearish_penalty": float(params.macd_bearish_penalty),
            "effective_breakout_high_volume_macd_weak_penalty": float(
                params.breakout_high_volume_macd_weak_penalty
            ),
            "effective_pullback_macd_weak_penalty": float(params.pullback_macd_weak_penalty),
            "effective_enable_macd_divergence_decision": bool(params.enable_macd_divergence_decision),
            "effective_macd_divergence_lookback_days": int(params.macd_divergence_lookback_days),
            "effective_macd_divergence_price_tolerance_pct": float(
                params.macd_divergence_price_tolerance_pct
            ),
            "effective_breakout_macd_bearish_divergence_min_volume_ratio": float(
                params.breakout_macd_bearish_divergence_min_volume_ratio
            ),
            "effective_breakout_macd_bearish_divergence_penalty": float(
                params.breakout_macd_bearish_divergence_penalty
            ),
            "effective_breakout_block_macd_bearish_divergence": bool(
                params.breakout_block_macd_bearish_divergence
            ),
            "effective_pullback_macd_bullish_divergence_bonus": float(
                params.pullback_macd_bullish_divergence_bonus
            ),
            "effective_enable_pullback_rebound_risk_control": bool(params.enable_pullback_rebound_risk_control),
            "effective_pullback_rebound_recent_gain_days": int(params.pullback_rebound_recent_gain_days),
            "effective_pullback_rebound_max_recent_gain_pct": float(
                params.pullback_rebound_max_recent_gain_pct
            ),
            "effective_pullback_rebound_max_bias_ma10_pct": float(
                params.pullback_rebound_max_bias_ma10_pct
            ),
            "effective_pullback_rebound_score_penalty": float(params.pullback_rebound_score_penalty),
            "effective_pullback_rebound_block_entry": bool(params.pullback_rebound_block_entry),
            "effective_enable_pullback_profit_power_filter": bool(params.enable_pullback_profit_power_filter),
            "effective_pullback_profit_power_lookback_days": int(params.pullback_profit_power_lookback_days),
            "effective_pullback_profit_power_min_range_pct": float(params.pullback_profit_power_min_range_pct),
            "effective_pullback_profit_power_rolling_gain_days": int(
                params.pullback_profit_power_rolling_gain_days
            ),
            "effective_pullback_profit_power_min_rolling_gain_pct": float(
                params.pullback_profit_power_min_rolling_gain_pct
            ),
            "effective_pullback_profit_power_max_recent_gain_pct": float(
                params.pullback_profit_power_max_recent_gain_pct
            ),
            "effective_pullback_profit_power_max_ma10_bias_pct": float(
                params.pullback_profit_power_max_ma10_bias_pct
            ),
            "effective_pullback_rebound_profit_power_penalty_multiplier": float(
                params.pullback_rebound_profit_power_penalty_multiplier
            ),
            "pullback_rebound_recent_gain_pct": (
                round(pullback_rebound_recent_gain_pct, 4)
                if pullback_rebound_recent_gain_pct is not None
                else None
            ),
            **pullback_profit_power,
            **pullback_rebound_risk,
            "effective_enable_breakout_trend_hold_extension": bool(
                params.enable_breakout_trend_hold_extension
            ),
            "effective_breakout_trend_hold_extension_max_days": int(
                params.breakout_trend_hold_extension_max_days
            ),
            "effective_min_turnover_rate": effective_min_turnover_rate,
            "effective_preferred_turnover_rate_low": effective_preferred_turnover_rate_low,
            "effective_preferred_turnover_rate_high": effective_preferred_turnover_rate_high,
            "effective_max_turnover_rate": float(params.max_turnover_rate),
            "effective_score_high_box_height_threshold_pct": float(params.score_high_box_height_threshold_pct),
            "effective_score_high_box_height_penalty": float(params.score_high_box_height_penalty),
            "effective_score_high_turnover_rate_threshold": float(params.score_high_turnover_rate_threshold),
            "effective_score_high_turnover_rate_penalty": float(params.score_high_turnover_rate_penalty),
            "effective_score_high_volume_ratio_threshold": float(params.score_high_volume_ratio_threshold),
            "effective_score_high_volume_ratio_penalty": float(params.score_high_volume_ratio_penalty),
            "effective_breakout_min_breakout_pct": breakout_min_breakout_pct,
            "effective_breakout_min_volume_ratio": breakout_min_volume_ratio,
            "effective_breakout_min_body_pct": breakout_min_body_pct,
            "effective_breakout_min_close_above_resistance_pct": breakout_min_close_above_resistance_pct,
            "effective_breakout_max_upper_shadow_ratio": breakout_max_upper_shadow_ratio,
            "effective_breakout_min_box_touches": breakout_min_box_touches,
            "effective_breakout_max_extension_pct": breakout_max_extension_pct,
            "effective_breakout_max_bias_ma10_pct": breakout_max_bias_ma10_pct,
            "effective_breakout_max_box_height_pct": breakout_max_box_height_pct,
            "effective_breakout_avoid_box_height_low_pct": breakout_avoid_box_height_low_pct,
            "effective_breakout_avoid_box_height_high_pct": breakout_avoid_box_height_high_pct,
            "effective_breakout_min_stack_lift_pct": breakout_min_stack_lift_pct,
            "effective_block_breakout_after_downtrend": bool(params.block_breakout_after_downtrend),
            "effective_pullback_min_volume_ratio": pullback_min_volume_ratio,
            "effective_pullback_min_box_touches": pullback_min_box_touches,
            "effective_pullback_reclaim_pct": pullback_reclaim_pct,
            "effective_pullback_max_break_below_resistance_pct": pullback_max_break_below_resistance_pct,
            "effective_pullback_max_bias_ma10_pct": pullback_max_bias_ma10_pct,
            "effective_pullback_min_box_height_pct": pullback_min_box_height_pct,
            "effective_breakout_min_signal_score": breakout_min_signal_score,
            "effective_pullback_min_signal_score": pullback_min_signal_score,
            "entry_signal_reason": entry_signal_reason,
            "effective_stop_loss_pct": exit_profile.stop_loss_pct,
            "effective_take_profit_pct": exit_profile.take_profit_pct,
            "effective_max_holding_days": exit_profile.max_holding_days,
            "effective_enable_trailing_stop": exit_profile.enable_trailing_stop,
            "effective_trailing_stop_activate_profit_pct": exit_profile.trailing_stop_activate_profit_pct,
            "effective_trailing_stop_drawdown_pct": exit_profile.trailing_stop_drawdown_pct,
            "effective_enable_ma10_confirm_exit": exit_profile.enable_ma10_confirm_exit,
            "effective_ma10_confirm_days": exit_profile.ma10_confirm_days,
            "effective_enable_entry_stall_exit": stall_profile.enable_entry_stall_exit,
            "effective_entry_stall_days": stall_profile.entry_stall_days,
            "effective_entry_stall_min_return_pct": stall_profile.entry_stall_min_return_pct,
            "effective_pullback_enable_failure_exit": bool(params.pullback_enable_failure_exit),
            "effective_pullback_failure_exit_days": int(params.pullback_failure_exit_days),
            "effective_pullback_failure_confirm_days": int(params.pullback_failure_confirm_days),
            "effective_pullback_failure_buffer_pct": float(params.pullback_failure_buffer_pct),
            "effective_pullback_failure_max_profit_pct": float(params.pullback_failure_max_profit_pct),
            "effective_enable_breakeven_stop": bool(params.enable_breakeven_stop),
            "effective_breakout_enable_breakeven_stop": (
                bool(params.breakout_enable_breakeven_stop)
                if params.breakout_enable_breakeven_stop is not None
                else None
            ),
            "effective_pullback_enable_breakeven_stop": (
                bool(params.pullback_enable_breakeven_stop)
                if params.pullback_enable_breakeven_stop is not None
                else None
            ),
            "effective_breakeven_activate_profit_pct": float(params.breakeven_activate_profit_pct),
            "effective_breakeven_exit_threshold_pct": float(params.breakeven_exit_threshold_pct),
        }

        return BoxSignalContext(
            working=working,
            latest=latest,
            current_box=current_box,
            previous_box=previous_box,
            pre_previous_box=pre_previous_box,
            trend=trend,
            previous_trend=previous_trend,
            close_price=close_price,
            low_price=low_price,
            ma10=ma10,
            pct_chg=pct_chg,
            volume_ratio=volume_ratio,
            turnover_rate=turnover_rate,
            turnover_rate_median_20=turnover_rate_median_20,
            atr_pct_20=atr_pct_20,
            style_bucket=style_bucket,
            open_price=open_price,
            previous_close=previous_close,
            macd_dif=macd_dif,
            macd_dea=macd_dea,
            macd_hist=macd_hist,
            macd_hist_slope_3=macd_hist_slope_3,
            macd_dif_above_dea=macd_dif_above_dea,
            macd_above_zero=macd_above_zero,
            macd_hist_rising_3=macd_hist_rising_3,
            macd_state=macd_state,
            effective_min_turnover_rate=effective_min_turnover_rate,
            effective_preferred_turnover_rate_low=effective_preferred_turnover_rate_low,
            effective_preferred_turnover_rate_high=effective_preferred_turnover_rate_high,
            breakout_min_breakout_pct=breakout_min_breakout_pct,
            breakout_min_volume_ratio=breakout_min_volume_ratio,
            breakout_min_body_pct=breakout_min_body_pct,
            breakout_min_close_above_resistance_pct=breakout_min_close_above_resistance_pct,
            breakout_max_upper_shadow_ratio=breakout_max_upper_shadow_ratio,
            breakout_min_box_touches=breakout_min_box_touches,
            breakout_max_extension_pct=breakout_max_extension_pct,
            breakout_max_bias_ma10_pct=breakout_max_bias_ma10_pct,
            breakout_max_box_height_pct=breakout_max_box_height_pct,
            breakout_avoid_box_height_low_pct=breakout_avoid_box_height_low_pct,
            breakout_avoid_box_height_high_pct=breakout_avoid_box_height_high_pct,
            breakout_min_stack_lift_pct=breakout_min_stack_lift_pct,
            pullback_min_volume_ratio=pullback_min_volume_ratio,
            pullback_min_box_touches=pullback_min_box_touches,
            pullback_reclaim_pct=pullback_reclaim_pct,
            pullback_max_break_below_resistance_pct=pullback_max_break_below_resistance_pct,
            pullback_max_bias_ma10_pct=pullback_max_bias_ma10_pct,
            pullback_min_box_height_pct=pullback_min_box_height_pct,
            breakout_min_signal_score=breakout_min_signal_score,
            pullback_min_signal_score=pullback_min_signal_score,
            exit_profile=exit_profile,
            stall_profile=stall_profile,
            ma10_bias_pct=ma10_bias_pct,
            box_height_pct=box_height_pct,
            box_stack_lift_pct=box_stack_lift_pct,
            recovering_from_downtrend=recovering_from_downtrend,
            pullback_rebound_recent_gain_pct=pullback_rebound_recent_gain_pct,
            pullback_profit_power=pullback_profit_power,
            pullback_rebound_risk=pullback_rebound_risk,
            base_metadata=base_metadata,
        )

    @staticmethod
    def _missing_price_context(context: BoxSignalContext) -> bool:
        return (
            context.close_price is None
            or context.low_price is None
            or context.ma10 is None
            or context.previous_close is None
        )

    @staticmethod
    def _build_risk_plan(context: BoxSignalContext, params: StrategyParams) -> BoxRiskPlan:
        close_price = float(context.close_price)
        stop_price = context.current_box.support * (1 - float(params.stop_buffer_pct))
        risk_per_share = max(0.0, close_price - stop_price)
        target_price = close_price + max(context.current_box.height, risk_per_share * float(params.rr_min))
        rr_ratio = (target_price - close_price) / risk_per_share if risk_per_share > 0 else None
        return BoxRiskPlan(stop_price=stop_price, target_price=target_price, rr_ratio=rr_ratio)

    def _generate_exit_signal(
        self,
        *,
        context: BoxSignalContext,
        risk_plan: BoxRiskPlan,
        params: StrategyParams,
        entry_price: float,
        holding_days: int,
        entry_signal_reason: Optional[str],
        entry_signal_metadata: Optional[dict],
        position_highest_price_seen: Optional[float],
    ) -> StrategySignal:
        close_price = float(context.close_price)
        ma10 = float(context.ma10)
        pnl_pct = (close_price - entry_price) / entry_price
        breakout_trend_hold_extension = self._detect_breakout_trend_hold_extension(
            entry_signal_reason=entry_signal_reason,
            close_price=close_price,
            ma10=ma10,
            macd_state=context.macd_state,
            holding_days=holding_days,
            params=params,
        )
        exit_metadata = {
            **context.base_metadata,
            **breakout_trend_hold_extension,
        }
        breakeven_signal = self._detect_breakeven_stop(
            entry_signal_reason=entry_signal_reason,
            entry_price=entry_price,
            close_price=close_price,
            position_highest_price_seen=position_highest_price_seen,
            params=params,
        )
        if breakeven_signal:
            return StrategySignal(
                action="sell",
                reason="breakeven_stop",
                score=pnl_pct,
                metadata={
                    **exit_metadata,
                    **breakeven_signal,
                },
            )
        if pnl_pct <= -abs(context.exit_profile.stop_loss_pct):
            return StrategySignal(action="sell", reason="stop_loss_hit", score=pnl_pct, metadata=exit_metadata)
        if pnl_pct >= abs(context.exit_profile.take_profit_pct):
            if not bool(breakout_trend_hold_extension.get("breakout_trend_hold_extension_active")):
                return StrategySignal(action="sell", reason="take_profit_hit", score=pnl_pct, metadata=exit_metadata)
        if bool(context.stall_profile.enable_entry_stall_exit):
            stall_days = max(1, int(context.stall_profile.entry_stall_days))
            stall_min_return_pct = float(context.stall_profile.entry_stall_min_return_pct)
            if holding_days >= stall_days and pnl_pct < stall_min_return_pct:
                return StrategySignal(
                    action="sell",
                    reason="entry_stall_exit",
                    score=pnl_pct,
                    metadata={
                        **exit_metadata,
                        "stall_days": stall_days,
                        "stall_min_return_pct": stall_min_return_pct,
                    },
                )
        pullback_failure_signal = self._detect_pullback_failure_exit(
            working=context.working,
            params=params,
            entry_signal_reason=entry_signal_reason,
            entry_signal_metadata=entry_signal_metadata,
            current_box=context.current_box,
            close_price=close_price,
            pnl_pct=pnl_pct,
            holding_days=holding_days,
        )
        if pullback_failure_signal:
            return StrategySignal(
                action="sell",
                reason="pullback_failure_exit",
                score=pnl_pct,
                metadata={
                    **exit_metadata,
                    **pullback_failure_signal,
                },
            )
        if bool(context.exit_profile.enable_trailing_stop) and position_highest_price_seen and entry_price > 0:
            activate_profit_pct = float(context.exit_profile.trailing_stop_activate_profit_pct)
            trailing_drawdown_pct = float(context.exit_profile.trailing_stop_drawdown_pct)
            peak_profit_pct = (float(position_highest_price_seen) - entry_price) / entry_price
            trailing_drawdown_from_peak = (
                (float(position_highest_price_seen) - close_price) / float(position_highest_price_seen)
                if float(position_highest_price_seen) > 0
                else 0.0
            )
            if peak_profit_pct >= activate_profit_pct and trailing_drawdown_from_peak >= trailing_drawdown_pct:
                return StrategySignal(
                    action="sell",
                    reason="trailing_stop_hit",
                    score=pnl_pct,
                    metadata={
                        **exit_metadata,
                        "position_highest_price_seen": round(float(position_highest_price_seen), 4),
                        "peak_profit_pct": round(peak_profit_pct, 4),
                        "trailing_drawdown_from_peak": round(trailing_drawdown_from_peak, 4),
                        "trailing_stop_activate_profit_pct": activate_profit_pct,
                        "trailing_stop_drawdown_pct": trailing_drawdown_pct,
                    },
                )
        if bool(breakout_trend_hold_extension.get("breakout_trend_hold_extension_limit_hit")):
            return StrategySignal(
                action="sell",
                reason="breakout_trend_extension_max_days_reached",
                score=pnl_pct,
                metadata=exit_metadata,
            )
        if holding_days >= int(context.exit_profile.max_holding_days):
            if not bool(breakout_trend_hold_extension.get("breakout_trend_hold_extension_active")):
                return StrategySignal(
                    action="sell",
                    reason="max_holding_days_reached",
                    score=pnl_pct,
                    metadata=exit_metadata,
                )
        if close_price < risk_plan.stop_price:
            return StrategySignal(action="sell", reason="box_support_failed", score=pnl_pct, metadata=exit_metadata)
        if bool(context.exit_profile.enable_ma10_confirm_exit):
            ma10_confirm_days = max(1, int(context.exit_profile.ma10_confirm_days))
            confirm_window = context.working.tail(ma10_confirm_days)
            if len(confirm_window) >= ma10_confirm_days:
                close_window = pd.to_numeric(confirm_window["close"], errors="coerce")
                ma10_window = pd.to_numeric(confirm_window["ma10"], errors="coerce")
                below_ma10_confirmed = bool(((close_window < ma10_window).fillna(False)).all())
                if below_ma10_confirmed:
                    return StrategySignal(
                        action="sell",
                        reason="close_below_ma10_confirmed",
                        score=pnl_pct,
                        metadata={
                            **exit_metadata,
                            "ma10_confirm_days": ma10_confirm_days,
                        },
                    )
        elif close_price < ma10:
            return StrategySignal(action="sell", reason="close_below_ma10", score=pnl_pct, metadata=exit_metadata)
        return StrategySignal(action="hold", reason="holding", metadata=exit_metadata)

    def _check_entry_preconditions(
        self,
        context: BoxSignalContext,
        params: StrategyParams,
    ) -> Optional[StrategySignal]:
        if bool(params.require_uptrend_for_entry) and context.trend != "uptrend":
            return StrategySignal(action="hold", reason="trend_not_up", metadata=context.base_metadata)
        if context.turnover_rate < context.effective_min_turnover_rate:
            return StrategySignal(action="hold", reason="turnover_rate_too_low", metadata=context.base_metadata)
        if self._turnover_rate_too_high(
            turnover_rate=context.turnover_rate,
            max_turnover_rate=float(params.max_turnover_rate),
        ):
            return StrategySignal(action="hold", reason="turnover_rate_too_high", metadata=context.base_metadata)
        return None

    def _generate_breakout_signal(
        self,
        *,
        context: BoxSignalContext,
        risk_plan: BoxRiskPlan,
        params: StrategyParams,
    ) -> Optional[StrategySignal]:
        close_price = float(context.close_price)
        low_price = float(context.low_price)
        breakout_confirmed = (
            float(context.previous_close) <= context.current_box.resistance
            and close_price > context.current_box.resistance
            and context.pct_chg >= context.breakout_min_breakout_pct
            and context.volume_ratio >= context.breakout_min_volume_ratio
            and self._passes_breakout_body_filter(
                open_price=context.open_price,
                close_price=close_price,
                breakout_min_body_pct=context.breakout_min_body_pct,
            )
            and self._passes_breakout_close_filter(
                close_price=close_price,
                resistance=context.current_box.resistance,
                breakout_min_close_above_resistance_pct=context.breakout_min_close_above_resistance_pct,
            )
            and self._passes_breakout_upper_shadow_filter(
                high_price=self._to_float(context.latest.get("high")),
                low_price=low_price,
                close_price=close_price,
                breakout_max_upper_shadow_ratio=context.breakout_max_upper_shadow_ratio,
            )
            and context.current_box.resistance_touches >= context.breakout_min_box_touches
            and ((close_price - context.current_box.resistance) / context.current_box.resistance)
            <= context.breakout_max_extension_pct
            and self._passes_max_box_height_filter(
                box_height_pct=context.box_height_pct,
                max_box_height_pct=context.breakout_max_box_height_pct,
            )
            and self._passes_avoid_box_height_range_filter(
                box_height_pct=context.box_height_pct,
                low_pct=context.breakout_avoid_box_height_low_pct,
                high_pct=context.breakout_avoid_box_height_high_pct,
            )
            and self._passes_min_stack_lift_filter(
                box_stack_lift_pct=context.box_stack_lift_pct,
                min_stack_lift_pct=context.breakout_min_stack_lift_pct,
            )
            and self._passes_ma10_bias_filter(
                ma10_bias_pct=context.ma10_bias_pct,
                max_bias_ma10_pct=context.breakout_max_bias_ma10_pct,
            )
            and not (bool(params.block_breakout_after_downtrend) and context.recovering_from_downtrend)
        )
        if not breakout_confirmed:
            return None

        breakout_extension_pct = (close_price - context.current_box.resistance) / context.current_box.resistance
        breakout_body_pct = self._calculate_breakout_body_pct(
            open_price=context.open_price,
            close_price=close_price,
        )
        breakout_close_above_resistance_pct = self._calculate_breakout_close_above_resistance_pct(
            close_price=close_price,
            resistance=context.current_box.resistance,
        )
        breakout_upper_shadow_ratio = self._calculate_breakout_upper_shadow_ratio(
            high_price=self._to_float(context.latest.get("high")),
            low_price=low_price,
            close_price=close_price,
        )
        signal_number, breakout_cluster_count = self._estimate_signal_number(
            context.working,
            params=params,
            signal_type="breakout_long",
        )
        quality_score = self._score_breakout_signal(
            trend=context.trend,
            current_box=context.current_box,
            volume_ratio=context.volume_ratio,
            turnover_rate=context.turnover_rate,
            effective_min_turnover_rate=context.effective_min_turnover_rate,
            preferred_turnover_rate_low=context.effective_preferred_turnover_rate_low,
            preferred_turnover_rate_high=context.effective_preferred_turnover_rate_high,
            extension_pct=breakout_extension_pct,
            breakout_body_pct=breakout_body_pct,
            breakout_close_above_resistance_pct=breakout_close_above_resistance_pct,
            breakout_upper_shadow_ratio=breakout_upper_shadow_ratio,
            box_height_pct=context.box_height_pct,
            box_stack_lift_pct=context.box_stack_lift_pct,
            style_bucket=context.style_bucket,
            rr_ratio=risk_plan.rr_ratio,
            signal_number=signal_number,
            params=params,
            breakout_min_volume_ratio=context.breakout_min_volume_ratio,
            breakout_min_box_touches=context.breakout_min_box_touches,
            breakout_max_extension_pct=context.breakout_max_extension_pct,
        )
        macd_score_adjustment = self._calculate_macd_score_adjustment(
            signal_type="breakout_long",
            volume_ratio=context.volume_ratio,
            macd_dif=context.macd_dif,
            macd_dea=context.macd_dea,
            macd_hist=context.macd_hist,
            macd_hist_slope_3=context.macd_hist_slope_3,
            params=params,
        )
        macd_divergence = self._detect_macd_divergence(
            working=context.working,
            signal_type="breakout_long",
            volume_ratio=context.volume_ratio,
            params=params,
        )
        macd_divergence_score_adjustment = self._calculate_macd_divergence_score_adjustment(
            signal_type="breakout_long",
            divergence=macd_divergence,
            params=params,
        )
        quality_score = self._apply_score_adjustment(quality_score, macd_score_adjustment)
        quality_score = self._apply_score_adjustment(quality_score, macd_divergence_score_adjustment)
        if (
            bool(params.enable_macd_divergence_decision)
            and bool(params.breakout_block_macd_bearish_divergence)
            and bool(macd_divergence.get("breakout_macd_bearish_divergence"))
        ):
            return StrategySignal(
                action="hold",
                reason="breakout_macd_bearish_divergence",
                score=quality_score,
                metadata={
                    **context.base_metadata,
                    "signal_type": "breakout_long",
                    "quality_score": quality_score,
                    "macd_score_adjustment": macd_score_adjustment,
                    "macd_divergence_score_adjustment": macd_divergence_score_adjustment,
                    **macd_divergence,
                },
            )
        if quality_score < context.breakout_min_signal_score:
            return StrategySignal(
                action="hold",
                reason="breakout_score_too_low",
                score=quality_score,
                metadata={
                    **context.base_metadata,
                    "signal_type": "breakout_long",
                    "quality_score": quality_score,
                    "macd_score_adjustment": macd_score_adjustment,
                    "macd_divergence_score_adjustment": macd_divergence_score_adjustment,
                    **macd_divergence,
                },
            )
        return StrategySignal(
            action="buy",
            reason="breakout_long",
            score=quality_score,
            metadata={
                **context.base_metadata,
                "signal_type": "breakout_long",
                "signal_number": signal_number,
                "breakout_cluster_count": breakout_cluster_count,
                "signal_number_rule": "count breakout clusters inside lookback window",
                "signal_number_lookback_days": int(params.signal_number_lookback_days),
                "signal_number_event_cooldown_days": int(params.signal_number_event_cooldown_days),
                "quality_score": quality_score,
                "macd_score_adjustment": macd_score_adjustment,
                "macd_divergence_score_adjustment": macd_divergence_score_adjustment,
                "rr_ratio": round(risk_plan.rr_ratio, 4) if risk_plan.rr_ratio is not None else None,
                "entry_price_hint": close_price,
                "stop_price_hint": round(risk_plan.stop_price, 4),
                "target_price_hint": round(risk_plan.target_price, 4),
                **macd_divergence,
                "breakout_extension_pct": round(breakout_extension_pct, 4),
                "breakout_body_pct": (
                    round(breakout_body_pct, 4) if breakout_body_pct is not None else None
                ),
                "breakout_close_above_resistance_pct": round(breakout_close_above_resistance_pct, 4),
                "breakout_upper_shadow_ratio": (
                    round(breakout_upper_shadow_ratio, 4)
                    if breakout_upper_shadow_ratio is not None
                    else None
                ),
            },
        )

    def _generate_pullback_signal(
        self,
        *,
        context: BoxSignalContext,
        risk_plan: BoxRiskPlan,
        params: StrategyParams,
    ) -> Optional[StrategySignal]:
        close_price = float(context.close_price)
        low_price = float(context.low_price)
        pullback_signal = None
        if self._passes_ma10_bias_filter(
            ma10_bias_pct=context.ma10_bias_pct,
            max_bias_ma10_pct=context.pullback_max_bias_ma10_pct,
        ) and self._passes_min_box_height_filter(
            box_height_pct=context.box_height_pct,
            min_box_height_pct=context.pullback_min_box_height_pct,
        ):
            pullback_signal = self._detect_pullback_bounce(
                working=context.working,
                params=params,
                current_box=context.current_box,
                close_price=close_price,
                low_price=low_price,
                open_price=context.open_price,
                volume_ratio=context.volume_ratio,
                pullback_min_volume_ratio=context.pullback_min_volume_ratio,
                pullback_min_box_touches=context.pullback_min_box_touches,
                pullback_reclaim_pct=context.pullback_reclaim_pct,
                pullback_max_break_below_resistance_pct=context.pullback_max_break_below_resistance_pct,
            )
        if not pullback_signal:
            return None

        signal_number, breakout_cluster_count = self._estimate_signal_number(
            context.working,
            params=params,
            signal_type="pullback_bounce",
        )
        quality_score = self._score_pullback_signal(
            trend=context.trend,
            current_box=context.current_box,
            volume_ratio=context.volume_ratio,
            turnover_rate=context.turnover_rate,
            effective_min_turnover_rate=context.effective_min_turnover_rate,
            preferred_turnover_rate_low=context.effective_preferred_turnover_rate_low,
            preferred_turnover_rate_high=context.effective_preferred_turnover_rate_high,
            style_bucket=context.style_bucket,
            pullback_low_vs_resistance_pct=float(pullback_signal["pullback_low_vs_resistance_pct"]),
            pullback_close_above_resistance_pct=float(pullback_signal["pullback_close_above_resistance_pct"]),
            box_height_pct=context.box_height_pct,
            box_stack_lift_pct=context.box_stack_lift_pct,
            rr_ratio=risk_plan.rr_ratio,
            signal_number=signal_number,
            params=params,
            pullback_min_volume_ratio=context.pullback_min_volume_ratio,
            pullback_min_box_touches=context.pullback_min_box_touches,
        )
        macd_score_adjustment = self._calculate_macd_score_adjustment(
            signal_type="pullback_bounce",
            volume_ratio=context.volume_ratio,
            macd_dif=context.macd_dif,
            macd_dea=context.macd_dea,
            macd_hist=context.macd_hist,
            macd_hist_slope_3=context.macd_hist_slope_3,
            params=params,
        )
        macd_divergence = self._detect_macd_divergence(
            working=context.working,
            signal_type="pullback_bounce",
            volume_ratio=context.volume_ratio,
            params=params,
        )
        macd_divergence_score_adjustment = self._calculate_macd_divergence_score_adjustment(
            signal_type="pullback_bounce",
            divergence=macd_divergence,
            params=params,
        )
        pullback_rebound_score_adjustment = self._calculate_pullback_rebound_score_adjustment(
            rebound_risk=context.pullback_rebound_risk,
            profit_power=context.pullback_profit_power,
            params=params,
        )
        quality_score = self._apply_score_adjustment(quality_score, macd_score_adjustment)
        quality_score = self._apply_score_adjustment(quality_score, macd_divergence_score_adjustment)
        quality_score = self._apply_score_adjustment(quality_score, pullback_rebound_score_adjustment)
        if bool(context.pullback_rebound_risk.get("pullback_rebound_blocked")):
            return StrategySignal(
                action="hold",
                reason="pullback_rebound_risk_delayed",
                score=quality_score,
                metadata={
                    **context.base_metadata,
                    "signal_type": "pullback_bounce",
                    "quality_score": quality_score,
                    "macd_score_adjustment": macd_score_adjustment,
                    "macd_divergence_score_adjustment": macd_divergence_score_adjustment,
                    "pullback_rebound_score_adjustment": pullback_rebound_score_adjustment,
                    **macd_divergence,
                    **pullback_signal,
                },
            )
        if quality_score < context.pullback_min_signal_score:
            return StrategySignal(
                action="hold",
                reason="pullback_score_too_low",
                score=quality_score,
                metadata={
                    **context.base_metadata,
                    "signal_type": "pullback_bounce",
                    "quality_score": quality_score,
                    "macd_score_adjustment": macd_score_adjustment,
                    "macd_divergence_score_adjustment": macd_divergence_score_adjustment,
                    "pullback_rebound_score_adjustment": pullback_rebound_score_adjustment,
                    **macd_divergence,
                    **pullback_signal,
                },
            )
        return StrategySignal(
            action="buy",
            reason="pullback_bounce",
            score=quality_score,
            metadata={
                **context.base_metadata,
                "signal_type": "pullback_bounce",
                "signal_number": signal_number,
                "breakout_cluster_count": breakout_cluster_count,
                "signal_number_rule": "pullback is treated as at least the next signal after breakout cluster count",
                "signal_number_lookback_days": int(params.signal_number_lookback_days),
                "signal_number_event_cooldown_days": int(params.signal_number_event_cooldown_days),
                "quality_score": quality_score,
                "macd_score_adjustment": macd_score_adjustment,
                "macd_divergence_score_adjustment": macd_divergence_score_adjustment,
                "pullback_rebound_score_adjustment": pullback_rebound_score_adjustment,
                "rr_ratio": round(risk_plan.rr_ratio, 4) if risk_plan.rr_ratio is not None else None,
                "entry_price_hint": close_price,
                "stop_price_hint": round(risk_plan.stop_price, 4),
                "target_price_hint": round(risk_plan.target_price, 4),
                **macd_divergence,
                **pullback_signal,
            },
        )

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
        pullback_min_volume_ratio: float,
        pullback_min_box_touches: int,
        pullback_reclaim_pct: float,
        pullback_max_break_below_resistance_pct: float,
    ) -> Optional[dict]:
        retest_window = max(2, int(params.breakout_retest_window))
        recent = working.iloc[-retest_window:]
        if recent.empty:
            return None

        recent_high_close = pd.to_numeric(recent["close"], errors="coerce").max()
        had_breakout = self._to_float(recent_high_close) is not None and recent_high_close > current_box.resistance
        touched_zone = low_price <= current_box.resistance * (1 + float(params.box_tolerance_pct))
        break_below_resistance_pct = (
            max(0.0, (current_box.resistance - low_price) / current_box.resistance)
            if current_box.resistance > 0
            else 0.0
        )
        depth_ok = (
            pullback_max_break_below_resistance_pct <= 0
            or break_below_resistance_pct <= pullback_max_break_below_resistance_pct
        )
        reclaimed = close_price >= current_box.resistance * (1 + pullback_reclaim_pct)
        rebound_bar = open_price is None or close_price >= open_price
        enough_volume = volume_ratio >= max(1.0, pullback_min_volume_ratio * 0.8)
        enough_touches = current_box.resistance_touches >= pullback_min_box_touches
        is_valid = bool(
            had_breakout
            and touched_zone
            and depth_ok
            and reclaimed
            and rebound_bar
            and enough_volume
            and enough_touches
        )
        if not is_valid:
            return None
        return {
            "had_breakout": had_breakout,
            "touched_zone": touched_zone,
            "pullback_depth_ok": depth_ok,
            "reclaimed": reclaimed,
            "rebound_bar": rebound_bar,
            "enough_volume": enough_volume,
            "enough_touches": enough_touches,
            "pullback_break_below_resistance_pct": round(break_below_resistance_pct, 4),
            "pullback_low_vs_resistance_pct": round((low_price - current_box.resistance) / current_box.resistance, 4),
            "pullback_close_above_resistance_pct": round((close_price - current_box.resistance) / current_box.resistance, 4),
        }

    def _detect_pullback_failure_exit(
        self,
        *,
        working: pd.DataFrame,
        params: StrategyParams,
        entry_signal_reason: Optional[str],
        entry_signal_metadata: Optional[dict],
        current_box: BoxSnapshot,
        close_price: float,
        pnl_pct: float,
        holding_days: int,
    ) -> Optional[dict]:
        if not bool(params.pullback_enable_failure_exit):
            return None
        if self._normalize_entry_signal_reason(entry_signal_reason) != "pullback":
            return None
        failure_exit_days = max(0, int(params.pullback_failure_exit_days))
        if failure_exit_days > 0 and holding_days > failure_exit_days:
            return None
        if pnl_pct > float(params.pullback_failure_max_profit_pct):
            return None

        confirm_days = max(1, int(params.pullback_failure_confirm_days))
        if len(working) < confirm_days:
            return None

        entry_box_resistance = self._to_float((entry_signal_metadata or {}).get("box_resistance"))
        if entry_box_resistance is None or entry_box_resistance <= 0:
            entry_box_resistance = current_box.resistance
        if entry_box_resistance <= 0:
            return None

        failure_line = entry_box_resistance * (1 - max(0.0, float(params.pullback_failure_buffer_pct)))
        recent_close = pd.to_numeric(working.tail(confirm_days)["close"], errors="coerce")
        if recent_close.isna().any():
            return None
        if not bool((recent_close < failure_line).all()):
            return None
        return {
            "pullback_failure_entry_box_resistance": round(entry_box_resistance, 4),
            "pullback_failure_line": round(failure_line, 4),
            "pullback_failure_confirm_days": confirm_days,
            "pullback_failure_exit_days": failure_exit_days,
            "pullback_failure_buffer_pct": float(params.pullback_failure_buffer_pct),
            "pullback_failure_max_profit_pct": float(params.pullback_failure_max_profit_pct),
            "pullback_failure_close_price": round(close_price, 4),
        }

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
        effective_min_turnover_rate: float,
        preferred_turnover_rate_low: float,
        preferred_turnover_rate_high: float,
        extension_pct: float,
        breakout_body_pct: Optional[float],
        breakout_close_above_resistance_pct: float,
        breakout_upper_shadow_ratio: Optional[float],
        box_height_pct: Optional[float],
        box_stack_lift_pct: Optional[float],
        style_bucket: Optional[str],
        rr_ratio: Optional[float],
        signal_number: int,
        params: StrategyParams,
        breakout_min_volume_ratio: float,
        breakout_min_box_touches: int,
        breakout_max_extension_pct: float,
    ) -> float:
        score = 0.0

        if trend == "uptrend":
            score += 20.0
        elif trend == "sideways":
            score += 10.0

        if current_box.resistance_touches >= max(4, breakout_min_box_touches):
            score += 8.0
        elif current_box.resistance_touches >= breakout_min_box_touches:
            score += 5.0

        if volume_ratio >= breakout_min_volume_ratio * 1.5:
            score += 10.0
        elif volume_ratio >= breakout_min_volume_ratio * 1.2:
            score += 7.0
        elif volume_ratio >= breakout_min_volume_ratio:
            score += 4.0

        score += self._turnover_score_v2(
            turnover_rate,
            min_turnover_rate=effective_min_turnover_rate,
            preferred_turnover_rate_low=preferred_turnover_rate_low,
            preferred_turnover_rate_high=preferred_turnover_rate_high,
        )

        if breakout_body_pct is not None:
            if breakout_body_pct >= 0.03:
                score += 10.0
            elif breakout_body_pct >= 0.02:
                score += 7.0
            elif breakout_body_pct >= 0.01:
                score += 4.0

        if breakout_close_above_resistance_pct >= 0.03:
            score += 10.0
        elif breakout_close_above_resistance_pct >= 0.02:
            score += 7.0
        elif breakout_close_above_resistance_pct >= 0.01:
            score += 4.0

        if breakout_upper_shadow_ratio is not None:
            if breakout_upper_shadow_ratio <= 0.2:
                score += 8.0
            elif breakout_upper_shadow_ratio <= 0.35:
                score += 5.0
            elif breakout_upper_shadow_ratio <= 0.5:
                score += 2.0

        if style_bucket == "balanced_trend":
            score += 4.0
        elif style_bucket == "high_beta":
            score += 2.0
        elif style_bucket == "slow_large":
            score += 1.0

        if rr_ratio is not None:
            if rr_ratio >= 3.0:
                score += 8.0
            elif rr_ratio >= float(params.rr_min):
                score += 5.0
            elif rr_ratio >= max(1.2, float(params.rr_min) * 0.8):
                score += 2.0

        if signal_number == 1:
            score += 7.0
        elif signal_number == 2:
            score += 3.0

        max_extension = max(0.001, breakout_max_extension_pct)
        if extension_pct <= max_extension * 0.3:
            score += 9.0
        elif extension_pct <= max_extension * 0.6:
            score += 6.0
        elif extension_pct <= max_extension * 0.85:
            score += 3.0

        score += self._score_box_stack_lift(box_stack_lift_pct) * float(params.box_stack_lift_score_weight)
        score += self._score_box_height(
            box_height_pct,
            signal_type="breakout_long",
        ) * float(params.box_height_score_weight)
        score += self._score_quality_penalties(
            box_height_pct=box_height_pct,
            turnover_rate=turnover_rate,
            volume_ratio=volume_ratio,
            params=params,
        )

        return round(max(0.0, min(score, 100.0)), 2)

    def _score_pullback_signal(
        self,
        *,
        trend: TrendLabel,
        current_box: BoxSnapshot,
        volume_ratio: float,
        turnover_rate: float,
        effective_min_turnover_rate: float,
        preferred_turnover_rate_low: float,
        preferred_turnover_rate_high: float,
        style_bucket: Optional[str],
        pullback_low_vs_resistance_pct: float,
        pullback_close_above_resistance_pct: float,
        box_height_pct: Optional[float],
        box_stack_lift_pct: Optional[float],
        rr_ratio: Optional[float],
        signal_number: int,
        params: StrategyParams,
        pullback_min_volume_ratio: float,
        pullback_min_box_touches: int,
    ) -> float:
        score = 0.0

        if trend == "uptrend":
            score += 24.0
        elif trend == "sideways":
            score += 12.0

        if current_box.resistance_touches >= max(3, pullback_min_box_touches + 1):
            score += 9.0
        elif current_box.resistance_touches >= pullback_min_box_touches:
            score += 6.0

        if volume_ratio >= pullback_min_volume_ratio * 1.4:
            score += 7.0
        elif volume_ratio >= pullback_min_volume_ratio:
            score += 5.0
        elif volume_ratio >= max(1.0, pullback_min_volume_ratio * 0.8):
            score += 3.0

        score += self._turnover_score_v2(
            turnover_rate,
            min_turnover_rate=effective_min_turnover_rate,
            preferred_turnover_rate_low=preferred_turnover_rate_low,
            preferred_turnover_rate_high=preferred_turnover_rate_high,
        )

        if pullback_close_above_resistance_pct >= 0.035:
            score += 13.0
        elif pullback_close_above_resistance_pct >= 0.02:
            score += 9.0
        elif pullback_close_above_resistance_pct >= 0.01:
            score += 5.0

        if pullback_low_vs_resistance_pct >= -0.01:
            score += 10.0
        elif pullback_low_vs_resistance_pct >= -0.02:
            score += 7.0
        elif pullback_low_vs_resistance_pct >= -0.035:
            score += 4.0

        if style_bucket == "high_beta":
            score += 8.0
        elif style_bucket == "balanced_trend":
            score += 6.0
        elif style_bucket == "slow_large":
            score += 2.0

        if rr_ratio is not None:
            if rr_ratio >= 3.0:
                score += 8.0
            elif rr_ratio >= float(params.rr_min):
                score += 5.0
            elif rr_ratio >= max(1.2, float(params.rr_min) * 0.8):
                score += 2.0

        if signal_number == 2:
            score += 8.0
        elif signal_number == 3:
            score += 4.0

        score += self._score_box_stack_lift(box_stack_lift_pct) * float(params.box_stack_lift_score_weight)
        score += self._score_box_height(
            box_height_pct,
            signal_type="pullback_bounce",
        ) * float(params.box_height_score_weight)
        score += self._score_quality_penalties(
            box_height_pct=box_height_pct,
            turnover_rate=turnover_rate,
            volume_ratio=volume_ratio,
            params=params,
        )

        return round(max(0.0, min(score, 100.0)), 2)

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

    def _build_optional_box_snapshot(self, window: pd.DataFrame, params: StrategyParams) -> Optional[BoxSnapshot]:
        if window is None or window.empty or len(window) < max(5, int(params.box_lookback_days) // 2):
            return None
        return self._build_box_snapshot(window, params)

    @staticmethod
    def _classify_trend(current_box: BoxSnapshot, previous_box: BoxSnapshot) -> TrendLabel:
        if current_box.support > previous_box.support and current_box.resistance > previous_box.resistance:
            return "uptrend"
        if current_box.support < previous_box.support and current_box.resistance < previous_box.resistance:
            return "downtrend"
        return "sideways"

    @staticmethod
    def _ensure_indicators(frame: pd.DataFrame) -> None:
        close = pd.to_numeric(frame["close"], errors="coerce")
        if "ma10" not in frame.columns:
            frame["ma10"] = close.rolling(10, min_periods=1).mean()
        if "volume_ratio" not in frame.columns:
            volume = pd.to_numeric(frame["volume"], errors="coerce")
            avg_volume_5 = volume.rolling(5, min_periods=1).mean().shift(1)
            frame["volume_ratio"] = (volume / avg_volume_5).replace([float("inf"), float("-inf")], pd.NA).fillna(1.0)
        if "turnover_rate" in frame.columns:
            frame["turnover_rate"] = pd.to_numeric(frame["turnover_rate"], errors="coerce")
        if "pct_chg" not in frame.columns:
            frame["pct_chg"] = close.pct_change().fillna(0.0) * 100.0
        if not {"macd_dif", "macd_dea", "macd_hist", "macd_hist_slope_3"}.issubset(frame.columns):
            ema12 = close.ewm(span=12, adjust=False, min_periods=1).mean()
            ema26 = close.ewm(span=26, adjust=False, min_periods=1).mean()
            dif = ema12 - ema26
            dea = dif.ewm(span=9, adjust=False, min_periods=1).mean()
            hist = (dif - dea) * 2.0
            frame["macd_dif"] = dif
            frame["macd_dea"] = dea
            frame["macd_hist"] = hist
            frame["macd_hist_slope_3"] = hist - hist.shift(3)

    @staticmethod
    def _classify_macd_state(
        *,
        macd_dif: Optional[float],
        macd_dea: Optional[float],
        macd_hist: Optional[float],
        macd_hist_slope_3: Optional[float],
    ) -> Optional[str]:
        if macd_dif is None or macd_dea is None or macd_hist is None:
            return None
        if macd_dif > macd_dea and macd_hist > 0:
            return "bullish_expanding" if macd_hist_slope_3 is not None and macd_hist_slope_3 >= 0 else "bullish_fading"
        if macd_dif <= macd_dea and macd_hist <= 0:
            return "bearish_deepening" if macd_hist_slope_3 is not None and macd_hist_slope_3 < 0 else "bearish_repairing"
        return "mixed"

    def _detect_macd_divergence(
        self,
        *,
        working: pd.DataFrame,
        signal_type: str,
        volume_ratio: float,
        params: StrategyParams,
    ) -> dict[str, object]:
        empty = {
            "macd_divergence_detected": False,
            "breakout_macd_bearish_divergence": False,
            "pullback_macd_bullish_divergence": False,
            "macd_divergence_price_confirms": False,
        }
        if not bool(params.enable_macd_divergence_decision):
            return empty
        if working is None or len(working) < 6:
            return empty

        lookback = max(5, int(params.macd_divergence_lookback_days))
        prior = working.iloc[:-1].tail(lookback)
        if prior.empty:
            return empty

        latest = working.iloc[-1]
        latest_dif = self._to_float(latest.get("macd_dif"))
        latest_hist = self._to_float(latest.get("macd_hist"))
        if latest_dif is None or latest_hist is None:
            return empty

        tolerance = max(0.0, float(params.macd_divergence_price_tolerance_pct))
        if signal_type == "breakout_long":
            high_series = pd.to_numeric(prior.get("high"), errors="coerce").dropna()
            if high_series.empty:
                return empty
            reference = working.loc[high_series.idxmax()]
            latest_price = self._to_float(latest.get("high"))
            reference_price = self._to_float(reference.get("high"))
            reference_dif = self._to_float(reference.get("macd_dif"))
            reference_hist = self._to_float(reference.get("macd_hist"))
            if (
                latest_price is None
                or reference_price is None
                or reference_price <= 0
                or reference_dif is None
                or reference_hist is None
            ):
                return empty

            price_confirms = latest_price >= reference_price * (1.0 - tolerance)
            hist_fails = latest_hist < reference_hist
            dif_fails = latest_dif <= reference_dif
            min_volume_ratio = max(0.0, float(params.breakout_macd_bearish_divergence_min_volume_ratio))
            volume_confirms = min_volume_ratio <= 0.0 or float(volume_ratio) >= min_volume_ratio
            detected = bool(price_confirms and hist_fails and dif_fails and volume_confirms)
            return {
                **empty,
                "macd_divergence_detected": detected,
                "breakout_macd_bearish_divergence": detected,
                "macd_divergence_price_confirms": price_confirms,
                "macd_divergence_type": "breakout_bearish" if detected else None,
                "macd_divergence_reference_date": self._date_to_iso(reference.get("date")),
                "macd_divergence_price_delta_pct": round((latest_price - reference_price) / reference_price, 4),
                "macd_divergence_hist_delta": round(latest_hist - reference_hist, 4),
                "macd_divergence_dif_delta": round(latest_dif - reference_dif, 4),
                "macd_divergence_reference_price": round(reference_price, 4),
                "macd_divergence_reference_hist": round(reference_hist, 4),
                "macd_divergence_reference_dif": round(reference_dif, 4),
                "macd_divergence_volume_ratio": round(float(volume_ratio), 4),
            }

        if signal_type == "pullback_bounce":
            low_series = pd.to_numeric(prior.get("low"), errors="coerce").dropna()
            if low_series.empty:
                return empty
            reference = working.loc[low_series.idxmin()]
            latest_price = self._to_float(latest.get("low"))
            reference_price = self._to_float(reference.get("low"))
            reference_dif = self._to_float(reference.get("macd_dif"))
            reference_hist = self._to_float(reference.get("macd_hist"))
            latest_hist_slope_3 = self._to_float(latest.get("macd_hist_slope_3"))
            if (
                latest_price is None
                or reference_price is None
                or reference_price <= 0
                or reference_dif is None
                or reference_hist is None
                or latest_hist_slope_3 is None
            ):
                return empty

            price_confirms = latest_price <= reference_price * (1.0 + tolerance)
            hist_repairs = latest_hist > reference_hist
            dif_repairs = latest_dif >= reference_dif
            hist_rising = latest_hist_slope_3 >= 0
            detected = bool(price_confirms and hist_repairs and dif_repairs and hist_rising)
            return {
                **empty,
                "macd_divergence_detected": detected,
                "pullback_macd_bullish_divergence": detected,
                "macd_divergence_price_confirms": price_confirms,
                "macd_divergence_type": "pullback_bullish" if detected else None,
                "macd_divergence_reference_date": self._date_to_iso(reference.get("date")),
                "macd_divergence_price_delta_pct": round((latest_price - reference_price) / reference_price, 4),
                "macd_divergence_hist_delta": round(latest_hist - reference_hist, 4),
                "macd_divergence_dif_delta": round(latest_dif - reference_dif, 4),
                "macd_divergence_reference_price": round(reference_price, 4),
                "macd_divergence_reference_hist": round(reference_hist, 4),
                "macd_divergence_reference_dif": round(reference_dif, 4),
            }

        return empty

    @staticmethod
    def _calculate_recent_gain_pct(working: pd.DataFrame, *, days: int) -> Optional[float]:
        lookback_days = max(1, int(days))
        if working is None or len(working) <= lookback_days:
            return None
        close_series = pd.to_numeric(working["close"], errors="coerce")
        latest_close = close_series.iloc[-1]
        reference_close = close_series.iloc[-lookback_days - 1]
        if pd.isna(latest_close) or pd.isna(reference_close) or float(reference_close) <= 0:
            return None
        return ((float(latest_close) - float(reference_close)) / float(reference_close)) * 100.0

    @classmethod
    def _detect_breakeven_stop(
        cls,
        *,
        entry_signal_reason: Optional[str],
        entry_price: float,
        close_price: Optional[float],
        position_highest_price_seen: Optional[float],
        params: StrategyParams,
    ) -> Optional[dict[str, object]]:
        if not cls._breakeven_stop_enabled(entry_signal_reason=entry_signal_reason, params=params):
            return None
        if entry_price <= 0 or close_price is None or position_highest_price_seen is None:
            return None
        peak_profit_pct = (float(position_highest_price_seen) - float(entry_price)) / float(entry_price)
        current_profit_pct = (float(close_price) - float(entry_price)) / float(entry_price)
        activate_profit_pct = max(0.0, float(params.breakeven_activate_profit_pct))
        exit_threshold_pct = float(params.breakeven_exit_threshold_pct)
        if peak_profit_pct < activate_profit_pct:
            return None
        if current_profit_pct > exit_threshold_pct:
            return None
        return {
            "breakeven_peak_profit_pct": round(peak_profit_pct, 4),
            "breakeven_current_profit_pct": round(current_profit_pct, 4),
            "breakeven_activate_profit_pct": activate_profit_pct,
            "breakeven_exit_threshold_pct": exit_threshold_pct,
        }

    @classmethod
    def _breakeven_stop_enabled(cls, *, entry_signal_reason: Optional[str], params: StrategyParams) -> bool:
        normalized = cls._normalize_entry_signal_reason(entry_signal_reason)
        if normalized == "breakout" and params.breakout_enable_breakeven_stop is not None:
            return bool(params.breakout_enable_breakeven_stop)
        if normalized == "pullback" and params.pullback_enable_breakeven_stop is not None:
            return bool(params.pullback_enable_breakeven_stop)
        return bool(params.enable_breakeven_stop)

    @staticmethod
    def _detect_pullback_profit_power(*, working: pd.DataFrame, params: StrategyParams) -> dict[str, object]:
        empty = {
            "pullback_profit_power_strong": False,
            "pullback_profit_power_range_pct": None,
            "pullback_profit_power_max_rolling_gain_pct": None,
            "pullback_profit_power_range_pass": False,
            "pullback_profit_power_rolling_gain_pass": False,
        }
        if not bool(params.enable_pullback_profit_power_filter):
            return empty
        if working is None or working.empty:
            return empty

        lookback_days = max(1, int(params.pullback_profit_power_lookback_days))
        rolling_days = max(1, int(params.pullback_profit_power_rolling_gain_days))
        high_series = pd.to_numeric(working.get("high"), errors="coerce")
        low_series = pd.to_numeric(working.get("low"), errors="coerce")
        close_series = pd.to_numeric(working.get("close"), errors="coerce")

        recent_high_low = pd.DataFrame({"high": high_series, "low": low_series}).dropna().tail(lookback_days)
        range_pct = None
        if not recent_high_low.empty:
            min_low = float(recent_high_low["low"].min())
            max_high = float(recent_high_low["high"].max())
            if min_low > 0:
                range_pct = ((max_high - min_low) / min_low) * 100.0

        rolling_gain_pct = None
        close_window = close_series.dropna()
        if len(close_window) > rolling_days:
            gains = ((close_window / close_window.shift(rolling_days)) - 1.0) * 100.0
            max_gain = gains.tail(lookback_days).max()
            if pd.notna(max_gain):
                rolling_gain_pct = float(max_gain)

        range_threshold = float(params.pullback_profit_power_min_range_pct)
        rolling_threshold = float(params.pullback_profit_power_min_rolling_gain_pct)
        range_pass = bool(range_threshold > 0 and range_pct is not None and range_pct >= range_threshold)
        rolling_gain_pass = bool(
            rolling_threshold > 0
            and rolling_gain_pct is not None
            and rolling_gain_pct >= rolling_threshold
        )

        return {
            **empty,
            "pullback_profit_power_strong": bool(range_pass or rolling_gain_pass),
            "pullback_profit_power_range_pct": round(range_pct, 4) if range_pct is not None else None,
            "pullback_profit_power_max_rolling_gain_pct": (
                round(rolling_gain_pct, 4) if rolling_gain_pct is not None else None
            ),
            "pullback_profit_power_range_pass": range_pass,
            "pullback_profit_power_rolling_gain_pass": rolling_gain_pass,
        }

    @staticmethod
    def _detect_pullback_rebound_risk(
        *,
        recovering_from_downtrend: bool,
        recent_gain_pct: Optional[float],
        ma10_bias_pct: Optional[float],
        profit_power: dict[str, object],
        params: StrategyParams,
    ) -> dict[str, object]:
        empty = {
            "pullback_rebound_risk": False,
            "pullback_rebound_recent_gain_hot": False,
            "pullback_rebound_ma10_bias_hot": False,
            "pullback_profit_power_recent_gain_ok": True,
            "pullback_profit_power_ma10_bias_ok": True,
            "pullback_rebound_profit_power_exempted": False,
            "pullback_rebound_blocked": False,
        }
        if not bool(params.enable_pullback_rebound_risk_control):
            return empty
        if not bool(recovering_from_downtrend):
            return empty
        recent_gain_hot = (
            recent_gain_pct is not None
            and recent_gain_pct >= float(params.pullback_rebound_max_recent_gain_pct)
        )
        ma10_bias_hot = (
            ma10_bias_pct is not None
            and ma10_bias_pct >= float(params.pullback_rebound_max_bias_ma10_pct)
        )
        risk = bool(recent_gain_hot or ma10_bias_hot)
        profit_power_recent_gain_ok = bool(
            float(params.pullback_profit_power_max_recent_gain_pct) <= 0
            or recent_gain_pct is None
            or recent_gain_pct <= float(params.pullback_profit_power_max_recent_gain_pct)
        )
        profit_power_ma10_bias_ok = bool(
            float(params.pullback_profit_power_max_ma10_bias_pct) <= 0
            or ma10_bias_pct is None
            or ma10_bias_pct <= float(params.pullback_profit_power_max_ma10_bias_pct)
        )
        profit_power_exempted = bool(
            risk
            and bool(params.enable_pullback_profit_power_filter)
            and bool(profit_power.get("pullback_profit_power_strong"))
            and profit_power_recent_gain_ok
            and profit_power_ma10_bias_ok
        )
        blocked = bool(risk and bool(params.pullback_rebound_block_entry) and not profit_power_exempted)
        return {
            **empty,
            "pullback_rebound_risk": risk,
            "pullback_rebound_recent_gain_hot": bool(recent_gain_hot),
            "pullback_rebound_ma10_bias_hot": bool(ma10_bias_hot),
            "pullback_profit_power_recent_gain_ok": profit_power_recent_gain_ok,
            "pullback_profit_power_ma10_bias_ok": profit_power_ma10_bias_ok,
            "pullback_rebound_profit_power_exempted": profit_power_exempted,
            "pullback_rebound_blocked": blocked,
        }

    @staticmethod
    def _calculate_pullback_rebound_score_adjustment(
        *,
        rebound_risk: dict[str, object],
        profit_power: dict[str, object],
        params: StrategyParams,
    ) -> float:
        if not bool(params.enable_pullback_rebound_risk_control):
            return 0.0
        if not bool(rebound_risk.get("pullback_rebound_risk")):
            return 0.0
        penalty = abs(float(params.pullback_rebound_score_penalty))
        if bool(rebound_risk.get("pullback_rebound_profit_power_exempted")):
            multiplier = max(0.0, float(params.pullback_rebound_profit_power_penalty_multiplier))
            penalty *= multiplier
        return round(-penalty, 2)

    @classmethod
    def _detect_breakout_trend_hold_extension(
        cls,
        *,
        entry_signal_reason: Optional[str],
        close_price: Optional[float],
        ma10: Optional[float],
        macd_state: Optional[str],
        holding_days: int,
        params: StrategyParams,
    ) -> dict[str, object]:
        empty = {
            "breakout_trend_hold_extension_active": False,
            "breakout_trend_hold_extension_limit_hit": False,
            "breakout_trend_hold_extension_close_above_ma10": False,
            "breakout_trend_hold_extension_macd_ok": False,
        }
        if not bool(params.enable_breakout_trend_hold_extension):
            return empty
        if cls._normalize_entry_signal_reason(entry_signal_reason) != "breakout":
            return empty
        max_days = max(1, int(params.breakout_trend_hold_extension_max_days))
        limit_hit = int(holding_days) >= max_days
        close_above_ma10 = bool(
            close_price is not None
            and ma10 is not None
            and float(ma10) > 0
            and float(close_price) >= float(ma10)
        )
        macd_ok = str(macd_state or "") == "bullish_expanding"
        active = bool((not limit_hit) and close_above_ma10 and macd_ok)
        return {
            **empty,
            "breakout_trend_hold_extension_active": active,
            "breakout_trend_hold_extension_limit_hit": bool(limit_hit),
            "breakout_trend_hold_extension_close_above_ma10": close_above_ma10,
            "breakout_trend_hold_extension_macd_ok": macd_ok,
        }

    @staticmethod
    def _calculate_macd_divergence_score_adjustment(
        *,
        signal_type: str,
        divergence: dict[str, object],
        params: StrategyParams,
    ) -> float:
        if not bool(params.enable_macd_divergence_decision):
            return 0.0
        if signal_type == "breakout_long" and bool(divergence.get("breakout_macd_bearish_divergence")):
            return round(-abs(float(params.breakout_macd_bearish_divergence_penalty)), 2)
        if signal_type == "pullback_bounce" and bool(divergence.get("pullback_macd_bullish_divergence")):
            return round(float(params.pullback_macd_bullish_divergence_bonus), 2)
        return 0.0

    @staticmethod
    def _calculate_macd_score_adjustment(
        *,
        signal_type: str,
        volume_ratio: float,
        macd_dif: Optional[float],
        macd_dea: Optional[float],
        macd_hist: Optional[float],
        macd_hist_slope_3: Optional[float],
        params: StrategyParams,
    ) -> float:
        if not bool(params.enable_macd_score_adjustment):
            return 0.0
        if macd_dif is None or macd_dea is None or macd_hist is None:
            return 0.0

        dif_above_dea = macd_dif > macd_dea
        hist_positive = macd_hist > 0
        hist_rising = macd_hist_slope_3 is not None and macd_hist_slope_3 >= 0
        weak_momentum = (not dif_above_dea) or (not hist_positive) or (
            macd_hist_slope_3 is not None and macd_hist_slope_3 < 0
        )

        adjustment = 0.0
        if dif_above_dea and hist_positive and hist_rising:
            adjustment += float(params.macd_bullish_bonus)
        elif (not dif_above_dea) and (not hist_positive):
            adjustment -= abs(float(params.macd_bearish_penalty))

        if signal_type == "breakout_long" and volume_ratio > 4.0 and weak_momentum:
            adjustment -= abs(float(params.breakout_high_volume_macd_weak_penalty))
        if signal_type == "pullback_bounce" and weak_momentum:
            adjustment -= abs(float(params.pullback_macd_weak_penalty))

        return round(adjustment, 2)

    @staticmethod
    def _apply_score_adjustment(score: float, adjustment: float) -> float:
        return round(max(0.0, min(float(score) + float(adjustment), 100.0)), 2)

    @staticmethod
    def _round_optional(value: Optional[float], digits: int = 4) -> Optional[float]:
        return round(float(value), digits) if value is not None else None

    @staticmethod
    def _date_to_iso(value) -> Optional[str]:
        if value is None or value is pd.NA or pd.isna(value):
            return None
        if hasattr(value, "date"):
            return value.date().isoformat()
        return str(value)

    @staticmethod
    def _turnover_score_v2(
        turnover_rate: float,
        *,
        min_turnover_rate: float,
        preferred_turnover_rate_low: float,
        preferred_turnover_rate_high: float,
    ) -> float:
        min_turnover = max(0.0, float(min_turnover_rate))
        preferred_low = max(min_turnover, float(preferred_turnover_rate_low))
        preferred_high = max(preferred_low, float(preferred_turnover_rate_high))
        if turnover_rate >= preferred_low and turnover_rate <= preferred_high:
            return 12.0
        if turnover_rate > preferred_high:
            return 5.0 if turnover_rate <= preferred_high * 1.5 else -4.0
        if turnover_rate >= min_turnover:
            return 3.0
        return -8.0

    @staticmethod
    def _score_quality_penalties(
        *,
        box_height_pct: Optional[float],
        turnover_rate: float,
        volume_ratio: float,
        params: StrategyParams,
    ) -> float:
        penalty = 0.0
        if (
            float(params.score_high_box_height_threshold_pct) > 0
            and box_height_pct is not None
            and box_height_pct > float(params.score_high_box_height_threshold_pct)
        ):
            penalty += abs(float(params.score_high_box_height_penalty))
        if (
            float(params.score_high_turnover_rate_threshold) > 0
            and turnover_rate > float(params.score_high_turnover_rate_threshold)
        ):
            penalty += abs(float(params.score_high_turnover_rate_penalty))
        if (
            float(params.score_high_volume_ratio_threshold) > 0
            and volume_ratio > float(params.score_high_volume_ratio_threshold)
        ):
            penalty += abs(float(params.score_high_volume_ratio_penalty))
        return round(-penalty, 2)

    @staticmethod
    def _turnover_rate_too_high(*, turnover_rate: float, max_turnover_rate: float) -> bool:
        return bool(float(max_turnover_rate) > 0 and float(turnover_rate) > float(max_turnover_rate))

    @staticmethod
    def _normalize_style_bucket(value) -> Optional[str]:
        if value is None or value is pd.NA:
            return None
        normalized = str(value).strip().lower()
        if not normalized or normalized == "nan":
            return None
        return normalized

    @staticmethod
    def _resolve_turnover_profile(style_bucket: Optional[str], params: StrategyParams) -> tuple[float, float, float]:
        if style_bucket == "slow_large":
            return 0.5, 0.8, 3.0
        if style_bucket == "balanced_trend":
            return 1.5, 2.0, 8.0
        if style_bucket == "high_beta":
            return 1.5, 2.0, 12.0
        return (
            float(params.min_turnover_rate),
            float(params.preferred_turnover_rate_low),
            float(params.preferred_turnover_rate_high),
        )

    @staticmethod
    def _resolve_breakout_min_breakout_pct(params: StrategyParams) -> float:
        value = params.breakout_min_breakout_pct
        return float(params.min_breakout_pct if value is None else value)

    @staticmethod
    def _resolve_breakout_min_volume_ratio(params: StrategyParams) -> float:
        value = params.breakout_min_volume_ratio
        return float(params.min_volume_ratio if value is None else value)

    @staticmethod
    def _resolve_breakout_min_body_pct(params: StrategyParams) -> float:
        value = params.breakout_min_body_pct
        return float(0.0 if value is None else value)

    @staticmethod
    def _resolve_breakout_min_close_above_resistance_pct(params: StrategyParams) -> float:
        value = params.breakout_min_close_above_resistance_pct
        return float(0.0 if value is None else value)

    @staticmethod
    def _resolve_breakout_max_upper_shadow_ratio(params: StrategyParams) -> float:
        value = params.breakout_max_upper_shadow_ratio
        return float(1.0 if value is None else value)

    @staticmethod
    def _resolve_pullback_min_volume_ratio(params: StrategyParams) -> float:
        value = params.pullback_min_volume_ratio
        return float(params.min_volume_ratio if value is None else value)

    @staticmethod
    def _resolve_breakout_min_box_touches(params: StrategyParams) -> int:
        value = params.breakout_min_box_touches
        return int(params.min_box_touches if value is None else value)

    @staticmethod
    def _resolve_pullback_min_box_touches(style_bucket: Optional[str], params: StrategyParams) -> int:
        value = AShareBoxStrategy._resolve_pullback_bucket_override(
            style_bucket,
            params,
            "min_box_touches",
        )
        return int(params.min_box_touches if value is None else value)

    @staticmethod
    def _resolve_pullback_reclaim_pct(style_bucket: Optional[str], params: StrategyParams) -> float:
        value = AShareBoxStrategy._resolve_pullback_bucket_override(
            style_bucket,
            params,
            "reclaim_pct",
        )
        return float(params.pullback_reclaim_pct if value is None else value)

    @staticmethod
    def _resolve_pullback_max_break_below_resistance_pct(params: StrategyParams) -> float:
        value = params.pullback_max_break_below_resistance_pct
        return float(0.0 if value is None else value)

    @classmethod
    def _resolve_pullback_bucket_override(
        cls,
        style_bucket: Optional[str],
        params: StrategyParams,
        suffix: str,
    ):
        normalized = cls._normalize_style_bucket(style_bucket)
        if not normalized:
            return getattr(params, f"pullback_{suffix}", None)
        attr_name = f"pullback_{normalized}_{suffix}"
        if hasattr(params, attr_name):
            value = getattr(params, attr_name)
            if value is not None:
                return value
        return getattr(params, f"pullback_{suffix}", None)

    @staticmethod
    def _resolve_breakout_max_extension_pct(params: StrategyParams) -> float:
        value = params.breakout_max_extension_pct
        return float(params.max_breakout_extension_pct if value is None else value)

    @staticmethod
    def _resolve_breakout_max_box_height_pct(params: StrategyParams) -> float:
        value = params.breakout_max_box_height_pct
        return float(0.0 if value is None else value)

    @staticmethod
    def _resolve_pullback_min_box_height_pct(params: StrategyParams) -> float:
        value = params.pullback_min_box_height_pct
        return float(0.0 if value is None else value)

    @staticmethod
    def _resolve_breakout_max_bias_ma10_pct(params: StrategyParams) -> float:
        value = params.breakout_max_bias_ma10_pct
        return float(params.max_bias_ma10_pct if value is None else value)

    @staticmethod
    def _resolve_pullback_max_bias_ma10_pct(params: StrategyParams) -> float:
        value = params.pullback_max_bias_ma10_pct
        return float(params.max_bias_ma10_pct if value is None else value)

    @staticmethod
    def _resolve_breakout_min_signal_score(params: StrategyParams) -> float:
        value = params.breakout_min_signal_score
        return float(params.min_signal_score if value is None else value)

    @staticmethod
    def _resolve_pullback_min_signal_score(params: StrategyParams) -> float:
        value = params.pullback_min_signal_score
        return float(params.min_signal_score if value is None else value)

    @classmethod
    def _resolve_exit_profile(
        cls,
        entry_signal_reason: Optional[str],
        style_bucket: Optional[str],
        params: StrategyParams,
    ) -> ExitProfile:
        prefix = cls._normalize_entry_signal_reason(entry_signal_reason)
        return ExitProfile(
            stop_loss_pct=cls._resolve_exit_float(prefix, params, "stop_loss_pct"),
            take_profit_pct=cls._resolve_exit_float(prefix, params, "take_profit_pct"),
            max_holding_days=cls._resolve_exit_int(prefix, params, "max_holding_days"),
            enable_trailing_stop=cls._resolve_style_aware_exit_bool(
                prefix,
                style_bucket,
                params,
                "enable_trailing_stop",
            ),
            trailing_stop_activate_profit_pct=cls._resolve_style_aware_exit_float(
                prefix,
                style_bucket,
                params,
                "trailing_stop_activate_profit_pct",
            ),
            trailing_stop_drawdown_pct=cls._resolve_style_aware_exit_float(
                prefix,
                style_bucket,
                params,
                "trailing_stop_drawdown_pct",
            ),
            enable_ma10_confirm_exit=cls._resolve_exit_bool(prefix, params, "enable_ma10_confirm_exit"),
            ma10_confirm_days=cls._resolve_exit_int(prefix, params, "ma10_confirm_days"),
        )

    @classmethod
    def _resolve_stall_profile(
        cls,
        entry_signal_reason: Optional[str],
        style_bucket: Optional[str],
        params: StrategyParams,
    ) -> StallProfile:
        prefix = cls._normalize_entry_signal_reason(entry_signal_reason)
        return StallProfile(
            enable_entry_stall_exit=cls._resolve_style_aware_exit_bool(
                prefix,
                style_bucket,
                params,
                "enable_entry_stall_exit",
            ),
            entry_stall_days=cls._resolve_style_aware_exit_int(
                prefix,
                style_bucket,
                params,
                "entry_stall_days",
            ),
            entry_stall_min_return_pct=cls._resolve_style_aware_exit_float(
                prefix,
                style_bucket,
                params,
                "entry_stall_min_return_pct",
            ),
        )

    @staticmethod
    def _normalize_entry_signal_reason(entry_signal_reason: Optional[str]) -> Optional[str]:
        if not entry_signal_reason:
            return None
        normalized = str(entry_signal_reason).strip().lower()
        if normalized == "breakout_long":
            return "breakout"
        if normalized == "pullback_bounce":
            return "pullback"
        return None

    @staticmethod
    def _resolve_exit_attr_name(prefix: Optional[str], attr_name: str) -> Optional[str]:
        if prefix is None:
            return None
        return f"{prefix}_{attr_name}"

    @classmethod
    def _resolve_exit_float(cls, prefix: Optional[str], params: StrategyParams, attr_name: str) -> float:
        override_name = cls._resolve_exit_attr_name(prefix, attr_name)
        override_value = getattr(params, override_name) if override_name is not None else None
        base_value = getattr(params, attr_name)
        return float(base_value if override_value is None else override_value)

    @classmethod
    def _resolve_exit_int(cls, prefix: Optional[str], params: StrategyParams, attr_name: str) -> int:
        override_name = cls._resolve_exit_attr_name(prefix, attr_name)
        override_value = getattr(params, override_name) if override_name is not None else None
        base_value = getattr(params, attr_name)
        return int(base_value if override_value is None else override_value)

    @classmethod
    def _resolve_exit_bool(cls, prefix: Optional[str], params: StrategyParams, attr_name: str) -> bool:
        override_name = cls._resolve_exit_attr_name(prefix, attr_name)
        override_value = getattr(params, override_name) if override_name is not None else None
        base_value = getattr(params, attr_name)
        return bool(base_value if override_value is None else override_value)

    @classmethod
    def _resolve_style_aware_exit_float(
        cls,
        prefix: Optional[str],
        style_bucket: Optional[str],
        params: StrategyParams,
        attr_name: str,
    ) -> float:
        if prefix == "pullback":
            bucket_override = cls._resolve_pullback_style_exit_override(style_bucket, params, attr_name)
            if bucket_override is not None:
                return float(bucket_override)
        return cls._resolve_exit_float(prefix, params, attr_name)

    @classmethod
    def _resolve_style_aware_exit_int(
        cls,
        prefix: Optional[str],
        style_bucket: Optional[str],
        params: StrategyParams,
        attr_name: str,
    ) -> int:
        if prefix == "pullback":
            bucket_override = cls._resolve_pullback_style_exit_override(style_bucket, params, attr_name)
            if bucket_override is not None:
                return int(bucket_override)
        return cls._resolve_exit_int(prefix, params, attr_name)

    @classmethod
    def _resolve_style_aware_exit_bool(
        cls,
        prefix: Optional[str],
        style_bucket: Optional[str],
        params: StrategyParams,
        attr_name: str,
    ) -> bool:
        if prefix == "pullback":
            bucket_override = cls._resolve_pullback_style_exit_override(style_bucket, params, attr_name)
            if bucket_override is not None:
                return bool(bucket_override)
        return cls._resolve_exit_bool(prefix, params, attr_name)

    @classmethod
    def _resolve_pullback_style_exit_override(
        cls,
        style_bucket: Optional[str],
        params: StrategyParams,
        attr_name: str,
    ):
        normalized = cls._normalize_style_bucket(style_bucket)
        if not normalized:
            return None
        bucket_attr = f"pullback_{normalized}_{attr_name}"
        if hasattr(params, bucket_attr):
            value = getattr(params, bucket_attr)
            if value is not None:
                return value
        return None

    @staticmethod
    def _passes_breakout_body_filter(
        *,
        open_price: Optional[float],
        close_price: float,
        breakout_min_body_pct: float,
    ) -> bool:
        if breakout_min_body_pct <= 0 or open_price is None or open_price <= 0:
            return True
        body_pct = ((close_price - open_price) / open_price) * 100.0
        return body_pct >= breakout_min_body_pct

    @staticmethod
    def _calculate_ma10_bias_pct(*, close_price: Optional[float], ma10: Optional[float]) -> Optional[float]:
        if close_price is None or ma10 is None or ma10 <= 0:
            return None
        return ((close_price - ma10) / ma10) * 100.0

    @staticmethod
    def _calculate_box_height_pct(box: BoxSnapshot) -> Optional[float]:
        if box.support <= 0:
            return None
        return (box.height / box.support) * 100.0

    @staticmethod
    def _calculate_box_stack_lift_pct(current_box: BoxSnapshot, previous_box: BoxSnapshot) -> Optional[float]:
        if previous_box.support <= 0 or previous_box.resistance <= 0:
            return None
        support_lift_pct = ((current_box.support - previous_box.support) / previous_box.support) * 100.0
        resistance_lift_pct = ((current_box.resistance - previous_box.resistance) / previous_box.resistance) * 100.0
        return min(support_lift_pct, resistance_lift_pct)

    @staticmethod
    def _score_box_stack_lift(box_stack_lift_pct: Optional[float]) -> float:
        if box_stack_lift_pct is None:
            return 0.0
        if box_stack_lift_pct > 10.0:
            return 7.0
        if box_stack_lift_pct > 5.0:
            return 5.0
        if box_stack_lift_pct > 0.0:
            return -3.0
        return -8.0

    @staticmethod
    def _score_box_height(box_height_pct: Optional[float], *, signal_type: str) -> float:
        if box_height_pct is None:
            return 0.0
        if signal_type == "pullback_bounce":
            if box_height_pct > 30.0:
                return 4.0
            if box_height_pct > 20.0:
                return 6.0
            if box_height_pct > 12.0:
                return 0.0
            return -4.0
        if box_height_pct > 30.0:
            return 2.0
        if box_height_pct > 20.0:
            return 6.0
        if box_height_pct > 12.0:
            return -2.0
        return 4.0

    @staticmethod
    def _passes_max_box_height_filter(
        *,
        box_height_pct: Optional[float],
        max_box_height_pct: float,
    ) -> bool:
        if max_box_height_pct <= 0 or box_height_pct is None:
            return True
        return box_height_pct <= max_box_height_pct

    @staticmethod
    def _passes_min_box_height_filter(
        *,
        box_height_pct: Optional[float],
        min_box_height_pct: float,
    ) -> bool:
        if min_box_height_pct <= 0 or box_height_pct is None:
            return True
        return box_height_pct >= min_box_height_pct

    @staticmethod
    def _passes_avoid_box_height_range_filter(
        *,
        box_height_pct: Optional[float],
        low_pct: float,
        high_pct: float,
    ) -> bool:
        if low_pct <= 0 or high_pct <= low_pct or box_height_pct is None:
            return True
        return not (low_pct < box_height_pct <= high_pct)

    @staticmethod
    def _passes_min_stack_lift_filter(
        *,
        box_stack_lift_pct: Optional[float],
        min_stack_lift_pct: float,
    ) -> bool:
        if min_stack_lift_pct <= 0 or box_stack_lift_pct is None:
            return True
        return box_stack_lift_pct >= min_stack_lift_pct

    @staticmethod
    def _passes_ma10_bias_filter(
        *,
        ma10_bias_pct: Optional[float],
        max_bias_ma10_pct: float,
    ) -> bool:
        if max_bias_ma10_pct <= 0 or ma10_bias_pct is None:
            return True
        return ma10_bias_pct <= max_bias_ma10_pct

    @staticmethod
    def _passes_breakout_close_filter(
        *,
        close_price: float,
        resistance: float,
        breakout_min_close_above_resistance_pct: float,
    ) -> bool:
        if breakout_min_close_above_resistance_pct <= 0 or resistance <= 0:
            return True
        close_above_resistance_pct = (close_price - resistance) / resistance
        return close_above_resistance_pct >= breakout_min_close_above_resistance_pct

    @staticmethod
    def _passes_breakout_upper_shadow_filter(
        *,
        high_price: Optional[float],
        low_price: float,
        close_price: float,
        breakout_max_upper_shadow_ratio: float,
    ) -> bool:
        if breakout_max_upper_shadow_ratio >= 1.0 or high_price is None:
            return True
        full_range = high_price - low_price
        if full_range <= 0:
            return True
        upper_shadow_ratio = max(0.0, high_price - close_price) / full_range
        return upper_shadow_ratio <= breakout_max_upper_shadow_ratio

    @staticmethod
    def _calculate_breakout_body_pct(*, open_price: Optional[float], close_price: float) -> Optional[float]:
        if open_price is None or open_price <= 0:
            return None
        return ((close_price - open_price) / open_price) * 100.0

    @staticmethod
    def _calculate_breakout_close_above_resistance_pct(*, close_price: float, resistance: float) -> float:
        if resistance <= 0:
            return 0.0
        return (close_price - resistance) / resistance

    @staticmethod
    def _calculate_breakout_upper_shadow_ratio(
        *,
        high_price: Optional[float],
        low_price: float,
        close_price: float,
    ) -> Optional[float]:
        if high_price is None:
            return None
        full_range = high_price - low_price
        if full_range <= 0:
            return 0.0
        return max(0.0, high_price - close_price) / full_range

    @staticmethod
    def _to_float(value) -> Optional[float]:
        if value is None or value is pd.NA:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
