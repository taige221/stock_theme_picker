# -*- coding: utf-8 -*-
"""
===================================
Single Stock Query Service
===================================
"""

from __future__ import annotations

import re
import threading
import uuid
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from theme_picker.application.registry_service import ThemeRegistryService
from theme_picker.application.stock_signal_service import StockSignalService
from theme_picker.application.stock_text_supplement_service import StockTextSupplementService
from theme_picker.application.stock_theme_attribution_service import StockThemeAttributionService
from theme_picker.config import get_config
from theme_picker.data.stock_index_loader import get_stock_name_index_map
from theme_picker.data.stock_mapping import STOCK_NAME_MAP, is_meaningful_stock_name
from theme_picker.data_provider import DataFetcherManager
from theme_picker.data_provider.base import normalize_stock_code
from theme_picker.infrastructure.persistence import get_theme_picker_db, save_stock_query_record
from theme_picker.infrastructure.stock_pool_service import build_stock_code_variants, canonicalize_stock_code
from theme_picker.stock_analyzer import StockTrendAnalyzer

_CODELIKE_RE = re.compile(
    r"^(?:\d{5,6}(?:\.(?:SH|SZ|BJ|HK|SS))?|[A-Z]{2}\d{5,6}|[A-Z]{1,5})$",
    re.IGNORECASE,
)
_A_SHARE_LIKE_RE = re.compile(r"^\d{6}(?:\.(?:SH|SZ|BJ))?$", re.IGNORECASE)
_STOCK_QUERY_A_SHARE_DAILY_ROUTE = (
    "TickFlowFetcher",
    "AkshareFetcher:sina",
    "AkshareFetcher:tencent",
    "TushareFetcher",
)
_STOCK_QUERY_UNPROXY_FETCHERS = {
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
_PROXY_ENV_LOCK = threading.Lock()

logger = logging.getLogger(__name__)


class StockQueryService:
    """Analyze one stock with a stock-first diagnosis path."""

    def __init__(
        self,
        *,
        registry_service: Optional[ThemeRegistryService] = None,
        fetcher_manager: Optional[DataFetcherManager] = None,
        trend_analyzer: Optional[StockTrendAnalyzer] = None,
        signal_service: Optional[StockSignalService] = None,
        text_supplement_service: Optional[StockTextSupplementService] = None,
        theme_attribution_service: Optional[StockThemeAttributionService] = None,
        db=None,
    ):
        self.config = get_config()
        self.registry_service = registry_service or ThemeRegistryService()
        self.fetcher_manager = fetcher_manager or DataFetcherManager()
        self.trend_analyzer = trend_analyzer or StockTrendAnalyzer()
        self.signal_service = signal_service or StockSignalService()
        self.text_supplement_service = text_supplement_service or StockTextSupplementService()
        self.theme_attribution_service = (
            theme_attribution_service
            or StockThemeAttributionService(registry_service=self.registry_service)
        )
        self.db = db or get_theme_picker_db()

    def analyze(self, request: Any, *, query_id: Optional[str] = None) -> Dict[str, Any]:
        stock_code = self._resolve_stock_code(request)
        requested_name = self._resolve_requested_name(request)
        stock_name = requested_name or stock_code
        if requested_name:
            stock_name = (
                requested_name
                or self.fetcher_manager.get_stock_name(stock_code, allow_realtime=False)
                or stock_code
            )

        daily_df, daily_source = self._load_daily_data(stock_code, days=120)
        if daily_df is None or daily_df.empty:
            raise ValueError(f"未获取到 {stock_code} 的日线数据")

        daily_df = daily_df.sort_values("date").reset_index(drop=True)
        quote = self.fetcher_manager.get_realtime_quote(stock_code, log_final_failure=False)
        if quote and getattr(quote, "name", None):
            stock_name = quote.name

        trend_df = self._augment_with_realtime(daily_df.copy(), quote) if quote else daily_df.copy()
        trend_result = self.trend_analyzer.analyze(trend_df, stock_code)
        latest = trend_df.iloc[-1]

        current_price = self._safe_float(getattr(quote, "price", None) if quote else trend_result.current_price)
        pct_chg = self._safe_float(getattr(quote, "change_pct", None) if quote else latest.get("pct_chg"))
        volume_ratio = self._safe_float(getattr(quote, "volume_ratio", None) if quote else latest.get("volume_ratio"))
        turnover_rate = self._safe_float(getattr(quote, "turnover_rate", None))

        chip_data = self._load_chip_distribution(stock_code)
        fundamental_context = self._load_fundamental_context(stock_code, quote=quote)
        self._augment_fundamental_text_supplements(
            stock_code=stock_code,
            stock_name=stock_name,
            fundamental_context=fundamental_context,
        )
        normalized_fundamental_context = self._normalize_fundamental_context(fundamental_context)
        stock_news_summary = self._load_stock_news_summary(
            stock_code=stock_code,
            stock_name=stock_name,
        )
        valuation_snapshot = self._extract_valuation_snapshot(quote, normalized_fundamental_context)
        signal_payload = self.signal_service.analyze(
            trend_result=trend_result,
            current_price=current_price,
            pct_chg=pct_chg,
            volume_ratio=volume_ratio,
            turnover_rate=turnover_rate,
            chip_data=chip_data,
            fundamental_context=normalized_fundamental_context,
        )
        theme_attributions = self.theme_attribution_service.attribute(stock_code)

        query_id = query_id or uuid.uuid4().hex
        news_provider = None
        if isinstance(stock_news_summary, dict):
            news_provider = str(stock_news_summary.get("provider") or "").strip() or None

        payload = {
            "query_id": query_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "current_price": current_price,
            "pct_chg": pct_chg,
            "turnover_rate": turnover_rate,
            "volume_ratio": volume_ratio,
            "pe_ratio": valuation_snapshot["pe_ratio"],
            "pb_ratio": valuation_snapshot["pb_ratio"],
            "total_mv": valuation_snapshot["total_mv"],
            "circ_mv": valuation_snapshot["circ_mv"],
            "trend_score": self._safe_float(trend_result.signal_score),
            "signal": signal_payload["signal"],
            "pattern": signal_payload["pattern"],
            "support": signal_payload["support"],
            "pressure": signal_payload["pressure"],
            "ma10": self._safe_float(trend_result.ma10),
            "ma20": self._safe_float(trend_result.ma20),
            "bias_ma10": self._safe_float(trend_result.bias_ma10),
            "trend_status": trend_result.trend_status.value,
            "buy_signal": trend_result.buy_signal.value,
            "selected_reasons": signal_payload["selected_reasons"],
            "excluded_reasons": signal_payload["excluded_reasons"],
            "theme_attributions": theme_attributions,
            "themes": theme_attributions,
            "stock_news_summary": stock_news_summary,
            "fundamental_context": normalized_fundamental_context,
            "fundamental_coverage": self._extract_fundamental_coverage(normalized_fundamental_context),
            "fundamental_errors": self._extract_fundamental_errors(normalized_fundamental_context),
            "fundamental_details": self._extract_fundamental_details(normalized_fundamental_context),
            "data_sources": {
                "daily": daily_source,
                "realtime": getattr(getattr(quote, "source", None), "value", None) if quote else None,
                "chip": getattr(chip_data, "source", None) if chip_data else None,
                "fundamental": self._resolve_fundamental_source(normalized_fundamental_context),
                "news": news_provider,
            },
        }
        self._persist_query_record(
            query_id=query_id,
            request=request,
            query_text=self._resolve_query_text(request),
            payload=payload,
        )
        return payload

    def _resolve_stock_code(self, request: Any) -> str:
        query = str(getattr(request, "stock_code", None) or getattr(request, "query", None) or "").strip()
        if query and self._looks_like_stock_code(query):
            return canonicalize_stock_code(query)

        stock_name = str(getattr(request, "stock_name", None) or getattr(request, "query", None) or "").strip()
        if stock_name:
            resolved = self._resolve_stock_code_by_name(stock_name)
            if resolved:
                return resolved

        raise ValueError(f"无法识别股票输入: {query or stock_name}")

    def _resolve_requested_name(self, request: Any) -> str:
        stock_name = str(getattr(request, "stock_name", None) or "").strip()
        if stock_name:
            return stock_name
        query = str(getattr(request, "query", None) or "").strip()
        if query and not self._looks_like_stock_code(query):
            return query
        return ""

    @staticmethod
    def _resolve_query_text(request: Any) -> str:
        query = str(getattr(request, "query", None) or "").strip()
        if query:
            return query
        stock_code = str(getattr(request, "stock_code", None) or "").strip()
        if stock_code:
            return stock_code
        stock_name = str(getattr(request, "stock_name", None) or "").strip()
        return stock_name

    @staticmethod
    def _looks_like_stock_code(value: str) -> bool:
        return bool(_CODELIKE_RE.match(str(value or "").strip().upper()))

    def _resolve_stock_code_by_name(self, stock_name: str) -> Optional[str]:
        target = str(stock_name or "").strip()
        if not target:
            return None

        exact_matches: List[str] = []
        fuzzy_matches: List[str] = []
        for code, name in self._iter_stock_name_pairs():
            if name == target:
                exact_matches.append(code)
            elif target in name:
                fuzzy_matches.append(code)

        if exact_matches:
            return exact_matches[0]
        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0]
        return None

    def _iter_stock_name_pairs(self) -> List[tuple[str, str]]:
        pairs: List[tuple[str, str]] = []
        seen = set()

        for code, name in STOCK_NAME_MAP.items():
            canonical = canonicalize_stock_code(code)
            if not canonical or not is_meaningful_stock_name(name, canonical) or canonical in seen:
                continue
            seen.add(canonical)
            pairs.append((canonical, str(name).strip()))

        for raw_code, name in get_stock_name_index_map().items():
            canonical = canonicalize_stock_code(raw_code)
            if not canonical or canonical in seen or not is_meaningful_stock_name(name, canonical):
                continue
            seen.add(canonical)
            pairs.append((canonical, str(name).strip()))

        return pairs

    def _load_daily_data(self, stock_code: str, *, days: int = 120):
        stock_code_text = str(stock_code or "").strip().upper()
        if not _A_SHARE_LIKE_RE.match(stock_code_text):
            return self.fetcher_manager.get_daily_data(stock_code, days=days)

        normalized_code = normalize_stock_code(stock_code)
        timeout_seconds = float(
            getattr(self.config, "stock_query_daily_fetch_timeout_seconds", 8.0) or 0.0
        )
        errors: List[str] = []

        for route_name in _STOCK_QUERY_A_SHARE_DAILY_ROUTE:
            try:
                daily_df = self._run_with_timeout(
                    lambda current_route=route_name: self._fetch_single_stock_daily_route(
                        current_route,
                        normalized_code,
                        days=days,
                    ),
                    timeout_seconds=timeout_seconds,
                    task_name=f"single_stock_daily:{route_name}",
                    without_proxy=(
                        bool(getattr(self.config, "stock_query_daily_unproxy_enabled", True))
                        and self._is_unproxy_daily_route(route_name)
                    ),
                )
                if daily_df is not None and not daily_df.empty:
                    return daily_df, route_name
            except Exception as exc:
                logger.warning("单股查询日线源失败: code=%s source=%s error=%s", stock_code, route_name, exc)
                errors.append(f"{route_name}: {exc}")

        if bool(getattr(self.config, "stock_query_allow_daily_cache_fallback", True)):
            cached = self._load_cached_daily_data(stock_code, days=days)
            if cached is not None:
                logger.warning("单股查询在线日线全部失败，退回本地缓存: code=%s", stock_code)
                return cached, "stock_daily_cache_fallback"

        if errors:
            raise ValueError(f"未获取到 {stock_code} 的日线数据: {' | '.join(errors[:4])}")
        raise ValueError(f"未获取到 {stock_code} 的日线数据")

    def _fetch_single_stock_daily_route(self, route_name: str, stock_code: str, *, days: int) -> pd.DataFrame:
        if route_name == "TickFlowFetcher":
            return self._fetch_tickflow_daily_data(stock_code, days=days)
        if route_name == "AkshareFetcher:sina":
            return self._fetch_akshare_daily_data(stock_code, source="sina", days=days)
        if route_name == "AkshareFetcher:tencent":
            return self._fetch_akshare_daily_data(stock_code, source="tencent", days=days)
        if route_name == "TushareFetcher":
            return self._fetch_named_fetcher_daily_data("TushareFetcher", stock_code, days=days)
        raise ValueError(f"未知单股日线路由: {route_name}")

    def _fetch_tickflow_daily_data(self, stock_code: str, *, days: int) -> pd.DataFrame:
        fetcher = self.fetcher_manager._get_tickflow_fetcher()
        if fetcher is None:
            raise ValueError("TickFlow API key 未配置或 TickFlow 初始化失败")
        return fetcher.get_daily_data(stock_code, days=days)

    def _fetch_akshare_daily_data(self, stock_code: str, *, source: str, days: int) -> pd.DataFrame:
        fetcher = self._get_named_fetcher("AkshareFetcher")
        if fetcher is None:
            raise ValueError("AkshareFetcher 不可用")

        start_date, end_date = self._resolve_daily_date_window(days)
        if source == "sina":
            raw_df = fetcher._fetch_stock_data_sina(stock_code, start_date, end_date)
        elif source == "tencent":
            raw_df = fetcher._fetch_stock_data_tx(stock_code, start_date, end_date)
        else:
            raise ValueError(f"未知 Akshare 日线子源: {source}")

        normalized_df = fetcher._normalize_data(raw_df, stock_code)
        cleaned_df = fetcher._clean_data(normalized_df)
        return fetcher._calculate_indicators(cleaned_df)

    def _fetch_named_fetcher_daily_data(self, fetcher_name: str, stock_code: str, *, days: int) -> pd.DataFrame:
        fetcher = self._get_named_fetcher(fetcher_name)
        if fetcher is None:
            raise ValueError(f"{fetcher_name} 不可用")
        return fetcher.get_daily_data(stock_code, days=days)

    def _get_named_fetcher(self, fetcher_name: str):
        for fetcher in self.fetcher_manager._get_fetchers_snapshot():
            if fetcher.name == fetcher_name:
                return fetcher
        return None

    @staticmethod
    def _resolve_daily_date_window(days: int) -> tuple[str, str]:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=days * 2)
        return start_dt.strftime("%Y-%m-%d"), end_date

    @staticmethod
    def _is_unproxy_daily_route(route_name: str) -> bool:
        fetcher_name = route_name.split(":", 1)[0]
        return fetcher_name in _STOCK_QUERY_UNPROXY_FETCHERS

    def _load_cached_daily_data(self, stock_code: str, *, days: int = 120) -> Optional[pd.DataFrame]:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=max(days * 2, 240))
        best_rows: List[Any] = []

        for candidate in build_stock_code_variants(stock_code):
            try:
                rows = self.db.get_data_range(candidate, start_date, end_date)
            except Exception:
                continue
            if len(rows) > len(best_rows):
                best_rows = rows

        if not best_rows:
            return None

        latest_row_date = max((row.date for row in best_rows if getattr(row, "date", None)), default=None)
        if latest_row_date is None:
            return None

        stale_days = (end_date - latest_row_date).days
        if len(best_rows) < 30 or stale_days > 21:
            return None

        frame = pd.DataFrame([row.to_dict() for row in best_rows])
        if frame.empty:
            return None
        return frame.sort_values("date").reset_index(drop=True)

    def _load_chip_distribution(self, stock_code: str):
        timeout_seconds = float(getattr(self.config, "stock_query_chip_timeout_seconds", 2.5) or 0.0)
        if timeout_seconds <= 0:
            return None

        result_box: Dict[str, Any] = {}

        def _task() -> None:
            try:
                result_box["value"] = self.fetcher_manager.get_chip_distribution(stock_code)
            except Exception as exc:
                result_box["error"] = exc

        worker = threading.Thread(target=_task, name="stock-query-chip", daemon=True)
        worker.start()
        worker.join(timeout=timeout_seconds)

        if worker.is_alive():
            logger.warning("单股查询筹码分布超时: code=%s timeout=%.1fs", stock_code, timeout_seconds)
            return None

        if "error" in result_box:
            return None
        return result_box.get("value")

    @staticmethod
    def _run_with_timeout(task, *, timeout_seconds: float, task_name: str, without_proxy: bool = False):
        if timeout_seconds <= 0:
            return task()

        result_box: Dict[str, Any] = {}

        def _task() -> None:
            try:
                result_box["value"] = task()
            except Exception as exc:
                result_box["error"] = exc

        worker = threading.Thread(target=_task, name=task_name, daemon=True)
        env_snapshot: Dict[str, Optional[str]] = {}
        lock = _PROXY_ENV_LOCK if without_proxy else None
        if lock is not None:
            lock.acquire()
        try:
            if without_proxy:
                env_snapshot = StockQueryService._disable_proxy_env_for_attempt()
            worker.start()
            worker.join(timeout=timeout_seconds)
        finally:
            if without_proxy:
                StockQueryService._restore_proxy_env_after_attempt(env_snapshot)
            if lock is not None:
                lock.release()

        if worker.is_alive():
            raise TimeoutError(f"{task_name} timeout after {timeout_seconds:.1f}s")
        if "error" in result_box:
            raise result_box["error"]
        return result_box.get("value")

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

    def _load_fundamental_context(self, stock_code: str, *, quote: Any = None) -> Optional[Dict[str, Any]]:
        try:
            return self.fetcher_manager.get_fundamental_context(stock_code, quote_payload=quote)
        except Exception as exc:
            return self.fetcher_manager.build_failed_fundamental_context(stock_code, str(exc))

    def _augment_fundamental_text_supplements(
        self,
        *,
        stock_code: str,
        stock_name: str,
        fundamental_context: Optional[Dict[str, Any]],
    ) -> None:
        if not isinstance(fundamental_context, dict):
            return
        if not self.text_supplement_service.is_available:
            return

        timeout_seconds = float(getattr(self.config, "stock_query_text_timeout_seconds", 2.0) or 0.0)
        if timeout_seconds <= 0:
            return

        try:
            earnings_text = self._run_with_timeout(
                lambda: self.text_supplement_service.get_earnings_text(stock_code, stock_name),
                timeout_seconds=timeout_seconds,
                task_name="stock-query-earnings-text",
            )
        except Exception:
            earnings_text = None
        if isinstance(earnings_text, dict) and earnings_text:
            self._merge_fundamental_block_data(fundamental_context, "earnings", earnings_text)

        try:
            institution_text = self._run_with_timeout(
                lambda: self.text_supplement_service.get_institution_text(stock_code, stock_name),
                timeout_seconds=timeout_seconds,
                task_name="stock-query-institution-text",
            )
        except Exception:
            institution_text = None
        if isinstance(institution_text, dict) and institution_text:
            self._merge_fundamental_block_data(fundamental_context, "institution", institution_text)

    def _load_stock_news_summary(
        self,
        *,
        stock_code: str,
        stock_name: str,
    ) -> Dict[str, Any]:
        if not self.text_supplement_service.is_available:
            return {}

        timeout_seconds = float(getattr(self.config, "stock_query_news_timeout_seconds", 1.8) or 0.0)
        if timeout_seconds <= 0:
            return {}

        try:
            summary = self._run_with_timeout(
                lambda: self.text_supplement_service.get_stock_news_summary(stock_code, stock_name),
                timeout_seconds=timeout_seconds,
                task_name="stock-query-news-summary",
            )
        except Exception:
            summary = None
        return summary if isinstance(summary, dict) else {}

    @staticmethod
    def _merge_fundamental_block_data(
        fundamental_context: Dict[str, Any],
        block_name: str,
        extra_data: Dict[str, Any],
    ) -> None:
        block = fundamental_context.get(block_name)
        if not isinstance(block, dict):
            return
        data = block.get("data")
        if not isinstance(data, dict):
            data = {}
            block["data"] = data
        data.update(extra_data)
        if data:
            status = str(block.get("status") or "").strip().lower()
            if status in {"", "failed", "not_supported"}:
                block["status"] = "partial"
        provider = str(extra_data.get("text_provider") or extra_data.get("provider") or "").strip()
        if provider:
            source_chain = block.get("source_chain")
            if not isinstance(source_chain, list):
                source_chain = []
                block["source_chain"] = source_chain
            if not any(str(item.get("provider") or "").strip() == provider for item in source_chain if isinstance(item, dict)):
                source_chain.append(
                    {
                        "provider": provider,
                        "result": "ok",
                        "duration_ms": 0,
                    }
                )

    @staticmethod
    def _resolve_fundamental_source(fundamental_context: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(fundamental_context, dict):
            return None
        status = str(fundamental_context.get("status") or "").strip().lower()
        if status in {"ok", "full", "partial", "failed", "not_supported"}:
            return status
        source_chain = fundamental_context.get("source_chain")
        if isinstance(source_chain, list) and source_chain:
            for item in source_chain:
                if not isinstance(item, dict):
                    continue
                provider = str(item.get("provider") or "").strip()
                if provider:
                    return provider
        return status or None

    def _normalize_fundamental_context(self, fundamental_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        block_names = (
            "valuation",
            "growth",
            "earnings",
            "institution",
            "capital_flow",
            "dragon_tiger",
            "boards",
        )
        normalized: Dict[str, Any] = {
            "market": None,
            "status": "failed",
            "coverage": {},
            "source_chain": [],
            "errors": [],
            "elapsed_ms": None,
        }
        if isinstance(fundamental_context, dict):
            normalized["market"] = fundamental_context.get("market")
            normalized["status"] = fundamental_context.get("status") or "failed"
            normalized["coverage"] = self._normalize_str_dict(fundamental_context.get("coverage"))
            normalized["source_chain"] = self._normalize_source_chain(fundamental_context.get("source_chain"))
            normalized["errors"] = self._normalize_error_list(fundamental_context.get("errors"))
            elapsed_ms = fundamental_context.get("elapsed_ms")
            if isinstance(elapsed_ms, int):
                normalized["elapsed_ms"] = elapsed_ms

        for block_name in block_names:
            raw_block = fundamental_context.get(block_name) if isinstance(fundamental_context, dict) else None
            normalized[block_name] = self._normalize_fundamental_block(raw_block)

        normalized["coverage"] = {
            **{key: str(value) for key, value in normalized["coverage"].items() if key},
            **{
                block_name: str(normalized[block_name].get("status") or "failed")
                for block_name in block_names
            },
        }
        merged_errors = list(normalized["errors"])
        for block_name in block_names:
            for item in normalized[block_name]["errors"]:
                if item not in merged_errors:
                    merged_errors.append(item)
            normalized["source_chain"].extend(normalized[block_name]["source_chain"])
        normalized["errors"] = merged_errors
        normalized["source_chain"] = self._dedupe_source_chain(normalized["source_chain"])

        if not normalized.get("market") and isinstance(fundamental_context, dict):
            normalized["market"] = fundamental_context.get("market")
        if not normalized.get("status"):
            coverage_values = set(normalized["coverage"].values())
            if coverage_values == {"not_supported"}:
                normalized["status"] = "not_supported"
            elif "failed" in coverage_values or "partial" in coverage_values:
                normalized["status"] = "partial"
            else:
                normalized["status"] = "ok"
        return normalized

    def _normalize_fundamental_block(self, block: Any) -> Dict[str, Any]:
        normalized = {
            "status": "failed",
            "data": {},
            "source_chain": [],
            "errors": [],
        }
        if not isinstance(block, dict):
            return normalized
        normalized["status"] = str(block.get("status") or "failed")
        data = block.get("data")
        normalized["data"] = dict(data) if isinstance(data, dict) else {}
        normalized["source_chain"] = self._normalize_source_chain(block.get("source_chain"))
        normalized["errors"] = self._normalize_error_list(block.get("errors"))
        return normalized

    @staticmethod
    def _normalize_str_dict(value: Any) -> Dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {
            str(key): str(item)
            for key, item in value.items()
            if str(key or "").strip() and item is not None
        }

    @staticmethod
    def _normalize_error_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        normalized: List[str] = []
        seen = set()
        for item in value:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    @staticmethod
    def _normalize_source_chain(value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(dict(item))
            elif isinstance(item, str) and item.strip():
                normalized.append({"provider": item.strip(), "result": "ok", "duration_ms": 0})
        return normalized

    @staticmethod
    def _dedupe_source_chain(source_chain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in source_chain:
            if not isinstance(item, dict):
                continue
            provider = str(item.get("provider") or "").strip()
            result = str(item.get("result") or "").strip()
            duration = item.get("duration_ms")
            key = (provider, result, duration)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @staticmethod
    def _extract_valuation_snapshot(quote: Any, fundamental_context: Optional[Dict[str, Any]]) -> Dict[str, Optional[float]]:
        valuation_block = {}
        if isinstance(fundamental_context, dict):
            raw_block = fundamental_context.get("valuation")
            if isinstance(raw_block, dict):
                raw_data = raw_block.get("data")
                if isinstance(raw_data, dict):
                    valuation_block = raw_data

        quote_pe_ratio = getattr(quote, "pe_ratio", None) if quote else None
        quote_pb_ratio = getattr(quote, "pb_ratio", None) if quote else None
        quote_total_mv = getattr(quote, "total_mv", None) if quote else None
        quote_circ_mv = getattr(quote, "circ_mv", None) if quote else None

        return {
            "pe_ratio": StockQueryService._safe_float(
                quote_pe_ratio if quote_pe_ratio is not None else valuation_block.get("pe_ratio")
            ),
            "pb_ratio": StockQueryService._safe_float(
                quote_pb_ratio if quote_pb_ratio is not None else valuation_block.get("pb_ratio")
            ),
            "total_mv": StockQueryService._safe_float(
                quote_total_mv if quote_total_mv is not None else valuation_block.get("total_mv")
            ),
            "circ_mv": StockQueryService._safe_float(
                quote_circ_mv if quote_circ_mv is not None else valuation_block.get("circ_mv")
            ),
        }

    @staticmethod
    def _extract_fundamental_coverage(fundamental_context: Optional[Dict[str, Any]]) -> Dict[str, str]:
        if not isinstance(fundamental_context, dict):
            return {}
        coverage = fundamental_context.get("coverage")
        if not isinstance(coverage, dict):
            return {}
        return {str(key): str(value) for key, value in coverage.items() if key}

    @staticmethod
    def _extract_fundamental_errors(fundamental_context: Optional[Dict[str, Any]]) -> List[str]:
        if not isinstance(fundamental_context, dict):
            return []
        errors = fundamental_context.get("errors")
        if not isinstance(errors, list):
            return []
        normalized: List[str] = []
        seen = set()
        for item in errors:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    @staticmethod
    def _extract_fundamental_details(fundamental_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(fundamental_context, dict):
            return {}

        details: Dict[str, Any] = {}
        for key in ("valuation", "growth", "earnings", "institution", "capital_flow", "dragon_tiger", "boards"):
            block = fundamental_context.get(key)
            if not isinstance(block, dict):
                continue
            data = block.get("data")
            if isinstance(data, dict) and data:
                details[key] = data
        return details

    def _persist_query_record(
        self,
        *,
        query_id: str,
        request: Any,
        query_text: str,
        payload: Dict[str, Any],
    ) -> None:
        try:
            save_stock_query_record(
                self.db,
                query_id=query_id,
                status="completed",
                query_text=query_text or None,
                stock_code=str(payload.get("stock_code") or "") or None,
                stock_name=str(payload.get("stock_name") or "") or None,
                signal=str(payload.get("signal") or "") or None,
                request_payload=self._serialize_request_payload(request),
                result_payload=payload,
                completed_at=datetime.now(),
            )
        except Exception as exc:
            logger.error("[StockQuery] 落库失败: %s", exc, exc_info=True)

    @staticmethod
    def _serialize_request_payload(request: Any) -> Dict[str, Any]:
        if hasattr(request, "model_dump"):
            payload = request.model_dump()
            return payload if isinstance(payload, dict) else {}
        if isinstance(request, dict):
            return dict(request)
        return {
            "query": getattr(request, "query", None),
            "stock_code": getattr(request, "stock_code", None),
            "stock_name": getattr(request, "stock_name", None),
        }

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _augment_with_realtime(df, quote: Any):
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
