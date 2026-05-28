# -*- coding: utf-8 -*-
"""Minimal single-position backtest engine for daily-bar strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

import pandas as pd

from theme_picker.backtest.metrics import calculate_metrics
from theme_picker.backtest.models import BacktestConfig, BacktestResult, EquityPoint, Position, Trade
from theme_picker.strategy.base import Strategy
from theme_picker.strategy.params import StrategyParams


@dataclass(slots=True)
class _PendingOrder:
    action: str
    signal_date: date
    reason: str
    score: Optional[float] = None
    metadata: dict = field(default_factory=dict)


class BacktestEngine:
    """Run a single-symbol, single-position daily-bar backtest."""

    def run(
        self,
        *,
        stock_code: str,
        bars: pd.DataFrame,
        strategy: Strategy,
        params: StrategyParams,
        config: Optional[BacktestConfig] = None,
    ) -> BacktestResult:
        if bars is None or bars.empty:
            raise ValueError(f"没有可用于回测的K线数据: {stock_code}")

        runtime_config = config or BacktestConfig()
        working = bars.copy().sort_values("date").reset_index(drop=True)
        working["date"] = pd.to_datetime(working["date"], errors="coerce")

        cash = float(runtime_config.initial_cash)
        position: Optional[Position] = None
        trades: List[Trade] = []
        equity_curve: List[EquityPoint] = []
        notes = [
            "当前为单票、单仓位、信号次日开盘近似成交的最小回测骨架。",
            f"价格口径: {runtime_config.price_adjustment}。",
            f"交易约束模式: {runtime_config.trading_constraint_mode}。",
        ]
        latest_signal_metadata: dict[str, object] = {}
        symbol_loss_streak = 0
        symbol_loss_cooldown_until: Optional[date] = None
        pending_order: Optional[_PendingOrder] = None

        for index in range(len(working)):
            row = working.iloc[index]
            trade_date = row["date"].date()
            close_price = self._to_float(row.get("close"))
            if close_price is None or close_price <= 0:
                continue
            execution_price = self._resolve_execution_price(row)

            if pending_order is not None and execution_price is not None:
                order = pending_order
                pending_order = None
                if order.action == "buy" and position is None:
                    cooldown_block_reason = self._symbol_loss_cooldown_block_reason(
                        trade_date=trade_date,
                        params=params,
                        cooldown_until=symbol_loss_cooldown_until,
                    )
                    buy_block_reason = self._buy_block_reason(row, runtime_config)
                    if cooldown_block_reason is not None:
                        notes.append(
                            f"{trade_date.isoformat()} 买入信号({order.signal_date.isoformat()})因{cooldown_block_reason}被跳过。"
                        )
                    elif buy_block_reason is not None:
                        notes.append(
                            f"{trade_date.isoformat()} 买入信号({order.signal_date.isoformat()})因{buy_block_reason}被跳过。"
                        )
                    else:
                        position = self._open_position(
                            stock_code=stock_code,
                            trade_date=trade_date,
                            execution_price=execution_price,
                            cash=cash,
                            signal_reason=order.reason,
                            signal_score=order.score,
                            signal_metadata=order.metadata,
                            params=params,
                            config=runtime_config,
                        )
                        if position is not None:
                            cost = self._trade_cost(position.entry_price, position.shares, runtime_config)
                            cash -= position.entry_price * position.shares + cost
                elif order.action == "sell" and position is not None:
                    can_exit = not runtime_config.enforce_t_plus_one or trade_date > position.entry_date
                    if not can_exit:
                        notes.append(f"{trade_date.isoformat()} 卖出信号因 T+1 约束延后。")
                        pending_order = order
                    else:
                        sell_block_reason = self._sell_block_reason(row, runtime_config)
                        if sell_block_reason is not None:
                            notes.append(
                                f"{trade_date.isoformat()} 卖出信号({order.signal_date.isoformat()})因{sell_block_reason}被跳过。"
                            )
                        else:
                            trade = self._close_position(
                                position=position,
                                trade_date=trade_date,
                                execution_price=execution_price,
                                exit_reason=order.reason,
                                config=runtime_config,
                            )
                            cash += trade.exit_price * trade.shares - self._trade_cost(trade.exit_price, trade.shares, runtime_config)
                            trades.append(trade)
                            symbol_loss_streak, symbol_loss_cooldown_until = self._update_symbol_loss_cooldown(
                                trade=trade,
                                params=params,
                                current_loss_streak=symbol_loss_streak,
                                current_cooldown_until=symbol_loss_cooldown_until,
                            )
                            position = None

            if position is not None:
                self._update_position_excursion(position, row)

            holding_days = 0
            entry_price = None
            if position is not None:
                holding_days = max(0, (trade_date - position.entry_date).days)
                entry_price = position.entry_price

            signal = strategy.generate_signal(
                working,
                current_index=index,
                params=params,
                price_adjustment=runtime_config.price_adjustment,
                has_position=position is not None,
                entry_price=entry_price,
                holding_days=holding_days,
                entry_signal_reason=(position.entry_signal_reason if position is not None else None),
                entry_signal_metadata=(
                    dict(position.entry_signal_metadata or {}) if position is not None else None
                ),
                position_highest_price_seen=(
                    float(position.highest_price_seen) if position is not None else None
                ),
            )
            latest_signal_metadata = self._sanitize_json_value(signal.metadata or {})

            if pending_order is None and position is None and signal.action == "buy":
                cooldown_block_reason = self._symbol_loss_cooldown_block_reason(
                    trade_date=trade_date,
                    params=params,
                    cooldown_until=symbol_loss_cooldown_until,
                )
                if cooldown_block_reason is not None:
                    notes.append(f"{trade_date.isoformat()} 买入信号因{cooldown_block_reason}被跳过。")
                else:
                    pending_order = _PendingOrder(
                        action="buy",
                        signal_date=trade_date,
                        reason=signal.reason,
                        score=signal.score,
                        metadata=self._sanitize_json_value(signal.metadata or {}),
                    )
            elif pending_order is None and position is not None and signal.action == "sell":
                pending_order = _PendingOrder(
                    action="sell",
                    signal_date=trade_date,
                    reason=signal.reason,
                    score=signal.score,
                    metadata=self._sanitize_json_value(signal.metadata or {}),
                )

            market_value = 0.0
            if position is not None:
                market_value = position.shares * close_price
            equity_curve.append(
                EquityPoint(
                    trade_date=trade_date,
                    cash=round(cash, 2),
                    market_value=round(market_value, 2),
                    equity=round(cash + market_value, 2),
                )
            )

        final_equity = equity_curve[-1].equity if equity_curve else cash
        metrics = calculate_metrics(
            trades=trades,
            equity_curve=equity_curve,
            initial_cash=float(runtime_config.initial_cash),
            final_equity=float(final_equity),
            open_position=position,
            latest_close=close_price if "close_price" in locals() else None,
        )
        return BacktestResult(
            strategy_name=strategy.name,
            stock_code=stock_code,
            start_date=working.iloc[0]["date"].date().isoformat(),
            end_date=working.iloc[-1]["date"].date().isoformat(),
            config=runtime_config.to_dict(),
            params=params.to_dict(),
            metrics=metrics,
            data_context={
                "price_adjustment": runtime_config.price_adjustment,
                "trading_constraint_mode": runtime_config.trading_constraint_mode,
                "columns": [str(column) for column in working.columns],
                "has_raw_close": "raw_close" in working.columns,
                "has_pre_close": "pre_close" in working.columns,
                "has_raw_pct_chg": "raw_pct_chg" in working.columns,
                "has_turnover_rate": "turnover_rate" in working.columns,
                "has_up_limit": "up_limit" in working.columns,
                "has_down_limit": "down_limit" in working.columns,
                "has_is_suspended": "is_suspended" in working.columns,
                "latest_signal_metadata": latest_signal_metadata,
            },
            open_position=position,
            trades=trades,
            equity_curve=equity_curve,
            notes=notes,
        )

    def _open_position(
        self,
        *,
        stock_code: str,
        trade_date,
        execution_price: float,
        cash: float,
        signal_reason: str,
        signal_score: Optional[float],
        signal_metadata: Optional[dict],
        params: StrategyParams,
        config: BacktestConfig,
    ) -> Optional[Position]:
        budget = max(0.0, cash * float(params.position_size_pct))
        entry_price = execution_price * (1 + (config.slippage_bps / 10000.0))
        commission_multiplier = 1 + (config.commission_bps / 10000.0)
        gross_unit_cost = entry_price * commission_multiplier
        if gross_unit_cost <= 0:
            return None
        raw_shares = int(budget // gross_unit_cost)
        shares = (raw_shares // int(config.lot_size)) * int(config.lot_size)
        if shares <= 0:
            return None
        return Position(
            stock_code=stock_code,
            entry_date=trade_date,
            entry_price=round(entry_price, 4),
            shares=shares,
            highest_price_seen=round(entry_price, 4),
            lowest_price_seen=round(entry_price, 4),
            entry_signal_reason=signal_reason,
            entry_signal_score=(round(float(signal_score), 4) if signal_score is not None else None),
            entry_signal_metadata=self._build_entry_signal_snapshot(signal_metadata),
        )

    def _close_position(
        self,
        *,
        position: Position,
        trade_date,
        execution_price: float,
        exit_reason: str,
        config: BacktestConfig,
    ) -> Trade:
        exit_price = execution_price * (1 - (config.slippage_bps / 10000.0))
        gross_pnl = (exit_price - position.entry_price) * position.shares
        entry_cost = self._trade_cost(position.entry_price, position.shares, config)
        exit_cost = self._trade_cost(exit_price, position.shares, config)
        net_pnl = gross_pnl - entry_cost - exit_cost
        holding_days = max(0, (trade_date - position.entry_date).days)
        invested = position.entry_price * position.shares
        return_pct = (net_pnl / invested * 100.0) if invested else 0.0
        highest_price_seen = float(position.highest_price_seen or position.entry_price)
        lowest_price_seen = float(position.lowest_price_seen or position.entry_price)
        max_favorable_excursion_pct = ((highest_price_seen - position.entry_price) / position.entry_price * 100.0) if position.entry_price else 0.0
        max_adverse_excursion_pct = ((lowest_price_seen - position.entry_price) / position.entry_price * 100.0) if position.entry_price else 0.0
        return Trade(
            stock_code=position.stock_code,
            entry_date=position.entry_date,
            exit_date=trade_date,
            entry_price=round(position.entry_price, 4),
            exit_price=round(exit_price, 4),
            shares=position.shares,
            gross_pnl=round(gross_pnl, 2),
            net_pnl=round(net_pnl, 2),
            return_pct=round(return_pct, 2),
            holding_days=holding_days,
            entry_signal_reason=position.entry_signal_reason,
            entry_signal_score=(
                round(float(position.entry_signal_score), 4)
                if position.entry_signal_score is not None
                else None
            ),
            entry_signal_metadata=dict(position.entry_signal_metadata or {}),
            exit_reason=exit_reason,
            highest_price_seen=round(highest_price_seen, 4),
            lowest_price_seen=round(lowest_price_seen, 4),
            max_favorable_excursion_pct=round(max_favorable_excursion_pct, 2),
            max_adverse_excursion_pct=round(max_adverse_excursion_pct, 2),
        )

    @staticmethod
    def _trade_cost(price: float, shares: int, config: BacktestConfig) -> float:
        turnover = float(price) * int(shares)
        return turnover * (float(config.commission_bps) / 10000.0)

    @classmethod
    def _resolve_execution_price(cls, row: pd.Series) -> Optional[float]:
        open_price = cls._to_float(row.get("open"))
        if open_price is not None and open_price > 0:
            return open_price
        close_price = cls._to_float(row.get("close"))
        if close_price is not None and close_price > 0:
            return close_price
        return None

    @classmethod
    def _symbol_loss_cooldown_block_reason(
        cls,
        *,
        trade_date: date,
        params: StrategyParams,
        cooldown_until: Optional[date],
    ) -> Optional[str]:
        if not cls._symbol_loss_cooldown_enabled(params) or cooldown_until is None:
            return None
        if trade_date <= cooldown_until:
            return f"单股连续亏损冷却至 {cooldown_until.isoformat()}"
        return None

    @classmethod
    def _update_symbol_loss_cooldown(
        cls,
        *,
        trade: Trade,
        params: StrategyParams,
        current_loss_streak: int,
        current_cooldown_until: Optional[date],
    ) -> tuple[int, Optional[date]]:
        if not cls._symbol_loss_cooldown_enabled(params):
            return current_loss_streak, current_cooldown_until
        if float(trade.net_pnl or 0.0) >= 0:
            return 0, current_cooldown_until

        loss_streak = int(current_loss_streak) + 1
        trigger_losses = max(1, int(params.symbol_loss_cooldown_losses))
        if loss_streak < trigger_losses:
            return loss_streak, current_cooldown_until

        cooldown_days = max(0, int(params.symbol_loss_cooldown_days))
        return 0, trade.exit_date + timedelta(days=cooldown_days)

    @staticmethod
    def _symbol_loss_cooldown_enabled(params: StrategyParams) -> bool:
        return (
            bool(params.enable_symbol_loss_cooldown)
            and int(params.symbol_loss_cooldown_losses) > 0
            and int(params.symbol_loss_cooldown_days) >= 0
        )

    @classmethod
    def _build_entry_signal_snapshot(cls, metadata: Optional[dict]) -> dict:
        if not isinstance(metadata, dict):
            return {}
        allowlist = {
            "signal_type",
            "signal_strategy",
            "stock_signal",
            "strategy_label",
            "target_decision_label",
            "target_decision_matched",
            "signal_number",
            "quality_score",
            "trend_score",
            "trend",
            "trend_status",
            "previous_trend",
            "recovering_from_downtrend",
            "style_bucket",
            "buy_signal",
            "pattern",
            "box_support",
            "box_resistance",
            "box_height",
            "box_height_pct",
            "box_stack_lift_pct",
            "support_touches",
            "resistance_touches",
            "close_price",
            "ma5",
            "ma10",
            "ma20",
            "ma60",
            "bias_ma5",
            "bias_ma10",
            "bias_ma20",
            "ma10_bias_pct",
            "pct_chg",
            "volume_ratio",
            "turnover_rate",
            "support",
            "pressure",
            "turnover_rate_median_20",
            "atr_pct_20",
            "macd_dif",
            "macd_dea",
            "macd_hist",
            "macd_hist_slope_3",
            "macd_dif_above_dea",
            "macd_above_zero",
            "macd_hist_rising_3",
            "macd_state",
            "macd_score_adjustment",
            "effective_enable_macd_score_adjustment",
            "effective_macd_bullish_bonus",
            "effective_macd_bearish_penalty",
            "effective_breakout_high_volume_macd_weak_penalty",
            "effective_pullback_macd_weak_penalty",
            "effective_enable_macd_divergence_decision",
            "effective_macd_divergence_lookback_days",
            "effective_macd_divergence_price_tolerance_pct",
            "effective_breakout_macd_bearish_divergence_min_volume_ratio",
            "effective_breakout_macd_bearish_divergence_penalty",
            "effective_breakout_block_macd_bearish_divergence",
            "effective_pullback_macd_bullish_divergence_bonus",
            "macd_divergence_detected",
            "breakout_macd_bearish_divergence",
            "pullback_macd_bullish_divergence",
            "macd_divergence_price_confirms",
            "macd_divergence_type",
            "macd_divergence_score_adjustment",
            "macd_divergence_reference_date",
            "macd_divergence_price_delta_pct",
            "macd_divergence_hist_delta",
            "macd_divergence_dif_delta",
            "macd_divergence_reference_price",
            "macd_divergence_reference_hist",
            "macd_divergence_reference_dif",
            "macd_divergence_volume_ratio",
            "effective_enable_pullback_rebound_risk_control",
            "effective_pullback_rebound_recent_gain_days",
            "effective_pullback_rebound_max_recent_gain_pct",
            "effective_pullback_rebound_max_bias_ma10_pct",
            "effective_pullback_rebound_score_penalty",
            "effective_pullback_rebound_block_entry",
            "effective_enable_pullback_profit_power_filter",
            "effective_pullback_profit_power_lookback_days",
            "effective_pullback_profit_power_min_range_pct",
            "effective_pullback_profit_power_rolling_gain_days",
            "effective_pullback_profit_power_min_rolling_gain_pct",
            "effective_pullback_profit_power_max_recent_gain_pct",
            "effective_pullback_profit_power_max_ma10_bias_pct",
            "effective_pullback_rebound_profit_power_penalty_multiplier",
            "pullback_rebound_recent_gain_pct",
            "pullback_profit_power_strong",
            "pullback_profit_power_range_pct",
            "pullback_profit_power_max_rolling_gain_pct",
            "pullback_profit_power_range_pass",
            "pullback_profit_power_rolling_gain_pass",
            "pullback_rebound_risk",
            "pullback_rebound_recent_gain_hot",
            "pullback_rebound_ma10_bias_hot",
            "pullback_profit_power_recent_gain_ok",
            "pullback_profit_power_ma10_bias_ok",
            "pullback_rebound_profit_power_exempted",
            "pullback_rebound_blocked",
            "pullback_rebound_score_adjustment",
            "effective_enable_breakout_trend_hold_extension",
            "effective_breakout_trend_hold_extension_max_days",
            "breakout_trend_hold_extension_active",
            "breakout_trend_hold_extension_limit_hit",
            "breakout_trend_hold_extension_close_above_ma10",
            "breakout_trend_hold_extension_macd_ok",
            "rr_ratio",
            "entry_price_hint",
            "stop_price_hint",
            "target_price_hint",
            "effective_min_turnover_rate",
            "effective_preferred_turnover_rate_low",
            "effective_preferred_turnover_rate_high",
            "effective_max_turnover_rate",
            "effective_score_high_box_height_threshold_pct",
            "effective_score_high_box_height_penalty",
            "effective_score_high_turnover_rate_threshold",
            "effective_score_high_turnover_rate_penalty",
            "effective_score_high_volume_ratio_threshold",
            "effective_score_high_volume_ratio_penalty",
            "effective_breakout_min_breakout_pct",
            "effective_breakout_min_volume_ratio",
            "effective_breakout_min_body_pct",
            "effective_breakout_min_close_above_resistance_pct",
            "effective_breakout_max_upper_shadow_ratio",
            "effective_breakout_min_box_touches",
            "effective_breakout_max_extension_pct",
            "effective_breakout_max_bias_ma10_pct",
            "effective_breakout_max_box_height_pct",
            "effective_breakout_avoid_box_height_low_pct",
            "effective_breakout_avoid_box_height_high_pct",
            "effective_breakout_min_stack_lift_pct",
            "effective_block_breakout_after_downtrend",
            "effective_pullback_min_volume_ratio",
            "effective_pullback_min_box_touches",
            "effective_pullback_max_break_below_resistance_pct",
            "effective_pullback_max_bias_ma10_pct",
            "effective_pullback_min_box_height_pct",
            "effective_pullback_enable_failure_exit",
            "effective_pullback_failure_exit_days",
            "effective_pullback_failure_confirm_days",
            "effective_pullback_failure_buffer_pct",
            "effective_pullback_failure_max_profit_pct",
            "effective_enable_breakeven_stop",
            "effective_breakout_enable_breakeven_stop",
            "effective_pullback_enable_breakeven_stop",
            "effective_breakeven_activate_profit_pct",
            "effective_breakeven_exit_threshold_pct",
            "breakeven_peak_profit_pct",
            "breakeven_current_profit_pct",
            "breakeven_activate_profit_pct",
            "breakeven_exit_threshold_pct",
            "breakout_extension_pct",
            "breakout_body_pct",
            "breakout_close_above_resistance_pct",
            "breakout_upper_shadow_ratio",
            "had_breakout",
            "touched_zone",
            "pullback_depth_ok",
            "pullback_break_below_resistance_pct",
            "reclaimed",
            "rebound_bar",
            "enough_volume",
            "enough_touches",
            "pullback_low_vs_resistance_pct",
            "pullback_close_above_resistance_pct",
        }
        snapshot: dict = {}
        for key in allowlist:
            value = metadata.get(key)
            if value is None or value is pd.NA:
                continue
            value = cls._sanitize_json_value(value)
            if isinstance(value, (str, bool, int, float)):
                snapshot[key] = value
        return snapshot

    @classmethod
    def _sanitize_json_value(cls, value):
        if value is None or value is pd.NA:
            return None
        if hasattr(value, "item") and not isinstance(value, (str, bytes)):
            try:
                value = value.item()
            except Exception:
                pass
        if isinstance(value, dict):
            sanitized = {}
            for key, item in value.items():
                normalized = cls._sanitize_json_value(item)
                if normalized is not None:
                    sanitized[str(key)] = normalized
            return sanitized
        if isinstance(value, (list, tuple)):
            return [item for item in (cls._sanitize_json_value(item) for item in value) if item is not None]
        if isinstance(value, (str, bool, int, float)):
            return value
        return str(value)

    @classmethod
    def _update_position_excursion(cls, position: Position, row: pd.Series) -> None:
        high_price = cls._to_float(row.get("high"))
        low_price = cls._to_float(row.get("low"))
        close_price = cls._to_float(row.get("close"))
        for candidate in (high_price, close_price):
            if candidate is not None and candidate > float(position.highest_price_seen):
                position.highest_price_seen = float(candidate)
        for candidate in (low_price, close_price):
            if candidate is not None and candidate < float(position.lowest_price_seen):
                position.lowest_price_seen = float(candidate)

    @staticmethod
    def _buy_block_reason(row: pd.Series, config: BacktestConfig) -> Optional[str]:
        if BacktestEngine._is_suspended(row):
            return "停牌约束"
        if str(config.trading_constraint_mode or "legacy_pct").strip().lower() == "daily_limits":
            raw_close = BacktestEngine._to_float(row.get("raw_close"))
            up_limit = BacktestEngine._to_float(row.get("up_limit"))
            if not config.allow_limit_up_entry and raw_close is not None and up_limit is not None:
                return "涨停约束" if raw_close >= (up_limit - 1e-6) else None
            return None
        if config.allow_limit_up_entry:
            return None
        pct_chg = BacktestEngine._to_float(row.get("raw_pct_chg"))
        if pct_chg is None:
            pct_chg = BacktestEngine._to_float(row.get("pct_chg")) or 0.0
        return "涨停近似约束" if pct_chg >= 9.5 else None

    @staticmethod
    def _sell_block_reason(row: pd.Series, config: BacktestConfig) -> Optional[str]:
        if BacktestEngine._is_suspended(row):
            return "停牌约束"
        if str(config.trading_constraint_mode or "legacy_pct").strip().lower() == "daily_limits":
            raw_close = BacktestEngine._to_float(row.get("raw_close"))
            down_limit = BacktestEngine._to_float(row.get("down_limit"))
            if config.block_limit_down_exit and raw_close is not None and down_limit is not None:
                return "跌停约束" if raw_close <= (down_limit + 1e-6) else None
            return None
        if not config.block_limit_down_exit:
            return None
        pct_chg = BacktestEngine._to_float(row.get("raw_pct_chg"))
        if pct_chg is None:
            pct_chg = BacktestEngine._to_float(row.get("pct_chg")) or 0.0
        return "跌停近似约束" if pct_chg <= -9.5 else None

    @staticmethod
    def _is_suspended(row: pd.Series) -> bool:
        value = row.get("is_suspended")
        if value is None or value is pd.NA:
            return False
        try:
            return int(value) == 1
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _to_float(value) -> Optional[float]:
        if value is None or value is pd.NA:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
