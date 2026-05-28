# -*- coding: utf-8 -*-
"""Backtest adapters for single-stock signal strategy views."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from theme_picker.application.stock_signal_service import StockSignalService
from theme_picker.stock_analyzer import StockTrendAnalyzer, TrendAnalysisResult
from theme_picker.strategy.base import Strategy, StrategySignal
from theme_picker.strategy.params import StrategyParams


class StockSignalBacktestStrategy(Strategy):
    """Adapt StockSignalService's strategy views to the backtest engine."""

    name = "stock_signal_auto"
    signal_strategy = "auto"
    entry_signals = {"低吸观察", "短线异动", "趋势跟随", "持有候选"}

    def __init__(self) -> None:
        self.trend_analyzer = StockTrendAnalyzer()
        self.signal_service = StockSignalService()

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
        min_required = max(60, int(params.breakout_lookback_days) + 20)
        available_rows = (int(current_index) + 1) if current_index is not None else len(history)
        if history is None or history.empty or available_rows < min_required:
            return StrategySignal(
                action="hold",
                reason="history_not_ready",
                metadata={"price_adjustment": price_adjustment, "strategy_name": self.name},
            )

        working = self._slice_history(history, current_index=current_index, lookback_rows=max(120, min_required))
        working = self._prepare_working_frame(working)
        if working.empty:
            return StrategySignal(
                action="hold",
                reason="missing_price_context",
                metadata={"price_adjustment": price_adjustment, "strategy_name": self.name},
            )

        latest = working.iloc[-1]
        close_price = self._to_float(latest.get("close"))
        if close_price is None or close_price <= 0:
            return StrategySignal(
                action="hold",
                reason="missing_price_context",
                metadata={"price_adjustment": price_adjustment, "strategy_name": self.name},
            )

        trend_result = self.trend_analyzer.analyze(working, self.name)
        signal_payload = self.signal_service.analyze(
            trend_result=trend_result,
            current_price=close_price,
            pct_chg=self._to_float(latest.get("pct_chg")),
            volume_ratio=self._to_float(latest.get("volume_ratio")),
            turnover_rate=self._to_float(latest.get("turnover_rate")),
            strategy=self.signal_strategy,
        )
        metadata = self._build_metadata(
            price_adjustment=price_adjustment,
            latest=latest,
            trend_result=trend_result,
            signal_payload=signal_payload,
        )

        if has_position and entry_price:
            exit_signal = self._build_exit_signal(
                close_price=close_price,
                entry_price=entry_price,
                holding_days=holding_days,
                params=params,
                trend_result=trend_result,
                metadata=metadata,
            )
            if exit_signal is not None:
                return exit_signal
            return StrategySignal(action="hold", reason="holding", metadata=metadata)

        if self._is_entry_signal(signal_payload):
            return StrategySignal(
                action="buy",
                reason=f"{self.signal_strategy}_signal_entry",
                score=self._to_float(metadata.get("trend_score")),
                metadata=metadata,
            )

        return StrategySignal(action="hold", reason="entry_not_ready", metadata=metadata)

    def _is_entry_signal(self, signal_payload: dict[str, Any]) -> bool:
        signal = str(signal_payload.get("signal") or "").strip()
        if signal not in self.entry_signals:
            return False

        decisions = signal_payload.get("strategy_decisions") or []
        if self.signal_strategy == "auto":
            return any(bool(item.get("matched")) for item in decisions if isinstance(item, dict))

        for item in decisions:
            if not isinstance(item, dict):
                continue
            if str(item.get("key") or "") == self.signal_strategy:
                return bool(item.get("matched"))
        return False

    def _build_exit_signal(
        self,
        *,
        close_price: float,
        entry_price: float,
        holding_days: int,
        params: StrategyParams,
        trend_result: TrendAnalysisResult,
        metadata: dict[str, Any],
    ) -> StrategySignal | None:
        pnl_pct = (close_price - entry_price) / entry_price
        if pnl_pct <= -abs(float(params.stop_loss_pct)):
            return StrategySignal(action="sell", reason="stop_loss_hit", score=pnl_pct, metadata=metadata)
        if pnl_pct >= abs(float(params.take_profit_pct)):
            return StrategySignal(action="sell", reason="take_profit_hit", score=pnl_pct, metadata=metadata)
        if holding_days >= int(params.max_holding_days):
            return StrategySignal(action="sell", reason="max_holding_days_reached", score=pnl_pct, metadata=metadata)
        if trend_result.buy_signal.value in {"卖出", "强烈卖出"}:
            return StrategySignal(action="sell", reason="stock_signal_bearish_exit", score=pnl_pct, metadata=metadata)
        ma10 = self._to_float(getattr(trend_result, "ma10", None))
        if ma10 is not None and close_price < ma10:
            return StrategySignal(action="sell", reason="close_below_ma10", score=pnl_pct, metadata=metadata)
        return None

    def _build_metadata(
        self,
        *,
        price_adjustment: str,
        latest: pd.Series,
        trend_result: TrendAnalysisResult,
        signal_payload: dict[str, Any],
    ) -> dict[str, Any]:
        target_decision = self._target_decision(signal_payload.get("strategy_decisions") or [])
        return {
            "price_adjustment": price_adjustment,
            "strategy_name": self.name,
            "signal_strategy": self.signal_strategy,
            "stock_signal": signal_payload.get("signal"),
            "strategy_label": signal_payload.get("strategy_label"),
            "target_decision_label": target_decision.get("label"),
            "target_decision_matched": bool(target_decision.get("matched")),
            "trend_score": self._to_float(trend_result.signal_score),
            "trend_status": trend_result.trend_status.value,
            "buy_signal": trend_result.buy_signal.value,
            "pattern": signal_payload.get("pattern"),
            "close_price": self._to_float(latest.get("close")),
            "ma5": self._to_float(getattr(trend_result, "ma5", None)),
            "ma10": self._to_float(getattr(trend_result, "ma10", None)),
            "ma20": self._to_float(getattr(trend_result, "ma20", None)),
            "ma60": self._to_float(getattr(trend_result, "ma60", None)),
            "bias_ma5": self._to_float(getattr(trend_result, "bias_ma5", None)),
            "bias_ma10": self._to_float(getattr(trend_result, "bias_ma10", None)),
            "bias_ma20": self._to_float(getattr(trend_result, "bias_ma20", None)),
            "pct_chg": self._to_float(latest.get("pct_chg")),
            "volume_ratio": self._to_float(latest.get("volume_ratio")),
            "turnover_rate": self._to_float(latest.get("turnover_rate")),
            "support": self._to_float(signal_payload.get("support")),
            "pressure": self._to_float(signal_payload.get("pressure")),
        }

    def _target_decision(self, decisions: list[Any]) -> dict[str, Any]:
        if self.signal_strategy == "auto":
            for item in decisions:
                if isinstance(item, dict) and bool(item.get("matched")):
                    return item
        for item in decisions:
            if isinstance(item, dict) and str(item.get("key") or "") == self.signal_strategy:
                return item
        return {}

    @staticmethod
    def _slice_history(history: pd.DataFrame, *, current_index: Optional[int], lookback_rows: int) -> pd.DataFrame:
        if current_index is None:
            return history.copy().sort_values("date").reset_index(drop=True)
        start_index = max(0, int(current_index) - int(lookback_rows) + 1)
        return history.iloc[start_index : int(current_index) + 1].copy().reset_index(drop=True)

    @classmethod
    def _prepare_working_frame(cls, frame: pd.DataFrame) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()
        working = frame.copy().sort_values("date").reset_index(drop=True)
        for column in ("open", "high", "low", "close", "volume"):
            if column in working.columns:
                working[column] = pd.to_numeric(working[column], errors="coerce")
        if "pct_chg" not in working.columns or working["pct_chg"].isna().all():
            working["pct_chg"] = pd.to_numeric(working["close"], errors="coerce").pct_change().fillna(0.0) * 100.0
        if "volume_ratio" not in working.columns or working["volume_ratio"].isna().all():
            volume = pd.to_numeric(working.get("volume"), errors="coerce")
            avg_volume_5 = volume.rolling(5, min_periods=1).mean().shift(1)
            working["volume_ratio"] = (volume / avg_volume_5).replace([float("inf"), float("-inf")], pd.NA).fillna(1.0)
        if "turnover_rate" not in working.columns:
            working["turnover_rate"] = 0.0
        working["pct_chg"] = pd.to_numeric(working.get("pct_chg"), errors="coerce").fillna(0.0)
        working["volume_ratio"] = pd.to_numeric(working.get("volume_ratio"), errors="coerce").fillna(1.0)
        working["turnover_rate"] = pd.to_numeric(working.get("turnover_rate"), errors="coerce").fillna(0.0)
        return working.dropna(subset=["date", "close"])

    @staticmethod
    def _to_float(value) -> Optional[float]:
        if value is None or value is pd.NA:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


class StockSignalPullbackStrategy(StockSignalBacktestStrategy):
    name = "stock_signal_pullback"
    signal_strategy = "pullback"


class StockSignalBreakoutStrategy(StockSignalBacktestStrategy):
    name = "stock_signal_breakout"
    signal_strategy = "breakout"


class StockSignalTrendFollowStrategy(StockSignalBacktestStrategy):
    name = "stock_signal_trend_follow"
    signal_strategy = "trend_follow"


class StockSignalHoldingStrategy(StockSignalBacktestStrategy):
    name = "stock_signal_holding"
    signal_strategy = "holding"
