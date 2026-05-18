# -*- coding: utf-8 -*-
"""
===================================
Theme Signal Service
===================================
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
from datetime import datetime, timedelta
from threading import Event, Lock
from typing import Any, Dict, List, Optional

import pandas as pd

from theme_picker.data_provider import DataFetcherManager
from theme_picker.data_provider.base import normalize_stock_code
from theme_picker.data.stock_mapping import STOCK_NAME_MAP
from theme_picker.domain.theme_event import (
    ThemeDefinitionSchema,
    ThemeEventSchema,
    ThemeSignalRuleSchema,
    ThemeStockSignalSchema,
)
from theme_picker.infrastructure.daily_bar_service import get_daily_bar_resolver
from theme_picker.stock_analyzer import StockTrendAnalyzer, TrendAnalysisResult
from theme_picker.infrastructure.persistence import get_theme_picker_db
from theme_picker.infrastructure.runtime import get_theme_picker_config
from theme_picker.infrastructure.stock_pool_service import canonicalize_stock_code

logger = logging.getLogger(__name__)

_THEME_QUOTE_UNPROXY_FETCHERS = {
    "TushareFetcher",
    "EfinanceFetcher",
    "AkshareFetcher",
}
_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)
_NO_PROXY_ENV_KEYS = ("NO_PROXY", "no_proxy")
_PROXY_ENV_LOCK = Lock()


class ThemeSignalService:
    """Apply technical confirmation rules to a theme stock pool."""

    def __init__(self, enable_realtime: Optional[bool] = None):
        self.db = get_theme_picker_db()
        self.fetcher_manager = DataFetcherManager()
        self.daily_bar_resolver = get_daily_bar_resolver()
        self.trend_analyzer = StockTrendAnalyzer()
        config = get_theme_picker_config()
        self.enable_realtime = config.enable_realtime_quote if enable_realtime is None else enable_realtime
        self.realtime_source_priority = config.realtime_source_priority
        self.theme_realtime_source_priority = config.theme_realtime_source_priority
        self.realtime_quote_timeout = float(
            getattr(config, "theme_realtime_quote_timeout", 15.0) or 15.0
        )
        self.tencent_quote_timeout = float(
            getattr(config, "theme_tencent_quote_timeout", 15.0) or 15.0
        )

    def evaluate_theme(
        self,
        theme: ThemeDefinitionSchema,
        event: ThemeEventSchema,
        stock_pool: List[str],
    ) -> List[ThemeStockSignalSchema]:
        candidates: List[Dict[str, Any]] = []
        rule = theme.signal_rules

        for code in stock_pool:
            signal = self.evaluate_stock(theme, event, code, rule)
            if signal is None:
                continue
            candidates.append(signal)

        resonance_count = sum(1 for item in candidates if item["triggered"])
        results: List[ThemeStockSignalSchema] = []
        for item in candidates:
            schema = self._finalize_signal(theme, item, resonance_count, rule)
            results.append(schema)

        return sorted(
            results,
            key=lambda item: (
                self._signal_rank(item.signal_level),
                -float(item.metrics.get("pct_chg") or 0.0),
                item.stock_code,
            ),
        )

    @staticmethod
    def _strategy_mode(rule: ThemeSignalRuleSchema) -> str:
        mode = str(getattr(rule, "strategy_mode", "event") or "event").strip().lower()
        if mode in {"holding", "swing", "position"}:
            return "holding"
        return "event"

    def evaluate_stock(
        self,
        theme: ThemeDefinitionSchema,
        event: ThemeEventSchema,
        stock_code: str,
        rule: ThemeSignalRuleSchema,
    ) -> Optional[Dict[str, Any]]:
        code = canonicalize_stock_code(stock_code)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=90)
        df = self._load_or_fetch_bars(code, start_date, end_date)
        if df is None or df.empty:
            return None

        df = df.sort_values("date").reset_index(drop=True)
        if len(df) < 20:
            return None

        quote = None
        if self.enable_realtime:
            quote = self._fetch_realtime_quote(code)
        stock_name = (
            getattr(quote, "name", None)
            or STOCK_NAME_MAP.get(code)
            or STOCK_NAME_MAP.get(code.split(".")[0])
            or code
        )

        trend_df = df.copy()
        if quote is not None:
            trend_df = self._augment_with_realtime(trend_df, quote)

        trend_result = self.trend_analyzer.analyze(trend_df, code)
        latest = trend_df.iloc[-1]

        metrics = {
            "current_price": float(latest["close"]),
            "pct_chg": self._safe_float(latest.get("pct_chg")),
            "ma5": self._safe_float(trend_result.ma5),
            "ma10": self._safe_float(trend_result.ma10),
            "ma20": self._safe_float(trend_result.ma20),
            "bias_ma5": self._safe_float(trend_result.bias_ma5),
            "bias_ma10": self._calculate_bias(float(latest["close"]), self._safe_float(trend_result.ma10)),
            "bias_ma20": self._calculate_bias(float(latest["close"]), self._safe_float(trend_result.ma20)),
            "volume_ratio": self._safe_float(getattr(quote, "volume_ratio", None) or latest.get("volume_ratio")),
            "turnover_rate": self._safe_float(getattr(quote, "turnover_rate", None)),
            "trend_score": self._safe_float(trend_result.signal_score),
            "trend_status": trend_result.trend_status.value,
            "buy_signal": trend_result.buy_signal.value,
            "realtime_price_used": bool(quote is not None and getattr(quote, "price", None) is not None),
            "realtime_source": getattr(getattr(quote, "source", None), "value", None) if quote else None,
        }
        metrics.update(self._build_context_metrics(trend_df, rule))

        prequalified, reasons = self._check_prequalification(df, trend_result, rule)
        intraday_triggered, intraday_reasons = self._check_intraday_trigger(
            df=trend_df,
            metrics=metrics,
            trend_result=trend_result,
            rule=rule,
        )
        reasons.extend(intraday_reasons)

        return {
            "theme": theme,
            "event": event,
            "stock_code": code,
            "stock_name": stock_name,
            "triggered": prequalified and intraday_triggered,
            "prequalified": prequalified,
            "metrics": metrics,
            "reasons": reasons,
        }

    def _build_context_metrics(
        self,
        df: pd.DataFrame,
        rule: ThemeSignalRuleSchema,
    ) -> Dict[str, Any]:
        recent_window = min(rule.recent_limit_up_days, len(df))
        recent_strong_days = int((pd.to_numeric(df["pct_chg"].tail(recent_window), errors="coerce") > 5).sum())

        lookback = min(rule.breakout_lookback_days, max(1, len(df) - 1))
        recent_high = None
        if len(df) > 1:
            recent_high = self._safe_float(
                pd.to_numeric(df["high"].iloc[-(lookback + 1):-1], errors="coerce").max()
            )

        return {
            "recent_window": recent_window,
            "recent_strong_days": recent_strong_days,
            "recent_high": recent_high,
        }

    def _fetch_realtime_quote(self, stock_code: str):
        executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        future: Optional[concurrent.futures.Future] = None
        stop_event = Event()
        effective_timeout = self._resolve_theme_quote_timeout()
        try:
            logger.debug(
                "主题技术层获取实时行情: code=%s priority=%s timeout=%.1fs",
                stock_code,
                self.theme_realtime_source_priority,
                effective_timeout,
            )
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(
                self._get_theme_realtime_quote,
                stock_code,
                stop_event,
            )
            quote = future.result(timeout=effective_timeout)
            if quote is not None:
                logger.debug(
                    "主题技术层实时行情命中: code=%s source=%s volume_ratio=%s turnover_rate=%s",
                    stock_code,
                    getattr(quote, "source", None),
                    getattr(quote, "volume_ratio", None),
                    getattr(quote, "turnover_rate", None),
                )
            return quote
        except concurrent.futures.TimeoutError:
            stop_event.set()
            logger.warning(
                "主题技术层实时行情超时: code=%s priority=%s timeout=%.1fs",
                stock_code,
                self.theme_realtime_source_priority,
                effective_timeout,
            )
            if future is not None:
                future.cancel()
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            return None
        except Exception as exc:
            stop_event.set()
            logger.debug("主题技术层实时行情失败: code=%s err=%s", stock_code, exc)
            if future is not None:
                future.cancel()
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            return None
        finally:
            stop_event.set()
            if executor is not None:
                executor.shutdown(wait=False)

    def _resolve_theme_quote_timeout(self) -> float:
        source_priority = [
            item.strip().lower()
            for item in str(self.theme_realtime_source_priority or "").split(",")
            if item.strip()
        ]
        if any(source in ("tencent", "akshare_qq") for source in source_priority):
            return max(self.realtime_quote_timeout, self.tencent_quote_timeout)
        return self.realtime_quote_timeout

    def _get_theme_realtime_quote(self, stock_code: str, stop_event: Optional[Event] = None):
        raw_stock_code = (stock_code or "").strip()
        normalized_code = normalize_stock_code(stock_code)
        source_priority = [
            item.strip().lower()
            for item in str(self.theme_realtime_source_priority or "").split(",")
            if item.strip()
        ]
        if not source_priority:
            return self.fetcher_manager.get_realtime_quote(stock_code, log_final_failure=False)

        primary_quote = None
        supplement_attempts = 0

        for source in source_priority:
            if stop_event is not None and stop_event.is_set():
                logger.debug("主题技术层实时行情停止后续 fallback: code=%s", stock_code)
                break
            quote = None
            try:
                if source == "efinance":
                    quote = self.fetcher_manager.get_realtime_http_quote(normalized_code, source=source)
                    if quote is None:
                        quote = self._call_named_fetcher_quote("EfinanceFetcher", normalized_code)
                elif source == "akshare_em":
                    quote = self.fetcher_manager.get_realtime_http_quote(normalized_code, source=source)
                    if quote is None:
                        quote = self._call_named_fetcher_quote("AkshareFetcher", normalized_code, source="em")
                elif source == "akshare_sina":
                    quote = self.fetcher_manager.get_realtime_http_quote(
                        normalized_code,
                        source=source,
                        timeout_seconds=self.realtime_quote_timeout,
                    )
                    if quote is None:
                        quote = self._call_named_fetcher_quote(
                            "AkshareFetcher",
                            normalized_code,
                            source="sina",
                            timeout_seconds=self.realtime_quote_timeout,
                        )
                elif source in ("tencent", "akshare_qq"):
                    quote = self.fetcher_manager.get_realtime_http_quote(
                        normalized_code,
                        source=source,
                        timeout_seconds=max(self.realtime_quote_timeout, self.tencent_quote_timeout),
                    )
                    if quote is None:
                        quote = self._call_named_fetcher_quote(
                            "AkshareFetcher",
                            normalized_code,
                            source="tencent",
                            timeout_seconds=max(self.realtime_quote_timeout, self.tencent_quote_timeout),
                        )
                elif source == "tushare":
                    quote = self._call_named_fetcher_quote("TushareFetcher", raw_stock_code or normalized_code)
            except Exception as exc:
                logger.debug("主题技术层实时行情源失败: code=%s source=%s err=%s", stock_code, source, exc)
                continue

            if quote is None or not quote.has_basic_data():
                continue

            if primary_quote is None:
                primary_quote = quote
                if not self.fetcher_manager._quote_needs_supplement(primary_quote):
                    return primary_quote
            else:
                if stop_event is not None and stop_event.is_set():
                    logger.debug("主题技术层实时行情停止补充源合并: code=%s", stock_code)
                    break
                supplement_attempts += 1
                if supplement_attempts > 1:
                    break
                self.fetcher_manager._merge_quote_fields(primary_quote, quote)
                if not self.fetcher_manager._quote_needs_supplement(primary_quote):
                    break

        return primary_quote

    def _call_named_fetcher_quote(self, fetcher_name: str, stock_code: str, **kwargs):
        without_proxy = fetcher_name in _THEME_QUOTE_UNPROXY_FETCHERS
        lock = _PROXY_ENV_LOCK if without_proxy else None
        env_snapshot: Dict[str, Optional[str]] = {}

        if lock is not None:
            lock.acquire()
        try:
            if without_proxy:
                env_snapshot = self._disable_proxy_env_for_attempt()
            for fetcher in self.fetcher_manager._get_fetchers_snapshot():
                if fetcher.name != fetcher_name:
                    continue
                if not hasattr(fetcher, "get_realtime_quote"):
                    return None
                return self.fetcher_manager._call_fetcher_method(
                    fetcher,
                    "get_realtime_quote",
                    stock_code,
                    **kwargs,
                )
            return None
        finally:
            if without_proxy:
                self._restore_proxy_env_after_attempt(env_snapshot)
            if lock is not None:
                lock.release()

    @staticmethod
    def _disable_proxy_env_for_attempt() -> Dict[str, Optional[str]]:
        snapshot: Dict[str, Optional[str]] = {}
        for key in (*_PROXY_ENV_KEYS, *_NO_PROXY_ENV_KEYS):
            snapshot[key] = os.environ.get(key)
        for key in _PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        return snapshot

    @staticmethod
    def _restore_proxy_env_after_attempt(snapshot: Dict[str, Optional[str]]) -> None:
        for key, value in snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _load_or_fetch_bars(
        self,
        stock_code: str,
        start_date,
        end_date,
    ):
        try:
            result = self.daily_bar_resolver.resolve_daily_bars(
                stock_code,
                bars=90,
                start_date=start_date,
                end_date=end_date,
                minimum_rows=20,
            )
        except Exception as exc:
            logger.debug("主题技术层在线补数失败: code=%s err=%s", stock_code, exc)
            return pd.DataFrame()
        return result.frame

    def _check_prequalification(
        self,
        df: pd.DataFrame,
        trend_result: TrendAnalysisResult,
        rule: ThemeSignalRuleSchema,
    ) -> tuple[bool, List[str]]:
        if self._strategy_mode(rule) == "holding":
            return self._check_holding_prequalification(df, trend_result, rule)
        return self._check_event_prequalification(df, trend_result, rule)

    def _check_event_prequalification(
        self,
        df: pd.DataFrame,
        trend_result: TrendAnalysisResult,
        rule: ThemeSignalRuleSchema,
    ) -> tuple[bool, List[str]]:
        reasons: List[str] = []
        prequalified = True

        if not (trend_result.ma5 > trend_result.ma10 > trend_result.ma20):
            prequalified = False
            reasons.append("未满足 MA5 > MA10 > MA20")
        else:
            reasons.append("满足多头排列底座")

        ma20_series = pd.to_numeric(df["ma20"], errors="coerce").dropna()
        if len(ma20_series) >= 3 and ma20_series.iloc[-1] >= ma20_series.iloc[-3]:
            reasons.append("MA20 维持向上")
        else:
            prequalified = False
            reasons.append("MA20 未明显向上")

        recent_window = min(rule.recent_limit_up_days, len(df))
        recent_strong_days = int((pd.to_numeric(df["pct_chg"].tail(recent_window), errors="coerce") > 5).sum())
        if recent_strong_days >= rule.min_recent_strong_days:
            reasons.append(f"最近 {recent_window} 天强势日达到 {recent_strong_days} 天")
        else:
            prequalified = False
            reasons.append(f"最近 {recent_window} 天强势日不足 {rule.min_recent_strong_days} 天")

        recent_5 = df.tail(5)
        latest_close = float(recent_5.iloc[-1]["close"])
        latest_ma10 = float(recent_5.iloc[-1]["ma10"])
        latest_ma20 = float(recent_5.iloc[-1]["ma20"])
        if latest_close >= latest_ma10:
            reasons.append("最近收盘仍站上 MA10")
        elif latest_close >= latest_ma20:
            reasons.append("最近收盘回落至 MA10 下方但未破 MA20")
        else:
            prequalified = False
            reasons.append("最近收盘已跌破 MA20")

        return prequalified, reasons

    def _check_holding_prequalification(
        self,
        df: pd.DataFrame,
        trend_result: TrendAnalysisResult,
        rule: ThemeSignalRuleSchema,
    ) -> tuple[bool, List[str]]:
        reasons: List[str] = []
        prequalified = True

        if trend_result.ma10 >= trend_result.ma20:
            reasons.append("MA10 仍在 MA20 上方")
        else:
            prequalified = False
            reasons.append("未满足 MA10 >= MA20")

        ma20_series = pd.to_numeric(df["ma20"], errors="coerce").dropna()
        ma20_floor = None
        if len(ma20_series) >= 3:
            ma20_floor = ma20_series.iloc[-3] * (1 - rule.holding_ma20_drift_tolerance_pct / 100.0)
        if len(ma20_series) >= 3 and ma20_series.iloc[-1] >= ma20_floor:
            reasons.append("MA20 维持向上")
        else:
            prequalified = False
            reasons.append("MA20 未明显向上")

        recent_window = min(rule.recent_limit_up_days, len(df))
        recent_strong_days = int((pd.to_numeric(df["pct_chg"].tail(recent_window), errors="coerce") > 5).sum())
        if recent_strong_days >= rule.holding_min_recent_strong_days:
            reasons.append(f"最近 {recent_window} 天至少保留 {recent_strong_days} 个强势日")
        else:
            prequalified = False
            reasons.append(f"最近 {recent_window} 天强势日不足 {rule.holding_min_recent_strong_days} 天")

        latest_close = float(df.iloc[-1]["close"])
        latest_ma10 = float(df.iloc[-1]["ma10"])
        latest_ma20 = float(df.iloc[-1]["ma20"])
        support_floor = latest_ma20 * (1 - rule.holding_support_tolerance_pct / 100.0)
        if latest_close >= latest_ma10:
            reasons.append("最近收盘仍站上 MA10")
        elif latest_close >= latest_ma20:
            reasons.append("最近收盘回落至 MA10 下方但未破 MA20")
        elif latest_close >= support_floor:
            reasons.append("最近收盘轻微跌破 MA20，但仍处于支撑带内")
        else:
            prequalified = False
            reasons.append("最近收盘已跌破 MA20")

        trend_score = float(trend_result.signal_score or 0.0)
        buy_signal = trend_result.buy_signal.value
        if trend_score >= rule.holding_min_trend_score or buy_signal in {"持有", "买入", "强烈买入"}:
            reasons.append(f"趋势评分 {trend_score:.0f} 仍处于可持有区间")
        else:
            prequalified = False
            reasons.append(f"趋势评分 {trend_score:.0f} 低于持有阈值")

        return prequalified, reasons

    def _check_intraday_trigger(
        self,
        *,
        df: pd.DataFrame,
        metrics: Dict[str, Any],
        trend_result: TrendAnalysisResult,
        rule: ThemeSignalRuleSchema,
    ) -> tuple[bool, List[str]]:
        if self._strategy_mode(rule) == "holding":
            return self._check_holding_trigger(
                df=df,
                metrics=metrics,
                trend_result=trend_result,
                rule=rule,
            )
        return self._check_event_trigger(
            df=df,
            metrics=metrics,
            trend_result=trend_result,
            rule=rule,
        )

    def _check_event_trigger(
        self,
        *,
        df: pd.DataFrame,
        metrics: Dict[str, Any],
        trend_result: TrendAnalysisResult,
        rule: ThemeSignalRuleSchema,
    ) -> tuple[bool, List[str]]:
        reasons: List[str] = []
        triggered = True

        pct_chg = float(metrics.get("pct_chg") or 0.0)
        if pct_chg >= rule.min_breakout_pct:
            reasons.append(f"当日涨幅 {pct_chg:.2f}% 达到异动阈值")
        else:
            triggered = False
            reasons.append(f"当日涨幅 {pct_chg:.2f}% 低于异动阈值")

        volume_ratio = float(metrics.get("volume_ratio") or 0.0)
        if volume_ratio >= rule.min_volume_ratio:
            reasons.append(f"量比 {volume_ratio:.2f} 达到放量阈值")
        else:
            triggered = False
            reasons.append(f"量比 {volume_ratio:.2f} 低于放量阈值")

        lookback = min(rule.breakout_lookback_days, max(1, len(df) - 1))
        recent_high = float(pd.to_numeric(df["high"].iloc[-(lookback + 1):-1], errors="coerce").max())
        current_price = float(metrics.get("current_price") or 0.0)
        if current_price >= recent_high:
            reasons.append(f"突破近 {lookback} 日高点 {recent_high:.2f}")
        else:
            triggered = False
            reasons.append(f"尚未突破近 {lookback} 日高点 {recent_high:.2f}")

        if trend_result.buy_signal.value in {"买入", "强烈买入"}:
            reasons.append(f"技术信号为 {trend_result.buy_signal.value}")
        else:
            triggered = False
            reasons.append(f"技术信号仅为 {trend_result.buy_signal.value}")

        return triggered, reasons

    def _check_holding_trigger(
        self,
        *,
        df: pd.DataFrame,
        metrics: Dict[str, Any],
        trend_result: TrendAnalysisResult,
        rule: ThemeSignalRuleSchema,
    ) -> tuple[bool, List[str]]:
        reasons: List[str] = []
        triggered = True

        buy_signal = trend_result.buy_signal.value
        if buy_signal in {"持有", "买入", "强烈买入"}:
            reasons.append(f"技术信号为 {buy_signal}")
        else:
            triggered = False
            reasons.append(f"技术信号仅为 {buy_signal}")

        current_price = float(metrics.get("current_price") or 0.0)
        ma20 = float(metrics.get("ma20") or 0.0)
        support_floor = ma20 * (1 - rule.holding_support_tolerance_pct / 100.0) if ma20 > 0 else ma20
        if current_price >= ma20:
            reasons.append("当前价格仍站在 MA20 上方")
        elif current_price >= support_floor:
            reasons.append("当前价格回踩至 MA20 附近，仍在可接受支撑带内")
        else:
            triggered = False
            reasons.append("当前价格已跌回 MA20 下方")

        pct_chg = float(metrics.get("pct_chg") or 0.0)
        if pct_chg >= rule.min_breakout_pct:
            reasons.append(f"当日涨幅 {pct_chg:.2f}% 已出现题材增强")
        else:
            reasons.append(f"当日涨幅 {pct_chg:.2f}% 未明显异动，更适合按趋势持有评估")

        volume_ratio = float(metrics.get("volume_ratio") or 0.0)
        if volume_ratio >= rule.min_volume_ratio:
            reasons.append(f"量比 {volume_ratio:.2f} 放大，为持有型额外加分")
        else:
            reasons.append(f"量比 {volume_ratio:.2f} 未明显放大，不作为持有型硬门槛")

        return triggered, reasons

    def _finalize_signal(
        self,
        theme: ThemeDefinitionSchema,
        item: Dict[str, Any],
        resonance_count: int,
        rule: ThemeSignalRuleSchema,
    ) -> ThemeStockSignalSchema:
        if self._strategy_mode(rule) == "holding":
            return self._finalize_holding_signal(theme, item, resonance_count, rule)
        return self._finalize_event_signal(theme, item, resonance_count, rule)

    def _finalize_event_signal(
        self,
        theme: ThemeDefinitionSchema,
        item: Dict[str, Any],
        resonance_count: int,
        rule: ThemeSignalRuleSchema,
    ) -> ThemeStockSignalSchema:
        metrics = dict(item["metrics"])
        reasons = list(item["reasons"])

        bias_ma5 = float(metrics.get("bias_ma5") or 0.0)
        pct_chg = float(metrics.get("pct_chg") or 0.0)
        turnover_rate = float(metrics.get("turnover_rate") or 0.0)

        triggered = bool(item["triggered"])
        if not triggered:
            signal_level = "主题触发"
        elif resonance_count < rule.min_resonance_count:
            signal_level = "盘中异动"
            reasons.append(
                f"同主题共振数量不足：{resonance_count}/{rule.min_resonance_count}"
            )
        elif bias_ma5 > rule.max_bias_ma5_pct:
            signal_level = "不宜追高"
            reasons.append(f"偏离 MA5 {bias_ma5:.2f}% ，超过追高阈值")
        elif pct_chg >= rule.min_limit_up_warning_pct:
            signal_level = "不宜追高"
            reasons.append("涨幅已接近涨停，优先等待分歧后的二次机会")
        elif turnover_rate >= 20:
            signal_level = "盘中异动"
            reasons.append(f"换手率 {turnover_rate:.2f}% 偏高，分歧较大")
        else:
            signal_level = "可参与"
            reasons.append(f"同主题共振数量达到 {resonance_count}")

        metrics["resonance_count"] = resonance_count
        return ThemeStockSignalSchema(
            theme_id=theme.id,
            theme_name=theme.name,
            stock_code=item["stock_code"],
            stock_name=item["stock_name"],
            signal_level=signal_level,
            triggered=triggered,
            reasons=reasons,
            metrics=metrics,
        )

    def _finalize_holding_signal(
        self,
        theme: ThemeDefinitionSchema,
        item: Dict[str, Any],
        resonance_count: int,
        rule: ThemeSignalRuleSchema,
    ) -> ThemeStockSignalSchema:
        metrics = dict(item["metrics"])
        reasons = list(item["reasons"])

        bias_ma5 = float(metrics.get("bias_ma5") or 0.0)
        bias_ma10 = float(metrics.get("bias_ma10") or 0.0)
        pct_chg = float(metrics.get("pct_chg") or 0.0)
        current_price = float(metrics.get("current_price") or 0.0)
        ma10 = float(metrics.get("ma10") or 0.0)
        ma20 = float(metrics.get("ma20") or 0.0)
        trend_score = float(metrics.get("trend_score") or 0.0)
        support_floor = ma20 * (1 - rule.holding_support_tolerance_pct / 100.0) if ma20 > 0 else ma20

        prequalified = bool(item["prequalified"])
        triggered = bool(item["triggered"])
        if not prequalified or not triggered:
            signal_level = "主题触发"
        elif bias_ma5 > rule.max_bias_ma5_pct or pct_chg >= rule.min_limit_up_warning_pct:
            signal_level = "不宜追高"
            reasons.append("短线加速过快，持有型更适合等回踩后的二次确认")
        elif current_price <= ma10 and current_price >= support_floor:
            signal_level = "低吸观察"
            reasons.append("价格回踩至 MA10/MA20 区间，更适合观察承接后分批介入")
        elif bias_ma10 <= rule.holding_max_bias_ma10_pct and trend_score >= rule.holding_min_trend_score:
            signal_level = "持有候选"
            reasons.append("趋势底座完整且距 MA10 偏离可控，适合作为题材持有型候选")
        else:
            signal_level = "主题触发"
            reasons.append("趋势尚可，但当前位置或节奏还不够舒服，先保留观察")

        if resonance_count >= rule.min_resonance_count:
            reasons.append(f"同主题共振数量达到 {resonance_count}")
        else:
            reasons.append(f"同主题共振数量偏少：{resonance_count}/{rule.min_resonance_count}")

        metrics["resonance_count"] = resonance_count
        return ThemeStockSignalSchema(
            theme_id=theme.id,
            theme_name=theme.name,
            stock_code=item["stock_code"],
            stock_name=item["stock_name"],
            signal_level=signal_level,
            triggered=triggered,
            reasons=reasons,
            metrics=metrics,
        )

    @staticmethod
    def _signal_rank(signal_level: str) -> int:
        rank_map = {
            "持有候选": 0,
            "可参与": 0,
            "低吸观察": 1,
            "盘中异动": 1,
            "主题触发": 2,
            "不宜追高": 3,
        }
        return rank_map.get(signal_level, 9)

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _calculate_bias(price: float, ma_value: Optional[float]) -> Optional[float]:
        if ma_value in (None, 0):
            return None
        try:
            return (float(price) / float(ma_value) - 1.0) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def _augment_with_realtime(df: pd.DataFrame, quote: Any) -> pd.DataFrame:
        result = df.copy()
        if result.empty:
            return result

        latest_idx = result.index[-1]
        price = getattr(quote, "price", None)
        if price is None:
            return result

        result.loc[latest_idx, "close"] = price
        if getattr(quote, "high", None) is not None:
            result.loc[latest_idx, "high"] = max(float(result.loc[latest_idx, "high"]), float(quote.high))
        if getattr(quote, "low", None) is not None:
            result.loc[latest_idx, "low"] = min(float(result.loc[latest_idx, "low"]), float(quote.low))
        if getattr(quote, "volume", None) is not None:
            result.loc[latest_idx, "volume"] = float(quote.volume)
        if getattr(quote, "amount", None) is not None:
            result.loc[latest_idx, "amount"] = float(quote.amount)
        if getattr(quote, "change_pct", None) is not None:
            result.loc[latest_idx, "pct_chg"] = float(quote.change_pct)
        if getattr(quote, "volume_ratio", None) is not None:
            result.loc[latest_idx, "volume_ratio"] = float(quote.volume_ratio)
        return result
