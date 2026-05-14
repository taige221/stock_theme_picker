# -*- coding: utf-8 -*-
"""
===================================
Single Stock Text Supplement Service
===================================
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from theme_picker.search_service import (
    SearchResponse,
    SearchService,
    SerpAPISearchProvider,
    TavilySearchProvider,
    get_search_service,
)

logger = logging.getLogger(__name__)


class StockTextSupplementService:
    """Fetch stock text supplements using a multi-dimension intel bundle."""

    _BUNDLE_CACHE_TTL_SECONDS = 120.0

    def __init__(self) -> None:
        self._search_service = get_search_service()
        self._bundle_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self._bundle_cache_lock = threading.RLock()

    @property
    def is_available(self) -> bool:
        return bool(self._preferred_providers())

    @property
    def provider_names(self) -> List[str]:
        names: List[str] = []
        for search_provider in self._preferred_providers():
            names.append(getattr(search_provider, "name", "SerpAPI"))
        return names

    def get_earnings_text(self, stock_code: str, stock_name: str) -> Dict[str, Any]:
        block = self._get_dimension_block(stock_code, stock_name, "earnings")
        if not block:
            return {}
        return {
            "summary": block.get("summary") or "",
            "provider": block.get("provider") or "search",
            "headlines": list(block.get("headlines") or [])[:3],
            "highlights": list(block.get("highlights") or [])[:4],
            "provider_attempted": list(block.get("provider_attempted") or self.provider_names),
            "dimension": "earnings",
        }

    def get_institution_text(self, stock_code: str, stock_name: str) -> Dict[str, Any]:
        block = self._get_dimension_block(stock_code, stock_name, "market_analysis")
        if not block:
            return {}
        return {
            "summary": block.get("summary") or "",
            "provider": block.get("provider") or "search",
            "headlines": list(block.get("headlines") or [])[:3],
            "highlights": list(block.get("highlights") or [])[:4],
            "provider_attempted": list(block.get("provider_attempted") or self.provider_names),
            "dimension": "market_analysis",
        }

    def get_stock_news_summary(self, stock_code: str, stock_name: str) -> Dict[str, Any]:
        bundle = self.build_stock_intel_bundle(stock_code, stock_name)
        dimensions = bundle.get("dimensions") or {}
        latest_block = dimensions.get("latest_news") or {}
        risk_block = dimensions.get("risk_check") or {}
        announcements_block = dimensions.get("announcements") or {}

        headlines = self._merge_unique_texts(
            list(latest_block.get("headlines") or []),
            list(risk_block.get("headlines") or []),
            list(announcements_block.get("headlines") or []),
            limit=5,
        )
        if not headlines:
            return {}

        summary_parts = [
            str(latest_block.get("summary") or "").strip(),
            str(risk_block.get("summary") or "").strip(),
            str(announcements_block.get("summary") or "").strip(),
        ]
        summary = "；".join(part for part in summary_parts if part).strip()
        catalysts = self._extract_catalysts(headlines)
        risk_events = self._merge_unique_texts(
            list(risk_block.get("highlights") or []),
            self._extract_risk_events(headlines),
            limit=5,
        )
        sentiment = self._derive_sentiment(" ".join([summary, *headlines]), risk_events=risk_events)
        providers_used = self._merge_unique_texts(
            [str(latest_block.get("provider") or "").strip()],
            [str(risk_block.get("provider") or "").strip()],
            [str(announcements_block.get("provider") or "").strip()],
            limit=3,
        )

        return {
            "summary": summary,
            "provider": " / ".join(providers_used) if providers_used else "search",
            "headlines": headlines[:3],
            "catalysts": catalysts[:3],
            "risk_events": risk_events[:3],
            "sentiment": sentiment,
            "provider_attempted": list(bundle.get("provider_attempted") or self.provider_names),
            "dimensions": ["latest_news", "risk_check", "announcements"],
        }

    def get_profile_text(self, stock_code: str, stock_name: str) -> Dict[str, Any]:
        block = self._get_dimension_block(stock_code, stock_name, "profile")
        if not block:
            return {}
        headlines = list(block.get("headlines") or [])
        highlights = self._extract_profile_highlights(headlines)
        return {
            "summary": str(block.get("summary") or "").strip(),
            "provider": block.get("provider") or "search",
            "headlines": headlines[:3],
            "highlights": highlights[:4],
            "provider_attempted": list(block.get("provider_attempted") or self.provider_names),
            "dimension": "profile",
        }

    def get_announcement_text(self, stock_code: str, stock_name: str) -> Dict[str, Any]:
        block = self._get_dimension_block(stock_code, stock_name, "announcements")
        if not block:
            return {}
        headlines = list(block.get("headlines") or [])
        highlights = self._extract_announcement_highlights(headlines)
        return {
            "summary": str(block.get("summary") or "").strip(),
            "provider": block.get("provider") or "search",
            "headlines": headlines[:4],
            "highlights": highlights[:4],
            "provider_attempted": list(block.get("provider_attempted") or self.provider_names),
            "dimension": "announcements",
        }

    def get_lockup_text(self, stock_code: str, stock_name: str) -> Dict[str, Any]:
        block = self._get_dimension_block(stock_code, stock_name, "lockup")
        if not block:
            return {}
        headlines = list(block.get("headlines") or [])
        highlights = self._extract_lockup_highlights(headlines)
        return {
            "summary": str(block.get("summary") or "").strip(),
            "provider": block.get("provider") or "search",
            "headlines": headlines[:4],
            "highlights": highlights[:4],
            "provider_attempted": list(block.get("provider_attempted") or self.provider_names),
            "dimension": "lockup",
        }

    def build_stock_intel_bundle(self, stock_code: str, stock_name: str) -> Dict[str, Any]:
        cache_key = self._bundle_cache_key(stock_code, stock_name)
        cached = self._get_cached_bundle(cache_key)
        if cached is not None:
            return cached

        providers = self._preferred_providers()
        if not providers:
            logger.info("单股文本补充未执行：未找到可用的 Tavily/SerpAPI provider")
            bundle = {
                "provider_attempted": [],
                "providers_used": [],
                "dimensions": {},
            }
            self._put_cached_bundle(cache_key, bundle)
            return bundle

        provider_attempted = [getattr(provider, "name", type(provider).__name__) for provider in providers]
        search_days = max(3, int(getattr(self._search_service, "news_window_days", 3) or 3))
        max_items = 3
        dimensions: Dict[str, Dict[str, Any]] = {}
        providers_used: List[str] = []

        for dimension in self._build_dimensions(stock_code, stock_name):
            response = self._search_dimension(
                providers=providers,
                dimension=dimension,
                days=search_days,
                max_results=max_items,
            )
            block = self._response_to_dimension_block(
                name=str(dimension.get("name") or ""),
                response=response,
                provider_attempted=provider_attempted,
            )
            if block:
                dimensions[str(dimension.get("name") or "")] = block
                provider_name = str(block.get("provider") or "").strip()
                if provider_name and provider_name not in providers_used:
                    providers_used.append(provider_name)

        bundle = {
            "provider_attempted": provider_attempted,
            "providers_used": providers_used,
            "dimensions": dimensions,
        }
        self._put_cached_bundle(cache_key, bundle)
        return bundle

    def _preferred_providers(self) -> List[Any]:
        tavily_providers: List[Any] = []
        serpapi_providers: List[Any] = []
        for search_provider in (getattr(self._search_service, "_providers", []) or []):
            if not getattr(search_provider, "is_available", False):
                continue
            if isinstance(search_provider, TavilySearchProvider):
                tavily_providers.append(search_provider)
            elif isinstance(search_provider, SerpAPISearchProvider):
                serpapi_providers.append(search_provider)
        return tavily_providers + serpapi_providers

    def _bundle_cache_key(self, stock_code: str, stock_name: str) -> str:
        return f"{stock_code.strip().upper()}::{stock_name.strip()}::{','.join(self.provider_names)}"

    def _get_cached_bundle(self, cache_key: str) -> Optional[Dict[str, Any]]:
        with self._bundle_cache_lock:
            cached = self._bundle_cache.get(cache_key)
            if cached is None:
                return None
            cached_at, bundle = cached
            if (time.time() - cached_at) > self._BUNDLE_CACHE_TTL_SECONDS:
                self._bundle_cache.pop(cache_key, None)
                return None
            return bundle

    def _put_cached_bundle(self, cache_key: str, bundle: Dict[str, Any]) -> None:
        with self._bundle_cache_lock:
            self._bundle_cache[cache_key] = (time.time(), bundle)

    def _get_dimension_block(self, stock_code: str, stock_name: str, dimension: str) -> Dict[str, Any]:
        bundle = self.build_stock_intel_bundle(stock_code, stock_name)
        dimensions = bundle.get("dimensions")
        if not isinstance(dimensions, dict):
            return {}
        block = dimensions.get(dimension)
        if not isinstance(block, dict) or str(block.get("status") or "") != "ok":
            return {}
        return block

    def _build_dimensions(self, stock_code: str, stock_name: str) -> List[Dict[str, Any]]:
        is_foreign = bool(self._search_service._is_foreign_stock(stock_code))
        if is_foreign:
            return [
                {"name": "latest_news", "query": f"{stock_name} {stock_code} latest news major events", "strict_freshness": True},
                {"name": "market_analysis", "query": f"{stock_name} analyst rating target price report", "strict_freshness": False},
                {"name": "risk_check", "query": f"{stock_name} insider selling lawsuit litigation regulatory risk", "strict_freshness": True},
                {"name": "announcements", "query": f"{stock_name} {stock_code} investor relations filing SEC announcement", "strict_freshness": True},
                {"name": "earnings", "query": f"{stock_name} earnings revenue profit growth forecast", "strict_freshness": False},
                {"name": "profile", "query": f"{stock_name} company overview core business key products market position", "strict_freshness": False},
                {"name": "lockup", "query": f"{stock_name} share unlock insider sale lock-up expiration", "strict_freshness": False},
            ]
        return [
            {"name": "latest_news", "query": f"{stock_name} {stock_code} 最新 新闻 重大 事件", "strict_freshness": True},
            {"name": "market_analysis", "query": f"{stock_name} 研报 目标价 评级 深度分析", "strict_freshness": False},
            {"name": "risk_check", "query": f"{stock_name} 减持 处罚 违规 诉讼 利空 风险", "strict_freshness": True},
            {"name": "announcements", "query": f"{stock_name} {stock_code} 公司公告 重要公告 上交所 深交所 cninfo", "strict_freshness": True},
            {"name": "earnings", "query": f"{stock_name} 业绩预告 财报 营收 净利润 同比增长", "strict_freshness": False},
            {"name": "profile", "query": f"{stock_name} {stock_code} 公司简介 主营业务 核心产品 行业地位", "strict_freshness": False},
            {"name": "lockup", "query": f"{stock_name} {stock_code} 限售解禁 解禁市值 解禁时间 股东减持", "strict_freshness": False},
        ]

    def _search_dimension(
        self,
        *,
        providers: List[SerpAPISearchProvider],
        dimension: Dict[str, Any],
        days: int,
        max_results: int,
    ) -> SearchResponse:
        query = str(dimension.get("query") or "").strip()
        dimension_name = str(dimension.get("name") or "").strip() or "unknown"
        strict_freshness = bool(dimension.get("strict_freshness"))
        had_provider_success = False
        fallback_response: Optional[SearchResponse] = None

        for provider in providers:
            try:
                response = provider.search(query, max_results=max_results, days=days)
            except Exception as exc:
                logger.warning(
                    "单股情报维度搜索失败: provider=%s dimension=%s query=%s error=%s",
                    getattr(provider, "name", type(provider).__name__),
                    dimension_name,
                    query,
                    exc,
                )
                continue

            had_provider_success = had_provider_success or bool(response.success)
            normalized = response
            if strict_freshness:
                filtered = self._search_service._filter_news_response(
                    response,
                    search_days=days,
                    max_results=max_results,
                    log_scope=f"{dimension_name}:{query}",
                )
                if filtered.success and filtered.results:
                    return filtered
                normalized = filtered
                if response.success and response.results:
                    # For single-stock context, keep a softer fallback when the
                    # provider returned usable articles but published dates are
                    # missing or unparsable. This avoids clearing the whole
                    # context block just because freshness metadata is weak.
                    normalized = self._search_service._normalize_and_limit_response(
                        response,
                        max_results=max_results,
                    )
            elif response.success:
                normalized = self._search_service._limit_search_response(response, max_results=max_results)

            if normalized.success and normalized.results:
                return normalized
            if response.success and fallback_response is None:
                fallback_response = normalized

        if fallback_response is not None:
            return fallback_response
        if had_provider_success:
            return SearchResponse(
                query=query,
                results=[],
                provider="Filtered",
                success=True,
                error_message=None,
            )
        return SearchResponse(
            query=query,
            results=[],
            provider="None",
            success=False,
            error_message="所有搜索 provider 均失败",
        )

    def _response_to_dimension_block(
        self,
        *,
        name: str,
        response: SearchResponse,
        provider_attempted: List[str],
    ) -> Dict[str, Any]:
        if not response.success and not response.results:
            return {
                "status": "error",
                "provider": response.provider or "search",
                "provider_attempted": list(provider_attempted),
                "query": response.query,
                "error": response.error_message,
            }

        if not response.results:
            return {
                "status": "empty",
                "provider": response.provider or "search",
                "provider_attempted": list(provider_attempted),
                "query": response.query,
            }

        aggregated: List[Dict[str, str]] = []
        seen_urls = set()
        for item in response.results[:3]:
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            aggregated.append(
                {
                    "title": item.title,
                    "snippet": item.snippet,
                    "source": item.source,
                    "published_date": item.published_date or "",
                }
            )

        headlines = [item["title"] for item in aggregated if item.get("title")]
        text = " ".join(headlines)
        if name == "announcements":
            highlights = self._extract_announcement_highlights(headlines)
        elif name == "lockup":
            highlights = self._extract_lockup_highlights(headlines)
        elif name == "profile":
            highlights = self._extract_profile_highlights(headlines)
        elif name == "risk_check":
            highlights = self._extract_risk_events(headlines)
        elif name == "earnings":
            highlights = self._extract_catalysts(headlines)
        elif name == "market_analysis":
            highlights = self._extract_institution_highlights(headlines)
        else:
            highlights = self._extract_catalysts(headlines) if text else []

        return {
            "status": "ok",
            "provider": response.provider or "search",
            "provider_attempted": list(provider_attempted),
            "query": response.query,
            "summary": self._build_summary(aggregated),
            "headlines": headlines[:3],
            "highlights": highlights[:4],
        }

    @staticmethod
    def _build_summary(results: List[Dict[str, str]]) -> str:
        lines: List[str] = []
        for item in results[:2]:
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if snippet and snippet not in title:
                lines.append(f"{title}：{snippet[:80]}")
            elif title:
                lines.append(title)
        return "；".join(line for line in lines if line).strip()

    @staticmethod
    def _extract_catalysts(headlines: List[str]) -> List[str]:
        keywords = [
            "业绩预告",
            "快报",
            "公告",
            "订单",
            "中标",
            "调研",
            "回购",
            "增持",
            "减持",
            "监管",
            "异动",
            "合作",
            "合同",
        ]
        matched: List[str] = []
        text = " ".join(str(item or "") for item in headlines)
        for keyword in keywords:
            if keyword in text and keyword not in matched:
                matched.append(keyword)
        return matched

    @staticmethod
    def _extract_risk_events(headlines: List[str]) -> List[str]:
        keywords = [
            "减持",
            "监管",
            "问询",
            "处罚",
            "风险",
            "亏损",
            "下滑",
            "冻结",
            "诉讼",
            "违规",
            "立案",
            "终止",
            "跌停",
        ]
        matched: List[str] = []
        text = " ".join(str(item or "") for item in headlines)
        for keyword in keywords:
            if keyword in text and keyword not in matched:
                matched.append(keyword)
        return matched

    @staticmethod
    def _extract_profile_highlights(headlines: List[str]) -> List[str]:
        keywords = [
            "主营业务",
            "核心产品",
            "行业地位",
            "产业链",
            "客户",
            "技术",
            "平台",
        ]
        matched: List[str] = []
        text = " ".join(str(item or "") for item in headlines)
        for keyword in keywords:
            if keyword in text and keyword not in matched:
                matched.append(keyword)
        return matched

    @staticmethod
    def _extract_institution_highlights(headlines: List[str]) -> List[str]:
        keywords = [
            "评级",
            "目标价",
            "买入",
            "增持",
            "调研",
            "机构",
            "券商",
            "覆盖",
        ]
        matched: List[str] = []
        text = " ".join(str(item or "") for item in headlines)
        for keyword in keywords:
            if keyword in text and keyword not in matched:
                matched.append(keyword)
        return matched

    @staticmethod
    def _extract_announcement_highlights(headlines: List[str]) -> List[str]:
        keywords = [
            "订单",
            "中标",
            "回购",
            "合作",
            "问询",
            "监管",
            "减持",
            "增持",
            "停牌",
            "诉讼",
        ]
        matched: List[str] = []
        text = " ".join(str(item or "") for item in headlines)
        for keyword in keywords:
            if keyword in text and keyword not in matched:
                matched.append(keyword)
        return matched

    @staticmethod
    def _extract_lockup_highlights(headlines: List[str]) -> List[str]:
        keywords = [
            "解禁",
            "限售",
            "解禁市值",
            "股东减持",
            "首发原股东",
            "定向增发",
        ]
        matched: List[str] = []
        text = " ".join(str(item or "") for item in headlines)
        for keyword in keywords:
            if keyword in text and keyword not in matched:
                matched.append(keyword)
        return matched

    @staticmethod
    def _merge_unique_texts(*groups: List[str], limit: int = 5) -> List[str]:
        merged: List[str] = []
        for group in groups:
            for item in group:
                text = str(item or "").strip()
                if not text or text in merged:
                    continue
                merged.append(text)
                if len(merged) >= limit:
                    return merged
        return merged

    @staticmethod
    def _derive_sentiment(text: str, *, risk_events: Optional[List[str]] = None) -> str:
        normalized = str(text or "")
        if not normalized:
            return "neutral"

        risk_keywords = ("减持", "监管", "问询", "处罚", "风险", "下滑", "亏损")
        positive_keywords = ("订单", "中标", "回购", "增持", "预增", "扭亏", "合作", "突破")

        if risk_events:
            return "risk"
        if any(keyword in normalized for keyword in risk_keywords):
            return "risk"
        if any(keyword in normalized for keyword in positive_keywords):
            return "positive"
        return "mixed"
