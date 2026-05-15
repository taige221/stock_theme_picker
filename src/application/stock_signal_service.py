# -*- coding: utf-8 -*-
"""
===================================
Single Stock Signal Service
===================================
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from theme_picker.config import get_config
from theme_picker.data_provider.realtime_types import ChipDistribution
from theme_picker.stock_analyzer import TrendAnalysisResult


class StockSignalService:
    """Derive a stock-first signal from trend, quote, chip, and fundamental context."""

    STRATEGY_LABELS = {
        "auto": "自动决策",
        "pullback": "低吸回踩",
        "breakout": "突破确认",
        "trend_follow": "趋势跟随",
        "holding": "趋势持有",
    }

    def __init__(self):
        self.config = get_config()

    def analyze(
        self,
        *,
        trend_result: TrendAnalysisResult,
        current_price: Optional[float],
        pct_chg: Optional[float],
        volume_ratio: Optional[float],
        turnover_rate: Optional[float],
        chip_data: Optional[ChipDistribution] = None,
        fundamental_context: Optional[Dict[str, Any]] = None,
        strategy: str = "auto",
    ) -> Dict[str, Any]:
        metrics = self._build_metrics(
            trend_result=trend_result,
            current_price=current_price,
            pct_chg=pct_chg,
            volume_ratio=volume_ratio,
            turnover_rate=turnover_rate,
        )
        strategy_decisions = self._build_strategy_decisions(metrics)
        decision = self._select_primary_decision(strategy_decisions, strategy)
        signal = str(decision.get("signal") or "仅观察")
        support = self._pick_support_level(
            current_price=current_price,
            support_levels=trend_result.support_levels,
            ma10=trend_result.ma10,
            ma20=trend_result.ma20,
        )
        pressure = self._pick_pressure_level(
            current_price=current_price,
            resistance_levels=trend_result.resistance_levels,
        )
        selected_reasons = self._build_selected_reasons(
            strategy_key=str(decision.get("key") or strategy or "auto"),
            signal=signal,
            trend_result=trend_result,
            current_price=current_price,
            pct_chg=pct_chg,
            volume_ratio=volume_ratio,
            chip_data=chip_data,
        )
        excluded_reasons = self._build_excluded_reasons(
            strategy_key=str(decision.get("key") or strategy or "auto"),
            signal=signal,
            trend_result=trend_result,
            pct_chg=pct_chg,
            turnover_rate=turnover_rate,
            chip_data=chip_data,
            fundamental_context=fundamental_context,
        )
        pattern = self._derive_pattern(signal, metrics)
        normalized_decisions = self._decorate_strategy_decisions(
            strategy_decisions=strategy_decisions,
            trend_result=trend_result,
            current_price=current_price,
            pct_chg=pct_chg,
            volume_ratio=volume_ratio,
            turnover_rate=turnover_rate,
            chip_data=chip_data,
            fundamental_context=fundamental_context,
        )
        return {
            "strategy": strategy,
            "strategy_label": self.STRATEGY_LABELS.get(strategy, strategy),
            "signal": signal,
            "pattern": pattern,
            "support": support,
            "pressure": pressure,
            "selected_reasons": selected_reasons,
            "excluded_reasons": excluded_reasons,
            "strategy_decisions": normalized_decisions,
        }

    def _build_metrics(
        self,
        *,
        trend_result: TrendAnalysisResult,
        current_price: Optional[float],
        pct_chg: Optional[float],
        volume_ratio: Optional[float],
        turnover_rate: Optional[float],
    ) -> Dict[str, Any]:
        bias_threshold = float(getattr(self.config, "bias_threshold", 5.0) or 5.0)
        trend_score = float(trend_result.signal_score or 0.0)
        bias_ma10 = float(trend_result.bias_ma10 or 0.0)
        pct = float(pct_chg or 0.0)
        volume = float(volume_ratio or 0.0)
        turnover = float(turnover_rate or 0.0)
        current = float(current_price or 0.0)
        ma10 = float(trend_result.ma10 or 0.0)
        ma20 = float(trend_result.ma20 or 0.0)
        support_floor = ma20 * 0.985 if ma20 > 0 else ma20
        buy_signal = trend_result.buy_signal.value
        trend_status = trend_result.trend_status.value

        has_bearish_signal = buy_signal in {"卖出", "强烈卖出"} or trend_status in {"空头排列", "强势空头"}
        has_acceleration_risk = (
            bias_ma10 >= bias_threshold
            or pct >= 8.0
            or turnover >= 20.0
        )
        is_near_support = ma10 > 0 and current > 0 and support_floor > 0 and current <= ma10 * 1.01 and current >= support_floor
        has_active_breakout = pct >= 3.0 and volume >= 1.2 and trend_score >= 55.0
        has_holding_quality = trend_score >= 68.0 and buy_signal in {"买入", "强烈买入", "持有"} and bias_ma10 <= 4.0
        has_trend_follow_setup = (
            trend_score >= 72.0
            and buy_signal in {"买入", "强烈买入", "持有"}
            and trend_status in {"多头排列", "强势多头"}
            and 0.5 <= bias_ma10 <= 4.0
            and pct < 3.0
            and turnover < 20.0
            and current > 0
            and ma10 > 0
            and current >= ma10
        )

        return {
            "pct_chg": self._safe_float(pct_chg),
            "bias_ma10": self._safe_float(trend_result.bias_ma10),
            "trend_score": trend_score,
            "buy_signal": buy_signal,
            "trend_status": trend_status,
            "has_bearish_signal": has_bearish_signal,
            "has_acceleration_risk": has_acceleration_risk,
            "is_near_support": is_near_support,
            "has_active_breakout": has_active_breakout,
            "has_holding_quality": has_holding_quality,
            "has_trend_follow_setup": has_trend_follow_setup,
        }

    def _build_strategy_decisions(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        has_bearish_signal = bool(metrics.get("has_bearish_signal"))
        has_acceleration_risk = bool(metrics.get("has_acceleration_risk"))
        decisions = [
            self._make_strategy_decision(
                key="pullback",
                label=self.STRATEGY_LABELS["pullback"],
                matched=bool(metrics.get("is_near_support")) and not has_bearish_signal and not has_acceleration_risk,
                signal="低吸观察" if bool(metrics.get("is_near_support")) and not has_bearish_signal and not has_acceleration_risk else ("不宜追高" if has_bearish_signal or has_acceleration_risk else "仅观察"),
            ),
            self._make_strategy_decision(
                key="breakout",
                label=self.STRATEGY_LABELS["breakout"],
                matched=bool(metrics.get("has_active_breakout")) and not has_acceleration_risk and not has_bearish_signal,
                signal="短线异动" if bool(metrics.get("has_active_breakout")) and not has_acceleration_risk and not has_bearish_signal else ("不宜追高" if has_bearish_signal or has_acceleration_risk else "仅观察"),
            ),
            self._make_strategy_decision(
                key="trend_follow",
                label=self.STRATEGY_LABELS["trend_follow"],
                matched=bool(metrics.get("has_trend_follow_setup")) and not has_acceleration_risk and not has_bearish_signal,
                signal="趋势跟随" if bool(metrics.get("has_trend_follow_setup")) and not has_acceleration_risk and not has_bearish_signal else ("不宜追高" if has_bearish_signal or has_acceleration_risk else "仅观察"),
            ),
            self._make_strategy_decision(
                key="holding",
                label=self.STRATEGY_LABELS["holding"],
                matched=bool(metrics.get("has_holding_quality")) and not has_acceleration_risk and not has_bearish_signal,
                signal="持有候选" if bool(metrics.get("has_holding_quality")) and not has_acceleration_risk and not has_bearish_signal else ("不宜追高" if has_bearish_signal or has_acceleration_risk else "仅观察"),
            ),
        ]
        return decisions

    @staticmethod
    def _make_strategy_decision(*, key: str, label: str, matched: bool, signal: str) -> Dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "matched": matched,
            "signal": signal,
        }

    def _select_primary_decision(self, decisions: List[Dict[str, Any]], strategy: str) -> Dict[str, Any]:
        if strategy and strategy != "auto":
            for item in decisions:
                if str(item.get("key")) == strategy:
                    return item
        for key in ("pullback", "breakout", "trend_follow", "holding"):
            for item in decisions:
                if str(item.get("key")) == key and bool(item.get("matched")):
                    return item
        if decisions:
            return decisions[-1]
        return {"key": strategy or "auto", "label": self.STRATEGY_LABELS.get(strategy or "auto", strategy or "auto"), "matched": False, "signal": "仅观察"}

    def _decorate_strategy_decisions(
        self,
        *,
        strategy_decisions: List[Dict[str, Any]],
        trend_result: TrendAnalysisResult,
        current_price: Optional[float],
        pct_chg: Optional[float],
        volume_ratio: Optional[float],
        turnover_rate: Optional[float],
        chip_data: Optional[ChipDistribution],
        fundamental_context: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in strategy_decisions:
            key = str(item.get("key") or "")
            signal = str(item.get("signal") or "仅观察")
            normalized.append(
                {
                    "key": key,
                    "label": str(item.get("label") or key),
                    "matched": bool(item.get("matched")),
                    "signal": signal,
                    "pattern": self._derive_pattern(
                        signal,
                        {"pct_chg": self._safe_float(pct_chg), "bias_ma10": self._safe_float(trend_result.bias_ma10)},
                    ),
                    "bias_ma10": self._safe_float(trend_result.bias_ma10),
                    "selected_reasons": self._build_selected_reasons(
                        strategy_key=key,
                        signal=signal,
                        trend_result=trend_result,
                        current_price=current_price,
                        pct_chg=pct_chg,
                        volume_ratio=volume_ratio,
                        chip_data=chip_data,
                    ),
                    "excluded_reasons": self._build_excluded_reasons(
                        strategy_key=key,
                        signal=signal,
                        trend_result=trend_result,
                        pct_chg=pct_chg,
                        turnover_rate=turnover_rate,
                        chip_data=chip_data,
                        fundamental_context=fundamental_context,
                    ),
                }
            )
        return normalized

    def _build_selected_reasons(
        self,
        *,
        strategy_key: str,
        signal: str,
        trend_result: TrendAnalysisResult,
        current_price: Optional[float],
        pct_chg: Optional[float],
        volume_ratio: Optional[float],
        chip_data: Optional[ChipDistribution],
    ) -> List[str]:
        reasons = self._pick_display_reasons(
            trend_result.signal_reasons,
            prefer_positive=True,
            limit=3,
        )
        if strategy_key == "trend_follow" and signal == "趋势跟随":
            reasons.insert(0, "趋势保持抬升，回踩偏浅，更适合顺势轻仓跟随")
        elif signal == "持有候选":
            reasons.insert(0, "趋势底座完整，当前位置仍处于可持续跟踪区间")
        elif signal == "低吸观察":
            reasons.insert(0, "价格回踩至 MA10 / MA20 支撑带附近，更适合等承接确认")
        elif signal == "短线异动":
            pct = float(pct_chg or 0.0)
            volume = float(volume_ratio or 0.0)
            reasons.insert(0, f"当日涨幅 {pct:.2f}% 且量比 {volume:.2f}，出现放量异动")
        elif signal == "仅观察":
            reasons.insert(0, "技术结构仍可跟踪，但还没到更舒服的出手位置")

        chip_reason = self._build_chip_positive_reason(chip_data)
        if chip_reason:
            reasons.append(chip_reason)

        return list(dict.fromkeys([item for item in reasons if str(item).strip()]))[:4]

    def _build_excluded_reasons(
        self,
        *,
        strategy_key: str,
        signal: str,
        trend_result: TrendAnalysisResult,
        pct_chg: Optional[float],
        turnover_rate: Optional[float],
        chip_data: Optional[ChipDistribution],
        fundamental_context: Optional[Dict[str, Any]],
    ) -> List[str]:
        reasons = self._pick_display_reasons(
            trend_result.risk_factors,
            prefer_positive=False,
            limit=3,
        )
        bias_threshold = float(getattr(self.config, "bias_threshold", 5.0) or 5.0)
        bias_ma10 = float(trend_result.bias_ma10 or 0.0)
        pct = float(pct_chg or 0.0)
        turnover = float(turnover_rate or 0.0)

        if signal == "不宜追高" and bias_ma10 >= bias_threshold:
            reasons.insert(0, f"偏离 MA10 {bias_ma10:.2f}% ，短线位置偏高")
        elif signal == "不宜追高" and pct >= 8.0:
            reasons.insert(0, f"当日涨幅 {pct:.2f}% 偏快，追高性价比不足")
        elif strategy_key == "trend_follow" and signal == "仅观察":
            reasons.insert(0, "趋势延续型更看重稳步抬高，当前还缺少足够清晰的顺势跟随机会")
        elif signal == "仅观察":
            reasons.insert(0, "当前趋势和位置都不差，但还没有形成更明确的右侧确认")

        if turnover >= 20.0:
            reasons.append(f"换手率 {turnover:.2f}% 偏高，短线分歧可能放大")

        chip_reason = self._build_chip_negative_reason(chip_data)
        if chip_reason:
            reasons.append(chip_reason)

        fundamental_reason = self._build_fundamental_caveat(fundamental_context)
        if fundamental_reason:
            reasons.append(fundamental_reason)

        return list(dict.fromkeys([item for item in reasons if str(item).strip()]))[:4]

    @staticmethod
    def _build_chip_positive_reason(chip_data: Optional[ChipDistribution]) -> Optional[str]:
        if chip_data is None:
            return None
        profit_ratio = float(getattr(chip_data, "profit_ratio", 0.0) or 0.0)
        concentration_90 = float(getattr(chip_data, "concentration_90", 0.0) or 0.0)
        if 0.35 <= profit_ratio <= 0.85 and concentration_90 > 0 and concentration_90 <= 0.22:
            return f"筹码集中度较好，90% 筹码集中度 {concentration_90:.2%}"
        return None

    @staticmethod
    def _build_chip_negative_reason(chip_data: Optional[ChipDistribution]) -> Optional[str]:
        if chip_data is None:
            return None
        profit_ratio = float(getattr(chip_data, "profit_ratio", 0.0) or 0.0)
        concentration_90 = float(getattr(chip_data, "concentration_90", 0.0) or 0.0)
        if profit_ratio >= 0.9:
            return f"获利盘比例 {profit_ratio:.0%} 偏高，短线兑现压力需要留意"
        if concentration_90 >= 0.32:
            return f"90% 筹码集中度 {concentration_90:.2%} 偏散，筹码结构仍需改善"
        return None

    @staticmethod
    def _build_fundamental_caveat(fundamental_context: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(fundamental_context, dict):
            return None
        status = str(fundamental_context.get("status") or "").strip().lower()
        if status in {"failed", "partial"}:
            return "基本面聚合结果暂不完整，结论应以技术面为主"
        return None

    @staticmethod
    def _pick_support_level(
        *,
        current_price: Optional[float],
        support_levels: List[float],
        ma10: Optional[float],
        ma20: Optional[float],
    ) -> Optional[float]:
        current = float(current_price or 0.0)
        candidates = {
            StockSignalService._safe_float(level)
            for level in [*support_levels, ma10, ma20]
        }
        valid = sorted(
            [level for level in candidates if level is not None and level > 0],
            reverse=True,
        )
        if not valid:
            return None
        if current <= 0:
            return valid[0]
        below = [level for level in valid if level <= current]
        return below[0] if below else valid[-1]

    @staticmethod
    def _pick_pressure_level(
        *,
        current_price: Optional[float],
        resistance_levels: List[float],
    ) -> Optional[float]:
        current = float(current_price or 0.0)
        valid = sorted(
            [
                level
                for level in (StockSignalService._safe_float(item) for item in resistance_levels)
                if level is not None and level > 0
            ]
        )
        if not valid:
            return None
        if current <= 0:
            return valid[-1]
        above = [level for level in valid if level >= current]
        return above[0] if above else valid[-1]

    @staticmethod
    def _derive_pattern(signal: str, metrics: Dict[str, Any]) -> Optional[str]:
        pct_chg = float(metrics.get("pct_chg") or 0.0)
        bias_ma10 = float(metrics.get("bias_ma10") or 0.0)
        if signal == "趋势跟随":
            return "趋势延续"
        if signal == "持有候选":
            return "趋势延续"
        if signal == "低吸观察":
            return "回踩支撑区"
        if signal == "不宜追高":
            return "短线加速"
        if signal == "短线异动":
            return "放量异动"
        if bias_ma10 <= 2 and pct_chg >= 0:
            return "平台整理"
        return "观望整理"

    @staticmethod
    def _pick_display_reasons(
        reasons: List[str],
        *,
        prefer_positive: bool,
        limit: int,
    ) -> List[str]:
        if not reasons:
            return []
        filtered: List[str] = []
        for reason in reasons:
            normalized = StockSignalService._normalize_reason_text(reason)
            if prefer_positive and StockSignalService._is_negative_reason(normalized):
                continue
            if not prefer_positive and StockSignalService._is_positive_reason(normalized):
                continue
            filtered.append(normalized)
        if filtered:
            return list(dict.fromkeys(filtered[:limit]))
        normalized_reasons = [StockSignalService._normalize_reason_text(item) for item in reasons[:limit]]
        return list(dict.fromkeys(normalized_reasons))

    @staticmethod
    def _is_positive_reason(reason: str) -> bool:
        positive_tokens = (
            "满足",
            "维持向上",
            "站上",
            "多头",
            "买入",
            "支撑",
            "回踩至",
            "强势",
            "放量",
            "金叉",
        )
        return any(token in str(reason) for token in positive_tokens)

    @staticmethod
    def _is_negative_reason(reason: str) -> bool:
        negative_tokens = (
            "未满足",
            "不足",
            "低于",
            "尚未",
            "跌破",
            "偏高",
            "分歧",
            "风险",
            "等待",
            "过快",
        )
        return any(token in str(reason) for token in negative_tokens)

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_reason_text(reason: Any) -> str:
        text = str(reason or "").strip()
        if not text:
            return ""
        return re.sub(r"^[^A-Za-z0-9\u4e00-\u9fff]+", "", text).strip()
