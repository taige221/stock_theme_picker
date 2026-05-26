# -*- coding: utf-8 -*-
"""ETF market snapshot service backed by mootdx and Tencent quote."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date, datetime, time, timedelta
import json
import logging
import re
from typing import Any, Dict, List, Optional

import akshare as ak
from mootdx.quotes import Quotes

from theme_picker.data.stock_index_loader import get_stock_name_index_map
from theme_picker.data.stock_mapping import STOCK_NAME_MAP, is_meaningful_stock_name
from theme_picker.config import get_config
from theme_picker.data_provider import DataFetcherManager
from theme_picker.data_provider.base import normalize_stock_code
from theme_picker.infrastructure.daily_bar_service import get_daily_bar_resolver
from theme_picker.infrastructure.etf_http_provider import get_etf_http_provider
from theme_picker.infrastructure.persistence import get_theme_picker_db
from theme_picker.infrastructure.stock_pool_service import canonicalize_stock_code, is_etf_code

logger = logging.getLogger(__name__)
DAILY_METRICS_SYNC_CUTOFF = time(hour=23, minute=0)
_CODELIKE_RE = re.compile(
    r"^(?:\d{5,6}(?:\.(?:SH|SZ|BJ|HK|SS))?|[A-Z]{2}\d{5,6}|[A-Z]{1,5})$",
    re.IGNORECASE,
)


class EtfMarketService:
    """Expose a small, Eastmoney-free ETF market snapshot."""

    def __init__(self) -> None:
        self.daily_bar_resolver = get_daily_bar_resolver()
        self.http_provider = get_etf_http_provider()
        self.fetcher_manager = DataFetcherManager()
        self.db = get_theme_picker_db()
        self._mootdx_etf_name_pairs: Optional[List[tuple[str, str]]] = None
        self._akshare_etf_name_pairs: Optional[List[tuple[str, str]]] = None

    def get_snapshot(self, stock_code: str, *, bars: int = 20) -> Dict[str, Any]:
        config = get_config()
        base_code = self._resolve_etf_input(stock_code)
        canonical_code = canonicalize_stock_code(base_code)
        errors: List[str] = []

        quote_payload: Dict[str, Any] = {}
        order_book_payload: Dict[str, Any] = {}
        kline_payload: List[Dict[str, Any]] = []
        profile_payload: Dict[str, Any] = {}
        top_holdings_payload: List[Dict[str, Any]] = []
        analysis_payload: Dict[str, Any] = {}
        estimated_iopv_payload: Dict[str, Any] = {}
        daily_metrics_payload: Dict[str, Any] = {}
        daily_bar_source = "wrapped_daily_bar:mootdx"
        quote_source = "unknown"

        try:
            quote_payload = self._run_with_timeout(
                lambda: self._fetch_quote_payload(canonical_code),
                timeout_seconds=float(getattr(config, "etf_realtime_quote_timeout_seconds", 8.0) or 0.0),
                task_name="etf realtime quote",
            )
        except Exception as exc:
            logger.warning("ETF 实时行情失败: code=%s error=%s", base_code, exc)
            errors.append(f"realtime quote failed: {exc}")
            try:
                quote_payload = self.http_provider.get_tencent_quote(base_code)
            except Exception as fallback_exc:
                logger.warning("ETF 腾讯行情兜底失败: code=%s error=%s", base_code, fallback_exc)
                errors.append(f"tencent quote fallback failed: {fallback_exc}")

        try:
            daily_result = self._run_with_timeout(
                lambda: self.daily_bar_resolver.resolve_daily_bars(
                    canonical_code,
                    bars=bars,
                    minimum_rows=1,
                ),
                timeout_seconds=float(getattr(config, "etf_daily_bar_timeout_seconds", 8.0) or 0.0),
                task_name="etf daily bars",
            )
            daily_bar_source = daily_result.data_source
            kline_payload = self._serialize_daily_bars(daily_result.frame)
            errors.extend(daily_result.errors)
        except Exception as exc:
            logger.warning("ETF 统一日K失败: code=%s error=%s", base_code, exc)
            errors.append(f"daily bars failed: {exc}")

        try:
            order_book_payload = self._run_with_timeout(
                lambda: self._fetch_mootdx_quote(base_code),
                timeout_seconds=float(getattr(config, "etf_mootdx_quote_timeout_seconds", 8.0) or 0.0),
                task_name="etf mootdx quote",
            )
        except Exception as exc:
            logger.warning("ETF mootdx 盘口失败: code=%s error=%s", base_code, exc)
            errors.append(f"mootdx quote failed: {exc}")

        try:
            profile_payload = self.http_provider.get_etf_profile(base_code)
        except Exception as exc:
            logger.warning("ETF 档案信息失败: code=%s error=%s", base_code, exc)
            errors.append(f"etf profile failed: {exc}")

        try:
            top_holdings_payload = self._run_with_timeout(
                lambda: self.http_provider.get_etf_top_holdings(base_code),
                timeout_seconds=float(getattr(config, "etf_top_holdings_timeout_seconds", 12.0) or 0.0),
                task_name="etf top holdings",
            )
        except Exception as exc:
            logger.warning("ETF 重仓股失败: code=%s error=%s", base_code, exc)
            errors.append(f"etf top holdings failed: {exc}")

        try:
            daily_metrics_payload = self._run_with_timeout(
                lambda: self._fetch_daily_metrics(canonical_code),
                timeout_seconds=float(getattr(config, "etf_daily_metrics_timeout_seconds", 12.0) or 0.0),
                task_name="etf daily metrics",
            )
        except Exception as exc:
            logger.warning("ETF 日频指标失败: code=%s error=%s", base_code, exc)
            errors.append(f"etf daily metrics failed: {exc}")

        if not quote_payload and order_book_payload:
            quote_payload = {
                "name": order_book_payload.get("name"),
                "price": order_book_payload.get("price"),
                "last_close": order_book_payload.get("last_close"),
                "open": order_book_payload.get("open"),
                "high": order_book_payload.get("high"),
                "low": order_book_payload.get("low"),
                "volume": order_book_payload.get("volume"),
                "amount": order_book_payload.get("amount"),
                "server_time": order_book_payload.get("server_time"),
                "raw_source": "mootdx_fallback",
            }

        if not quote_payload and not order_book_payload and not kline_payload:
            raise ValueError(f"未获取到 {canonical_code} 的 ETF 市场数据")

        quote_source = self._resolve_quote_source(quote_payload)
        try:
            estimated_iopv_payload = self._run_with_timeout(
                lambda: self._build_estimated_iopv(
                    etf_code=canonical_code,
                    quote_payload=quote_payload,
                    top_holdings=top_holdings_payload,
                ),
                timeout_seconds=float(getattr(config, "etf_estimated_iopv_timeout_seconds", 8.0) or 0.0),
                task_name="etf estimated iopv",
            )
        except Exception as exc:
            logger.warning("ETF estimated IOPV 失败: code=%s error=%s", base_code, exc)
            errors.append(f"estimated iopv failed: {exc}")
        analysis_payload = self._build_etf_analysis(
            stock_code=canonical_code,
            stock_name=quote_payload.get("name") or order_book_payload.get("name") or canonical_code,
            quote_payload=quote_payload,
            daily_bars=kline_payload,
            profile_payload=profile_payload,
        )

        response: Dict[str, Any] = {
            "stock_code": canonical_code,
            "base_code": base_code,
            "stock_name": quote_payload.get("name") or order_book_payload.get("name") or canonical_code,
            "instrument_type": "etf",
            "instrument_label": "ETF",
            "quote": quote_payload,
            "daily_bars": kline_payload,
            "order_book": order_book_payload,
            "profile": profile_payload,
            "top_holdings": top_holdings_payload,
            "analysis": analysis_payload,
            "estimated_iopv": estimated_iopv_payload,
            "daily_metrics": daily_metrics_payload,
            "data_sources": {
                "quote": quote_source,
                "daily_bars": daily_bar_source,
                "order_book": "mootdx",
                "profile": "eastmoney_fund_archive",
                "top_holdings": "eastmoney_fund_portfolio",
                "estimated_iopv": "top_holdings_weighted_realtime",
                "daily_metrics": daily_metrics_payload.get("data_source"),
            },
            "errors": errors,
        }
        return response

    @staticmethod
    def _run_with_timeout(task, *, timeout_seconds: float, task_name: str):
        if timeout_seconds <= 0:
            return task()

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(task)
            return future.result(timeout=max(0.0, float(timeout_seconds)))
        except FuturesTimeoutError as exc:
            raise TimeoutError(f"{task_name} timeout after {timeout_seconds:.1f}s") from exc
        finally:
            executor.shutdown(wait=False)

    @staticmethod
    def _resolve_quote_source(quote_payload: Dict[str, Any]) -> str:
        raw_source = str((quote_payload or {}).get("raw_source") or "").strip()
        if raw_source:
            return raw_source
        return "unknown"

    def _fetch_quote_payload(self, canonical_code: str) -> Dict[str, Any]:
        quote = self.fetcher_manager.get_realtime_quote(canonical_code, log_final_failure=False)
        if quote is not None and quote.has_basic_data():
            return {
                "name": quote.name,
                "price": quote.price,
                "last_close": quote.pre_close,
                "open": getattr(quote, "open_price", None),
                "high": quote.high,
                "low": quote.low,
                "volume": quote.volume,
                "amount": quote.amount,
                "change_pct": quote.change_pct,
                "volume_ratio": quote.volume_ratio,
                "turnover_rate": quote.turnover_rate,
                "server_time": getattr(quote, "timestamp", None),
                "raw_source": getattr(getattr(quote, "source", None), "value", None) or "realtime_priority",
            }

        base_code = normalize_stock_code(canonical_code)
        return self.http_provider.get_tencent_quote(base_code)

    def _resolve_etf_input(self, stock_code: str) -> str:
        raw = str(stock_code or "").strip()
        if not raw:
            raise ValueError("ETF 输入不能为空")

        if self._looks_like_stock_code(raw):
            normalized = normalize_stock_code(raw)
            if is_etf_code(normalized):
                return normalized

        resolved = self._resolve_etf_code_by_name(raw)
        if resolved:
            return normalize_stock_code(resolved)

        raise ValueError(f"无法识别 ETF 输入: {stock_code}")

    @staticmethod
    def _looks_like_stock_code(value: str) -> bool:
        return bool(_CODELIKE_RE.match(str(value or "").strip().upper()))

    def _resolve_etf_code_by_name(self, stock_name: str) -> Optional[str]:
        target = str(stock_name or "").strip()
        if not target:
            return None

        normalized_target = self._normalize_name_token(target)
        exact_matches: List[tuple[str, str]] = []
        fuzzy_matches: List[tuple[str, str]] = []

        for code, name in self._iter_etf_name_pairs():
            normalized_name = self._normalize_name_token(name)
            if name == target or normalized_name == normalized_target:
                exact_matches.append((code, name))
            elif target in name or normalized_target in normalized_name:
                fuzzy_matches.append((code, name))

        if len(exact_matches) == 1:
            return exact_matches[0][0]
        if len(exact_matches) > 1:
            candidates = "、".join(f"{name}({code})" for code, name in exact_matches[:5])
            raise ValueError(f"ETF 名称命中过多，请改用代码或更完整名称: {candidates}")
        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0][0]
        if len(fuzzy_matches) > 1:
            fuzzy_matches = sorted(fuzzy_matches, key=lambda item: (len(item[1]), item[1], item[0]))
            candidates = "、".join(f"{name}({code})" for code, name in fuzzy_matches[:5])
            raise ValueError(f"ETF 名称匹配不唯一，请补充更完整名称: {candidates}")
        return None

    def _iter_etf_name_pairs(self) -> List[tuple[str, str]]:
        pairs: List[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for code, name in STOCK_NAME_MAP.items():
            canonical = canonicalize_stock_code(code)
            clean_name = str(name).strip()
            pair_key = (canonical, clean_name)
            if not canonical or pair_key in seen:
                continue
            base_code = normalize_stock_code(canonical)
            if not is_etf_code(base_code) or not is_meaningful_stock_name(name, canonical):
                continue
            seen.add(pair_key)
            pairs.append((canonical, clean_name))

        for raw_code, name in get_stock_name_index_map().items():
            canonical = canonicalize_stock_code(raw_code)
            clean_name = str(name).strip()
            pair_key = (canonical, clean_name)
            if not canonical or pair_key in seen:
                continue
            base_code = normalize_stock_code(canonical)
            if not is_etf_code(base_code) or not is_meaningful_stock_name(name, canonical):
                continue
            seen.add(pair_key)
            pairs.append((canonical, clean_name))

        for canonical, name in self._iter_mootdx_etf_name_pairs():
            pair_key = (canonical, str(name).strip())
            if pair_key in seen or not is_meaningful_stock_name(name, canonical):
                continue
            seen.add(pair_key)
            pairs.append((canonical, str(name).strip()))

        for canonical, name in self._iter_akshare_etf_name_pairs():
            pair_key = (canonical, str(name).strip())
            if pair_key in seen or not is_meaningful_stock_name(name, canonical):
                continue
            seen.add(pair_key)
            pairs.append((canonical, str(name).strip()))

        return pairs

    def _iter_mootdx_etf_name_pairs(self) -> List[tuple[str, str]]:
        if self._mootdx_etf_name_pairs is not None:
            return self._mootdx_etf_name_pairs

        pairs: List[tuple[str, str]] = []
        try:
            client = Quotes.factory(market="std")
            frame = client.stock_all()
            if frame is not None and not frame.empty:
                for _, row in frame.iterrows():
                    canonical = canonicalize_stock_code(str(row.get("code") or "").strip())
                    if not canonical:
                        continue
                    base_code = normalize_stock_code(canonical)
                    if not is_etf_code(base_code):
                        continue
                    name = self._safe_text(row.get("name"))
                    if not is_meaningful_stock_name(name, canonical):
                        continue
                    pairs.append((canonical, str(name).strip()))
        except Exception as exc:
            logger.debug("ETF mootdx 名称索引加载失败: %s", exc)

        self._mootdx_etf_name_pairs = pairs
        return self._mootdx_etf_name_pairs

    def _iter_akshare_etf_name_pairs(self) -> List[tuple[str, str]]:
        if self._akshare_etf_name_pairs is not None:
            return self._akshare_etf_name_pairs

        pairs: List[tuple[str, str]] = []
        try:
            frame = ak.fund_etf_spot_em()
            if frame is not None and not frame.empty:
                for _, row in frame.iterrows():
                    canonical = canonicalize_stock_code(str(row.get("代码") or "").strip())
                    if not canonical:
                        continue
                    base_code = normalize_stock_code(canonical)
                    if not is_etf_code(base_code):
                        continue
                    name = self._safe_text(row.get("名称"))
                    if not is_meaningful_stock_name(name, canonical):
                        continue
                    pairs.append((canonical, str(name).strip()))
        except Exception as exc:
            logger.debug("ETF akshare 名称索引加载失败: %s", exc)

        self._akshare_etf_name_pairs = pairs
        return self._akshare_etf_name_pairs

    @staticmethod
    def _normalize_name_token(value: str) -> str:
        return re.sub(r"[\s\-_/]+", "", str(value or "").strip().upper())

    def _build_etf_analysis(
        self,
        *,
        stock_code: str,
        stock_name: str,
        quote_payload: Dict[str, Any],
        daily_bars: List[Dict[str, Any]],
        profile_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        closes = [float(item["close"]) for item in daily_bars if self._safe_float(item.get("close")) is not None]
        highs = [float(item["high"]) for item in daily_bars if self._safe_float(item.get("high")) is not None]
        latest_close = closes[-1] if closes else None
        current_price = self._safe_float(quote_payload.get("price")) or latest_close
        pct_chg = self._safe_float(quote_payload.get("change_pct")) or 0.0
        volume_ratio = self._safe_float(quote_payload.get("volume_ratio")) or 0.0
        turnover_rate = self._safe_float(quote_payload.get("turnover_rate")) or 0.0
        ma5 = self._rolling_mean(closes, 5)
        ma10 = self._rolling_mean(closes, 10)
        ma20 = self._rolling_mean(closes, 20)
        bias_ma10 = None
        if current_price and ma10 and ma10 > 0:
            bias_ma10 = (current_price - ma10) / ma10 * 100.0

        support = self._pick_nearest_support(current_price, [ma5, ma10, ma20])
        recent_high_20 = max(highs[-20:]) if highs else None
        pressure = self._pick_nearest_pressure(
            current_price,
            [recent_high_20, self._safe_float(quote_payload.get("limit_up"))],
        )
        tracking_target = str(profile_payload.get("tracking_target") or "").strip()

        signal = "仅观察"
        pattern = "观望整理"
        selected_reasons: List[str] = []
        risk_reasons: List[str] = []

        trend_up = bool(
            current_price and ma5 and ma10 and ma20
            and current_price >= ma10
            and ma5 >= ma10 >= ma20
        )
        has_acceleration_risk = bool(
            (bias_ma10 is not None and bias_ma10 >= 4.5)
            or pct_chg >= 4.0
            or volume_ratio >= 2.5
        )
        near_support = bool(
            current_price and ma10 and ma20
            and current_price <= ma10 * 1.01
            and current_price >= ma20 * 0.99
        )
        near_breakout = bool(
            current_price and recent_high_20
            and current_price >= recent_high_20 * 0.995
            and pct_chg >= 2.0
            and volume_ratio >= 1.2
        )
        weakened = bool(
            current_price and ma20 and current_price < ma20
        ) or bool(current_price and ma10 and pct_chg <= -2.5 and current_price < ma10)

        if has_acceleration_risk:
            signal = "不宜追高"
            pattern = "短线加速"
            if bias_ma10 is not None:
                risk_reasons.append(f"价格偏离 MA10 {bias_ma10:.2f}% ，短线位置偏热")
            if pct_chg >= 4.0:
                risk_reasons.append(f"当日涨幅 {pct_chg:.2f}% 偏快，继续追价的盈亏比一般")
            if volume_ratio >= 2.5:
                risk_reasons.append(f"量比 {volume_ratio:.2f} 偏高，短线分歧和回落风险同步抬升")
            selected_reasons.append("当前更适合等回踩或换手冷却，不适合把 ETF 当成追涨对象")
        elif near_breakout:
            signal = "短线异动"
            pattern = "临近突破"
            selected_reasons.append(f"价格已贴近近 20 日高点 {recent_high_20:.3f}，量价开始同步放大")
            selected_reasons.append(f"当日涨幅 {pct_chg:.2f}% 且量比 {volume_ratio:.2f}，右侧异动特征更明显")
            risk_reasons.append("如果后续冲高回落且量能不能继续放大，假突破概率会升高")
        elif near_support:
            signal = "低吸观察"
            pattern = "回踩支撑区"
            if support is not None:
                selected_reasons.append(f"价格回到支撑带附近，当前参考支撑约 {support:.3f}")
            selected_reasons.append("更适合等止跌承接确认后小仓验证，而不是提前抄底")
            if pct_chg <= -2.0:
                risk_reasons.append(f"当日回撤 {pct_chg:.2f}% 偏快，先看是否出现止跌企稳")
        elif trend_up and bias_ma10 is not None and 0.5 <= bias_ma10 <= 4.0 and pct_chg < 3.5:
            signal = "趋势跟随"
            pattern = "趋势延续"
            selected_reasons.append("均线保持抬升，ETF 更适合作为指数/板块趋势载体顺势跟随")
            selected_reasons.append(f"当前距离 MA10 偏离 {bias_ma10:.2f}% ，没有明显失真")
            if support is not None:
                selected_reasons.append(f"短线可把 {support:.3f} 附近视为第一观察支撑")
            risk_reasons.append("如果跌回 MA20 下方，趋势跟随逻辑就需要重新评估")
        elif weakened:
            signal = "仅观察"
            pattern = "转弱整理"
            risk_reasons.append("价格已经跌回中期均线下方，当前位置更像整理而不是舒服的出手位")
            if support is not None:
                risk_reasons.append(f"先看 {support:.3f} 一带能否重新站稳")
        else:
            signal = "仅观察"
            pattern = "区间整理"
            selected_reasons.append("ETF 本身没有明显走坏，但当前位置也没有给出特别舒服的盈亏比")
            if support is not None:
                selected_reasons.append(f"支撑观察位大致在 {support:.3f}")
            if pressure is not None:
                risk_reasons.append(f"上方最近压力大致在 {pressure:.3f}，靠近前不适合贸然加速追价")

        if tracking_target:
            selected_reasons.insert(0, f"它跟踪的是「{tracking_target}」，更适合当成主题/指数载体来看")

        summary_parts = [
            f"{stock_name} 当前更偏「{signal}」，形态属于「{pattern}」。",
        ]
        if tracking_target:
            summary_parts.append(f"这只 ETF 跟踪 {tracking_target}，观察重点应放在趋势位置和流动性，而不是公司基本面。")
        if signal == "不宜追高":
            summary_parts.append("短线位置已经偏热，更适合等回踩确认或换手降温后再看。")
        elif signal == "低吸观察":
            summary_parts.append("价格靠近支撑带，但更稳的做法仍是等止跌承接出现后再小仓验证。")
        elif signal == "趋势跟随":
            summary_parts.append("均线结构仍在抬升，操作上更适合顺势跟随，而不是逆势猜顶。")
        elif signal == "短线异动":
            summary_parts.append("如果后续量价继续放大，可以当成右侧异动继续跟踪；若冲高回落，则避免追价。")
        else:
            summary_parts.append("当前位置没有明显优势，先观察支撑与压力之间的博弈更合适。")

        return {
            "signal": signal,
            "pattern": pattern,
            "summary": " ".join(part for part in summary_parts if part).strip(),
            "support": support,
            "pressure": pressure,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "bias_ma10": bias_ma10,
            "selected_reasons": list(dict.fromkeys([item for item in selected_reasons if str(item).strip()]))[:4],
            "risk_reasons": list(dict.fromkeys([item for item in risk_reasons if str(item).strip()]))[:4],
        }

    def _build_estimated_iopv(
        self,
        *,
        etf_code: str,
        quote_payload: Dict[str, Any],
        top_holdings: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        etf_last_close = self._safe_float(quote_payload.get("last_close"))
        etf_price = self._safe_float(quote_payload.get("price"))
        if etf_last_close is None or etf_last_close <= 0 or not top_holdings:
            return {}

        holding_quotes = self._fetch_batch_mootdx_quotes(
            [
                str(item.get("stock_code") or "").strip()
                for item in top_holdings
                if str(item.get("stock_code") or "").strip()
            ]
        )
        if not holding_quotes:
            return {}

        weighted_return = 0.0
        coverage_weight_pct = 0.0
        matched_holdings_count = 0
        total_holdings_count = len(top_holdings)
        report_period = None

        for item in top_holdings:
            code = canonicalize_stock_code(str(item.get("stock_code") or "").strip())
            weight_pct = self._safe_float(item.get("weight_pct"))
            if report_period is None:
                report_period = self._safe_text(item.get("report_period"))
            if not code or weight_pct is None or weight_pct <= 0:
                continue
            holding_quote = holding_quotes.get(code)
            if not holding_quote:
                continue
            price = self._safe_float(holding_quote.get("price"))
            last_close = self._safe_float(holding_quote.get("last_close"))
            if price is None or last_close is None or last_close <= 0:
                continue

            holding_return = (price - last_close) / last_close
            weighted_return += (weight_pct / 100.0) * holding_return
            coverage_weight_pct += weight_pct
            matched_holdings_count += 1

        if matched_holdings_count == 0 or coverage_weight_pct <= 0:
            return {}

        estimated_iopv = etf_last_close * (1.0 + weighted_return)
        if estimated_iopv <= 0:
            return {}

        premium_discount_pct = None
        if etf_price is not None:
            premium_discount_pct = (etf_price - estimated_iopv) / estimated_iopv * 100.0

        return {
            "value": estimated_iopv,
            "premium_discount_pct": premium_discount_pct,
            "coverage_weight_pct": coverage_weight_pct,
            "matched_holdings_count": matched_holdings_count,
            "total_holdings_count": total_holdings_count,
            "report_period": report_period,
            "basis": "top_holdings_weighted_return",
            "note": "基于前十重仓股盘中涨跌幅估算，未覆盖持仓按不变处理，仅供参考，不等同于交易所正式 IOPV。",
        }

    def _fetch_daily_metrics(self, canonical_code: str) -> Dict[str, Any]:
        config = get_config()
        cached_snapshot = self._get_cached_daily_metrics(canonical_code)
        expected_trade_date = self._resolve_expected_daily_metrics_date()
        if self._is_daily_metrics_fresh(cached_snapshot, expected_trade_date=expected_trade_date):
            return self._with_daily_metrics_status(cached_snapshot, cache_status="hit")

        refreshed_metrics, _ = self._run_with_timeout(
            lambda: self._fetch_daily_metrics_online(canonical_code),
            timeout_seconds=float(getattr(config, "etf_daily_metrics_timeout_seconds", 12.0) or 0.0),
            task_name="etf daily metrics",
        )
        if self._is_daily_metrics_fresh(refreshed_metrics, expected_trade_date=expected_trade_date):
            return self._with_daily_metrics_status(refreshed_metrics, cache_status="refreshed")
        if cached_snapshot:
            return self._with_daily_metrics_status(cached_snapshot, cache_status="stale_fallback")
        return {}

    def refresh_daily_metrics(self, stock_code: str) -> Dict[str, Any]:
        config = get_config()
        base_code = self._resolve_etf_input(stock_code)
        canonical_code = canonicalize_stock_code(base_code)
        errors: List[str] = []
        expected_trade_date = self._resolve_expected_daily_metrics_date()

        try:
            refreshed_metrics, refresh_errors = self._run_with_timeout(
                lambda: self._fetch_daily_metrics_online(canonical_code),
                timeout_seconds=float(getattr(config, "etf_daily_metrics_timeout_seconds", 12.0) or 0.0),
                task_name="etf daily metrics",
            )
            errors.extend(refresh_errors)
        except Exception as exc:
            refreshed_metrics = {}
            errors.append(str(exc))
        if self._is_daily_metrics_fresh(refreshed_metrics, expected_trade_date=expected_trade_date):
            return {
                "stock_code": canonical_code,
                "base_code": base_code,
                "instrument_type": "etf",
                "instrument_label": "ETF",
                "refreshed": True,
                "cache_status": "refreshed",
                "daily_metrics": self._with_daily_metrics_status(refreshed_metrics, cache_status="refreshed"),
                "errors": errors,
            }

        cached_snapshot = self._get_cached_daily_metrics(canonical_code)
        if cached_snapshot:
            return {
                "stock_code": canonical_code,
                "base_code": base_code,
                "instrument_type": "etf",
                "instrument_label": "ETF",
                "refreshed": False,
                "cache_status": "stale_fallback",
                "daily_metrics": self._with_daily_metrics_status(cached_snapshot, cache_status="stale_fallback"),
                "errors": errors,
            }

        raise ValueError(f"未获取到 {canonical_code} 的 ETF 日频指标")

    def _get_cached_daily_metrics(self, canonical_code: str) -> Optional[Dict[str, Any]]:
        cached_snapshot = self.db.get_latest_etf_daily_metrics_snapshot(canonical_code)
        if cached_snapshot is None:
            return None
        return cached_snapshot.to_dict()

    def _is_daily_metrics_fresh(
        self,
        metrics: Optional[Dict[str, Any]],
        *,
        expected_trade_date: date,
    ) -> bool:
        if not metrics or not metrics.get("trade_date"):
            return False
        try:
            return self._parse_iso_date(metrics.get("trade_date")) >= expected_trade_date
        except (TypeError, ValueError):
            return False

    def _fetch_daily_metrics_online(self, canonical_code: str) -> tuple[Dict[str, Any], List[str]]:
        errors: List[str] = []
        exchange = canonical_code.split(".")[-1].upper() if "." in canonical_code else ""
        if exchange == "SH":
            for offset in range(0, 8):
                trade_date = datetime.now().date() - timedelta(days=offset)
                try:
                    rows = self.http_provider.get_sse_etf_daily_metrics(trade_date)
                    self.db.save_etf_daily_metrics_snapshots(rows)
                    matched = self._match_daily_metrics(canonical_code, rows)
                    if matched:
                        matched["updated_at"] = datetime.now().isoformat()
                        return matched, errors
                except Exception as exc:
                    errors.append(f"sse daily metrics failed({trade_date.isoformat()}): {exc}")
            return {}, errors

        if exchange == "SZ":
            try:
                rows = self.http_provider.get_szse_etf_daily_metrics()
                self.db.save_etf_daily_metrics_snapshots(rows)
                matched = self._match_daily_metrics(canonical_code, rows)
                if matched:
                    matched["updated_at"] = datetime.now().isoformat()
                    return matched, errors
            except Exception as exc:
                errors.append(f"szse daily metrics failed(latest): {exc}")

            for offset in range(0, 8):
                trade_date = datetime.now().date() - timedelta(days=offset)
                try:
                    rows = self.http_provider.get_szse_etf_daily_metrics(
                        start_date=trade_date,
                        end_date=trade_date,
                    )
                    self.db.save_etf_daily_metrics_snapshots(rows)
                    matched = self._match_daily_metrics(canonical_code, rows)
                    if matched:
                        matched["updated_at"] = datetime.now().isoformat()
                        return matched, errors
                except Exception as exc:
                    errors.append(f"szse daily metrics failed({trade_date.isoformat()}): {exc}")
        return {}, errors

    @staticmethod
    def _with_daily_metrics_status(metrics: Dict[str, Any], *, cache_status: str) -> Dict[str, Any]:
        payload = dict(metrics or {})
        payload["cache_status"] = cache_status
        return payload

    @staticmethod
    def _resolve_expected_daily_metrics_date(now: Optional[datetime] = None) -> date:
        current = now or datetime.now()
        if current.time() >= DAILY_METRICS_SYNC_CUTOFF:
            target = current.date()
        else:
            target = current.date() - timedelta(days=1)
        return EtfMarketService._previous_weekday_if_needed(target)

    @staticmethod
    def _previous_weekday_if_needed(value: date) -> date:
        result = value
        while result.weekday() >= 5:
            result -= timedelta(days=1)
        return result

    @staticmethod
    def _parse_iso_date(value: Optional[str]) -> date:
        text = str(value or "").strip()
        return datetime.strptime(text[:10], "%Y-%m-%d").date()

    @staticmethod
    def _match_daily_metrics(canonical_code: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not rows:
            return {}
        target = canonicalize_stock_code(canonical_code)
        for row in rows:
            row_code = canonicalize_stock_code(str(row.get("stock_code") or "").strip())
            if row_code == target:
                return {
                    "trade_date": row.get("trade_date"),
                    "fund_shares": row.get("fund_shares"),
                    "nav": row.get("nav"),
                    "derived_fund_size_yi": row.get("derived_fund_size_yi"),
                    "exchange": row.get("exchange"),
                    "data_source": row.get("data_source"),
                }
        return {}

    @staticmethod
    def _rolling_mean(values: List[float], window: int) -> Optional[float]:
        if len(values) < window or window <= 0:
            return None
        segment = values[-window:]
        if not segment:
            return None
        return sum(segment) / len(segment)

    @staticmethod
    def _pick_nearest_support(current_price: Optional[float], candidates: List[Optional[float]]) -> Optional[float]:
        valid = sorted({value for value in candidates if value is not None and value > 0}, reverse=True)
        if not valid:
            return None
        if not current_price or current_price <= 0:
            return valid[0]
        below = [level for level in valid if level <= current_price]
        return below[0] if below else valid[-1]

    @staticmethod
    def _pick_nearest_pressure(current_price: Optional[float], candidates: List[Optional[float]]) -> Optional[float]:
        valid = sorted({value for value in candidates if value is not None and value > 0})
        if not valid:
            return None
        if not current_price or current_price <= 0:
            return valid[-1]
        above = [level for level in valid if level >= current_price]
        return above[0] if above else valid[-1]

    def _fetch_mootdx_quote(self, base_code: str) -> Dict[str, Any]:
        client = Quotes.factory(market="std")
        df = client.quotes(symbol=[base_code])
        if df is None or df.empty:
            return {}

        row = df.iloc[0]
        return {
            "name": self._safe_text(row.get("name")),
            "price": self._safe_float(row.get("price")),
            "last_close": self._safe_float(row.get("last_close")),
            "open": self._safe_float(row.get("open")),
            "high": self._safe_float(row.get("high")),
            "low": self._safe_float(row.get("low")),
            "volume": self._safe_float(row.get("vol") or row.get("volume")),
            "amount": self._safe_float(row.get("amount")),
            "server_time": self._safe_text(row.get("servertime")),
            "bid1": self._safe_float(row.get("bid1")),
            "ask1": self._safe_float(row.get("ask1")),
            "bid_vol1": self._safe_float(row.get("bid_vol1")),
            "ask_vol1": self._safe_float(row.get("ask_vol1")),
            "raw_source": "mootdx",
        }

    def _fetch_batch_mootdx_quotes(self, stock_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        normalized_codes = []
        for code in stock_codes:
            normalized = normalize_stock_code(code)
            if not normalized:
                continue
            # mootdx only supports CN numeric symbols here.  Overseas ETF holdings
            # such as AAPL / MSFT would otherwise bubble up low-level socket/protocol
            # errors like "head_buf is not 0x10 : b''".
            if not normalized.isdigit() or len(normalized) != 6:
                continue
            normalized_codes.append(normalized)
        if not normalized_codes:
            return {}

        client = Quotes.factory(market="std")
        df = client.quotes(symbol=normalized_codes)
        if df is None or df.empty:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            raw_code = str(row.get("code") or "").strip()
            canonical_code = canonicalize_stock_code(raw_code)
            if not canonical_code:
                continue
            results[canonical_code] = {
                "price": self._safe_float(row.get("price")),
                "last_close": self._safe_float(row.get("last_close")),
                "name": self._safe_text(row.get("name")),
            }
        return results

    @staticmethod
    def _serialize_daily_bars(frame) -> List[Dict[str, Any]]:
        if frame is None or getattr(frame, "empty", True):
            return []
        rows: List[Dict[str, Any]] = []
        for item in get_daily_bar_resolver().serialize_frame(frame):
            rows.append(
                {
                    "datetime": item.get("datetime"),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "close": item.get("close"),
                    "volume": item.get("volume"),
                    "amount": item.get("amount"),
                }
            )
        return rows

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value in (None, "", "--"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_text(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        if isinstance(value, (dict, list, tuple)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        return str(value).replace("\x00", "").strip()


_ETF_MARKET_SERVICE: Optional[EtfMarketService] = None


def get_etf_market_service() -> EtfMarketService:
    global _ETF_MARKET_SERVICE
    if _ETF_MARKET_SERVICE is None:
        _ETF_MARKET_SERVICE = EtfMarketService()
    return _ETF_MARKET_SERVICE
